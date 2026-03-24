"""Tracely FastAPI application — main entry point."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings
from .entity_map import EntityMap
from .ha_client import HAClient
from .health import get_health, get_metrics_text, get_runtime_metrics
from .models import (
    AlertResponse,
    BookmarkRequest,
    EventRecord,
    EventResponse,
    HealthResponse,
    IncidentResponse,
    KnxFlowResponse,
    KnxGroupAddressResponse,
    KnxTelegramResponse,
    PaginatedEvents,
    PaginatedKnxTelegrams,
)
from .normalizer import Normalizer
from .purge import PurgeManager
from .storage import Storage
from .tree_builder import TreeBuilder
from .device_monitor import DeviceMonitor
from . import logs

logger = structlog.get_logger(__name__)

# ─── Globals (initialised during lifespan) ───────────────

settings = Settings()
storage = Storage(settings)
entity_map = EntityMap()
normalizer = Normalizer(entity_map)
tree_builder = TreeBuilder(storage, settings)
purge_manager = PurgeManager(storage, settings)
device_monitor = DeviceMonitor(settings, entity_map)
ha_client: HAClient | None = None
_start_time: float = time.time()

# Alert SSE clients — separate from event SSE
alert_sse_clients: set[asyncio.Queue[str]] = set()

# SSE clients — general events
sse_clients: set[asyncio.Queue[str]] = set()
# SSE clients — KNX telegrams
knx_sse_clients: set[asyncio.Queue[str]] = set()

# Dedup / rate state
_dedup_cache: dict[str, float] = {}
_sensor_counts: dict[str, list[float]] = defaultdict(list)

# Event processing queue (back-pressure at 10 000 items)
_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10_000)
_processor_task: asyncio.Task[None] | None = None
_runtime_monitor_task: asyncio.Task[None] | None = None
_entity_reload_lock = asyncio.Lock()
_incident_last_seen: dict[str, float] = {}
_runtime_status: dict[str, Any] = {
    "cpu_percent": 0.0,
    "memory_percent": 0.0,
    "memory_rss_mb": 0.0,
    "event_queue_depth": 0,
    "last_async_block_ms": 0.0,
    "ha_restart_count": 0,
}

# KNX diagnostics — track recent raw events for debugging
_knx_diag: dict[str, Any] = {
    "received": 0,
    "stored": 0,
    "dropped_no_ga": 0,
    "last_error": None,
    "recent_raw": deque(maxlen=10),  # last 10 raw knx_event data dicts
}


# ─── Rate-limiter middleware ─────────────────────────────


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple token-bucket rate limiter per client IP."""

    def __init__(
        self, app: Any, *, max_requests: int = 100, window: int = 60,
    ) -> None:
        super().__init__(app)
        self._max = max_requests
        self._window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._hits[ip] = [t for t in self._hits[ip] if t > now - self._window]
        if len(self._hits[ip]) >= self._max:
            return Response(
                content='{"error":"rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )
        self._hits[ip].append(now)
        return await call_next(request)


# ─── Helpers ─────────────────────────────────────────────


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _parse_timestamp(value: str | None) -> int | None:
    """Parse a timestamp string to epoch-ms. Accepts epoch-ms digits or ISO 8601."""
    if not value:
        return None
    if value.isdigit():
        return int(value)
    try:
        dt = datetime.fromisoformat(value)
        return int(dt.timestamp() * 1000)
    except (ValueError, OverflowError):
        return None


def _to_response(row: dict[str, Any]) -> EventResponse:
    ts = row.get("timestamp", 0)
    iso = (
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        if ts
        else ""
    )
    payload_str = row.get("payload", "{}")
    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        payload = {}

    return EventResponse(
        id=row["id"],
        parent_id=row.get("parent_id"),
        event_type=row.get("event_type", ""),
        domain=row.get("domain"),
        service=row.get("service"),
        entity_id=row.get("entity_id"),
        payload=payload,
        name=row.get("name"),
        integration=row.get("integration"),
        area=row.get("area"),
        timestamp=iso,
        user_id=row.get("user_id"),
        important=bool(row.get("important", 0)),
        confidence=row.get("confidence", "propagated"),
        generated_root=bool(row.get("generated_root", 0)),
    )


def _dedup_hash(entity_id: str | None, event_type: str, payload: str) -> str:
    data = f"{entity_id}:{event_type}:{payload}"
    return hashlib.md5(data.encode()).hexdigest()  # noqa: S324


# ─── Event ingestion pipeline ────────────────────────────


async def _process_ha_event(raw_event: dict[str, Any]) -> None:
    """Receive raw HA event → push into async processing queue."""
    try:
        _event_queue.put_nowait(raw_event)
    except asyncio.QueueFull:
        logger.warning("event_queue.full")


def _normalize_raw_event(raw_event: dict[str, Any]) -> EventRecord | None:
    """Turn a raw HA event dict into an EventRecord (or None if deduped)."""
    event_type = raw_event.get("event_type", "")
    data = raw_event.get("data", {})
    context = raw_event.get("context", {})

    # Generate ID
    event_id = context.get("id") or TreeBuilder.generate_event_id(
        json.dumps(raw_event, default=str),
    )
    parent_id = context.get("parent_id")
    user_id = context.get("user_id")

    # Entity & domain resolution
    entity_id = normalizer.extract_entity_id(event_type, data)
    domain, service = normalizer.extract_domain_service(event_type, data)

    # Update entity map from state_changed payloads
    if event_type == "state_changed" and entity_id:
        new_st = data.get("new_state")
        if new_st:
            entity_map.update_entity(entity_id, new_st)

    # Dedup check
    payload_str = json.dumps(data, sort_keys=True, default=str)
    dedup_key = _dedup_hash(entity_id, event_type, payload_str)
    now = time.time()
    if dedup_key in _dedup_cache:
        if (now - _dedup_cache[dedup_key]) < (settings.dedup_window_ms / 1000):
            return None
    _dedup_cache[dedup_key] = now

    # High-frequency sensor aggregation
    if entity_id and event_type == "state_changed":
        ts_list = _sensor_counts[entity_id]
        ts_list.append(now)
        _sensor_counts[entity_id] = [t for t in ts_list if t > now - 1.0]
        if len(_sensor_counts[entity_id]) > settings.aggregate_threshold_per_sec:
            return None  # skip — aggregate mode

    # Housekeep dedup cache
    if len(_dedup_cache) > 10_000:
        _dedup_cache.clear()  # simple periodic reset

    # Resolve entity info
    entity_info = entity_map.resolve(entity_id)
    area = entity_info.area if entity_info else ""
    integration = entity_info.integration if entity_info else ""

    # Infer integration from entity_id if not set by registry
    if not integration and entity_id:
        eid_lower = entity_id.lower()
        if "knx" in eid_lower:
            integration = "knx"
        elif "z2m" in eid_lower or "zigbee2mqtt" in eid_lower:
            integration = "mqtt"
        elif "zha" in eid_lower:
            integration = "zha"
        elif "esphome" in eid_lower:
            integration = "esphome"
        elif "hue" in eid_lower:
            integration = "hue"

    # Human-readable name
    name = normalizer.label(event_type, data, entity_id)

    # Timestamp
    time_fired = raw_event.get("time_fired")
    if time_fired:
        try:
            dt = datetime.fromisoformat(time_fired.replace("Z", "+00:00"))
            timestamp_ms = int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            timestamp_ms = _epoch_ms()
    else:
        timestamp_ms = _epoch_ms()

    confidence = "propagated" if parent_id else "inferred"
    if not domain and entity_id and "." in entity_id:
        domain = entity_id.split(".")[0]

    return EventRecord(
        id=event_id,
        parent_id=parent_id,
        event_type=event_type,
        domain=domain,
        service=service,
        entity_id=entity_id,
        payload=payload_str,
        name=name,
        integration=integration or None,
        area=area or None,
        timestamp=timestamp_ms,
        user_id=user_id,
        important=0,
        confidence=confidence,
        generated_root=0,
    )


async def _event_processor() -> None:
    """Background task: read raw events from queue, normalise, store, link, fan-out SSE."""
    while True:
        try:
            # Block-wait for the first event
            raw = await _event_queue.get()
            batch: list[EventRecord] = []
            # KNX events are handled separately (not stored in events table)
            if raw.get("event_type") in {"knx_event", "knx.telegram"}:
                await _process_knx_event(raw)
                continue

            record = _normalize_raw_event(raw)
            if record:
                batch.append(record)

            # Drain queue for up to 50 ms (batch window)
            await asyncio.sleep(0.05)
            while not _event_queue.empty() and len(batch) < 200:
                try:
                    raw = _event_queue.get_nowait()
                    if raw.get("event_type") in {"knx_event", "knx.telegram"}:
                        await _process_knx_event(raw)
                        continue
                    rec = _normalize_raw_event(raw)
                    if rec:
                        batch.append(rec)
                except asyncio.QueueEmpty:
                    break

            if not batch:
                continue

            # Bulk insert
            try:
                await storage.insert_events_batch(batch)
            except Exception:
                logger.exception("event_processor.insert_error")
                try:
                    await purge_manager.emergency_purge()
                except Exception:
                    logger.exception("event_processor.emergency_purge_error")
                continue

            # Link + SSE fan-out
            for rec in batch:
                await tree_builder.link(rec)
                _fan_out_sse(rec)

                if rec.event_type in {"homeassistant_start", "homeassistant_stop"}:
                    asyncio.create_task(
                        _handle_ha_lifecycle_event(rec),
                        name=f"ha-lifecycle-{rec.event_type}",
                    )

                # Device offline monitoring
                if rec.event_type == "state_changed" and rec.entity_id:
                    try:
                        payload = json.loads(rec.payload) if isinstance(rec.payload, str) else rec.payload
                        old_s = payload.get("old_state", {})
                        new_s = payload.get("new_state", {})
                        old_state = old_s.get("state") if isinstance(old_s, dict) else None
                        new_state = new_s.get("state", "") if isinstance(new_s, dict) else ""
                        alerts = device_monitor.process_state_change(
                            rec.entity_id, old_state, new_state, payload,
                        )
                        for alert_data in alerts:
                            await storage.insert_alert(**alert_data)
                            _fan_out_alert_sse(alert_data)
                    except Exception:
                        logger.debug("device_monitor.process_error", entity_id=rec.entity_id)

                # Reverse-link: if this is a state_changed for a KNX entity,
                # find the nearest KNX telegram on any of its GAs and record
                # the event_id on that telegram row so the KNX monitor can
                # show "→ caused state change" with a direct jump to the trace.
                if rec.event_type == "state_changed" and rec.entity_id:
                    info = entity_map.resolve(rec.entity_id)
                    is_knx = (
                        (info and info.integration == "knx")
                        or "knx" in (rec.entity_id or "").lower()
                    )
                    if is_knx:
                        # Extract GA candidates from entity attributes
                        ga_candidates: list[str] = []
                        if info:
                            for attr_key, attr_val in info.attributes.items():
                                if isinstance(attr_val, str) and "/" in attr_val and attr_key != "source":
                                    ga_candidates.append(attr_val)
                                elif isinstance(attr_val, list):
                                    for v in attr_val:
                                        if isinstance(v, str) and "/" in v:
                                            ga_candidates.append(v)
                        for ga_candidate in ga_candidates[:5]:  # safety cap
                            tg = await storage.find_recent_knx_telegram_for_ga(
                                ga_candidate, rec.timestamp, window_ms=2000,
                            )
                            if tg and not tg.get("linked_event_id"):
                                await storage.update_knx_telegram_event_link(tg["id"], rec.id)
                                break

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("event_processor.error")


async def _run_backfill(client: HAClient, days: int) -> None:
    """
    Background task: backfill historical HA events.

    - Waits for the HA client to connect before starting.
    - Skips if the DB already has >= 500 events (subsequent restarts).
    - Uses INSERT OR IGNORE so duplicates cause no harm.
    - Runs with low priority by yielding to the event loop between batches.
    """
    # Wait for HA connection (max 30 s)
    for _ in range(30):
        if client.connected:
            break
        await asyncio.sleep(1)
    else:
        logger.warning("backfill.skipped_no_connection")
        return

    # Skip if we already appear to have historical data
    try:
        existing = await storage.get_event_count()
    except Exception:
        existing = 0

    if existing >= 500:
        logger.info("backfill.skipped_enough_data", existing=existing)
        return

    logger.info("backfill.starting", days=days, existing_events=existing)
    try:
        count = await client.fetch_history(days=days, on_event=_process_ha_event)
        logger.info("backfill.done", events_queued=count)
        # Let the processor drain
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info("backfill.cancelled")
    except Exception:
        logger.exception("backfill.error")


# ─── KNX helpers ────────────────────────────────────────


def _knx_epoch_ms(time_fired: str | None) -> int:
    if time_fired:
        try:
            dt = datetime.fromisoformat(time_fired.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            pass
    return _epoch_ms()


def _knx_to_response(row: dict[str, Any]) -> KnxTelegramResponse:
    logger.info("[_knx_to_response] ROW", row=row)
    ts = row.get("timestamp", 0)
    iso = (
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        if ts else ""
    )
    return KnxTelegramResponse(
        id=row["id"],
        timestamp=iso,
        group_address=row["group_address"],
        direction=row["direction"],
        source_address=row.get("source_address"),
        telegram_type=row["telegram_type"],
        raw_data=row.get("raw_data"),
        decoded_value=row.get("decoded_value"),
        dpt_type=row.get("dpt_type"),
        linked_entity_id=row.get("linked_entity_id"),
        linked_entity_name=entity_map.get_friendly_name(row.get("linked_entity_id")) or None,
        linked_event_id=row.get("linked_event_id"),
        context_id=row.get("context_id"),
    )


def _knx_ga_to_response(row: dict[str, Any]) -> KnxGroupAddressResponse:
    ts = row.get("last_seen", 0)
    iso = (
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        if ts else None
    )
    return KnxGroupAddressResponse(
        group_address=row["group_address"],
        friendly_name=row.get("friendly_name"),
        dpt_type=row.get("dpt_type"),
        linked_entities=row.get("linked_entities"),
        last_seen=iso,
        total_writes=row.get("total_writes") or 0,
        total_reads=row.get("total_reads") or 0,
        total_responses=row.get("total_responses") or 0,
        last_value=row.get("last_value"),
    )


async def _process_knx_event(raw_event: dict[str, Any]) -> None:
    """Extract KNX telegram from a raw knx_event OR knx/subscribe_telegrams and persist it.

    Two event paths reach this function:
    - "knx_event"    — from subscribe_events; fires only for fire_event:true GAs.
                       Fields: data.destination, data.source, data.data (bytes list),
                               data.dpt_name, data.value
    - "knx.telegram" — synthetic wrapper around knx/subscribe_telegrams (ALL telegrams,
                       same stream as the HA Group Monitor).
                       Fields: data.destination_address, data.source_address,
                               data.payload (hex str), data.dpt (dict), data.value,
                               data.destination_text (GA friendly name), data.unit
    """
    logger.info("[_PROCESS_KNX_EVENT] raw event", raw_event=raw_event)
    event_type = raw_event.get("event_type", "knx_event")
    data = raw_event.get("data", {})
    context = raw_event.get("context", {})

    # time_fired is set by knx_event; knx.telegram uses data.timestamp
    time_fired = raw_event.get("time_fired") or data.get("timestamp")
    timestamp_ms = _knx_epoch_ms(time_fired)

    _knx_diag["received"] += 1
    _knx_diag.setdefault("received_by_source", {"knx_event": 0, "knx.telegram": 0})
    _knx_diag["received_by_source"][event_type] = (
        _knx_diag["received_by_source"].get(event_type, 0) + 1
    )
    _knx_diag["recent_raw"].append({
        "source": event_type,
        "data_keys": list(data.keys()),
        "destination": data.get("destination") or data.get("destination_address"),
        "direction": data.get("direction"),
        "telegramtype": data.get("telegramtype"),
        "time_fired": time_fired,
    })

    # Group address — knx_event uses "destination", subscribe path uses "destination_address"
    ga = (
        data.get("destination")
        or data.get("destination_address")
        or data.get("group_address")
        or ""
    )
    if not ga:
        _knx_diag["dropped_no_ga"] += 1
        logger.warning("knx.dropped_no_ga", data_keys=list(data.keys()), source=event_type)
        return

    telegram_type = data.get("telegramtype") or data.get("telegram_type") or "Unknown"
    direction = data.get("direction", "Incoming")
    source = data.get("source") or data.get("source_address")

    # ── Raw bytes → hex string ──────────────────────────────────────────────
    # knx_event:    data.data  = list of ints, e.g. [0]
    # knx.telegram: data.payload = hex string, e.g. "0x00"
    raw_bytes = data.get("data")
    raw_hex: str | None = None
    if isinstance(raw_bytes, (list, bytes)):
        raw_hex = bytes(raw_bytes).hex() if isinstance(raw_bytes, list) else raw_bytes.hex()
    elif isinstance(raw_bytes, str):
        raw_hex = raw_bytes
    # knx/subscribe_telegrams provides a hex string directly in "payload"
    if raw_hex is None:
        payload_str = data.get("payload")
        if isinstance(payload_str, str) and payload_str:
            # Strip "0x" prefix so storage is consistent (pure hex, no prefix)
            raw_hex = payload_str[2:] if payload_str.startswith("0x") else payload_str

    # ── DPT type ────────────────────────────────────────────────────────────
    # knx_event:    data.dpt_name = "DPT-1" or None
    # knx.telegram: data.dpt = {"main": 1, "sub": 8} or None
    dpt_type: str | None = data.get("dpt_name")
    if dpt_type is None:
        dpt_dict = data.get("dpt")
        if isinstance(dpt_dict, dict):
            main = dpt_dict.get("main")
            sub = dpt_dict.get("sub")
            if main is not None:
                dpt_type = f"DPT-{main}.{sub:03d}" if sub is not None else f"DPT-{main}"

    # ── Decoded value → JSON-safe string ────────────────────────────────────
    decoded = data.get("value")
    unit = data.get("unit")
    decoded_str: str | None = None
    if decoded is not None:
        # If a unit is provided, append it for display (e.g. "23.5 °C")
        if unit and isinstance(decoded, (int, float, str)):
            decoded_str = f"{decoded} {unit}"
        else:
            decoded_str = json.dumps(decoded, default=str)

    # ── GA friendly name (only available from knx/subscribe_telegrams) ──────
    destination_text: str | None = data.get("destination_text") or None

    # ── Entity linkage (resolved early so it appears in the received log) ───
    # Strategy 1: scan entity attributes for the group address
    linked_entity: str | None = entity_map.find_entity_by_attribute("knx", ga)
    entity_match_method = "ga_attribute"
    # Strategy 2: match by KNX physical/individual source address ("source" attribute)
    # KNX entities expose their bus address as attributes["source"] (e.g. "1.1.17")
    if not linked_entity and source:
        linked_entity = entity_map.find_knx_entity_by_source(source)
        if linked_entity:
            entity_match_method = "source_address"
    linked_entity_name: str = entity_map.get_friendly_name(linked_entity) if linked_entity else ""

    logger.info(
        "knx.received",
        ga=ga,
        ga_name=destination_text or "",
        direction=direction,
        type=telegram_type,
        source=event_type,
        entity=linked_entity or "",
        entity_name=linked_entity_name,
        entity_match=entity_match_method if linked_entity else "none",
        value=decoded_str or (f"0x{raw_hex.upper()}" if raw_hex else ""),
        dpt=dpt_type or "",
    )

    # ── Deduplication ID ─────────────────────────────────────────────────────
    # Use a content-based hash so the same physical telegram arriving via
    # both knx_event AND knx/subscribe_telegrams produces the same ID and
    # INSERT OR IGNORE silently drops the duplicate.
    source_for_id = source or "?"
    telegram_id = TreeBuilder.generate_event_id(
        f"knx:{ga}:{source_for_id}:{telegram_type}:{timestamp_ms}"
    )
    # Preserve HA context id for event-chain linkage when available
    ha_context_id: str | None = context.get("id") or None

    telegram: dict[str, Any] = {
        "id": telegram_id,
        "timestamp": timestamp_ms,
        "group_address": ga,
        "direction": direction,
        "source_address": source,
        "telegram_type": telegram_type,
        "raw_data": raw_hex,
        "decoded_value": decoded_str,
        "dpt_type": dpt_type,
        "linked_entity_id": linked_entity,
        "linked_event_id": None,
        "context_id": ha_context_id,
        # Extra enrichment from knx/subscribe_telegrams (stored in GA table only)
        "_ga_name": destination_text,
    }
    try:
        await storage.insert_knx_telegram(telegram)
        _knx_diag["stored"] += 1

        # ── Cross-link: find the closest state_changed event for this entity ──
        # KNX writes typically trigger a state_changed within ~500 ms.  We look
        # in a ±2s window so we tolerate slow HA processing.
        linked_event_id: str | None = None
        if linked_entity:
            sc = await storage.find_recent_state_change_for_entity(
                linked_entity, timestamp_ms, window_ms=2000,
            )
            if sc:
                linked_event_id = sc["id"]
                await storage.update_knx_telegram_event_link(telegram_id, linked_event_id)

        logger.info(
            "knx.stored",
            ga=ga,
            id=telegram_id,
            entity=linked_entity or "",
            entity_name=linked_entity_name,
            entity_match=entity_match_method if linked_entity else "none",
            linked_event=linked_event_id or "",
            value=decoded_str or (f"0x{raw_hex.upper()}" if raw_hex else ""),
            dpt=dpt_type or "",
            direction=direction,
            type=telegram_type,
        )
    except Exception as exc:
        _knx_diag["last_error"] = str(exc)
        logger.exception("knx.insert_error", ga=ga)
        return

    # Fan-out to KNX SSE clients — refresh with updated linked_event_id
    telegram["linked_event_id"] = linked_event_id
    resp = _knx_to_response(telegram)
    sse_data = resp.model_dump_json()
    dead: set[asyncio.Queue[str]] = set()
    for client in knx_sse_clients:
        try:
            client.put_nowait(sse_data)
        except asyncio.QueueFull:
            dead.add(client)
    knx_sse_clients.difference_update(dead)


def _fan_out_sse(record: EventRecord) -> None:
    """Push event to all connected SSE clients."""
    resp = _to_response(
        {
            "id": record.id,
            "parent_id": record.parent_id,
            "event_type": record.event_type,
            "domain": record.domain,
            "service": record.service,
            "entity_id": record.entity_id,
            "payload": record.payload,
            "name": record.name,
            "integration": record.integration,
            "area": record.area,
            "timestamp": record.timestamp,
            "user_id": record.user_id,
            "important": record.important,
            "confidence": record.confidence,
            "generated_root": record.generated_root,
        },
    )
    sse_data = resp.model_dump_json()
    dead: set[asyncio.Queue[str]] = set()
    for client in sse_clients:
        try:
            client.put_nowait(sse_data)
        except asyncio.QueueFull:
            dead.add(client)
    sse_clients.difference_update(dead)


def _fan_out_alert_sse(alert_data: dict[str, Any]) -> None:
    """Push alert to all connected alert SSE clients."""
    ts = alert_data.get("timestamp", 0)
    iso = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat() if ts else ""
    details_raw = alert_data.get("details", "{}")
    try:
        details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
    except (json.JSONDecodeError, TypeError):
        details = {}
    resp = AlertResponse(
        id=alert_data.get("alert_id", ""),
        alert_type=alert_data.get("alert_type", ""),
        severity=alert_data.get("severity", "info"),
        title=alert_data.get("title", ""),
        message=alert_data.get("message", ""),
        entity_id=alert_data.get("entity_id"),
        integration=alert_data.get("integration"),
        details=details,
        acknowledged=False,
        timestamp=iso,
    )
    sse_data = resp.model_dump_json()
    dead: set[asyncio.Queue[str]] = set()
    for client in alert_sse_clients:
        try:
            client.put_nowait(sse_data)
        except asyncio.QueueFull:
            dead.add(client)
    alert_sse_clients.difference_update(dead)


def _incident_to_response(row: dict[str, Any]) -> IncidentResponse:
    ts = row.get("timestamp", 0)
    iso = (
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        if ts
        else ""
    )
    details_raw = row.get("details", "{}")
    try:
        details = json.loads(details_raw)
    except (json.JSONDecodeError, TypeError):
        details = {"raw": str(details_raw)}
    return IncidentResponse(
        id=row["id"],
        incident_type=row.get("incident_type", ""),
        severity=row.get("severity", "info"),
        source=row.get("source", "runtime_monitor"),
        message=row.get("message", ""),
        details=details,
        related_event_id=row.get("related_event_id"),
        cpu_percent=row.get("cpu_percent"),
        memory_percent=row.get("memory_percent"),
        memory_rss_mb=row.get("memory_rss_mb"),
        event_queue_depth=row.get("event_queue_depth"),
        loop_block_ms=row.get("loop_block_ms"),
        timestamp=iso,
    )


async def _record_incident(
    *,
    incident_type: str,
    severity: str,
    source: str,
    message: str,
    details: dict[str, Any],
    related_event_id: str | None = None,
    loop_block_ms: float | None = None,
    emit_timeline_event: bool = False,
) -> None:
    """Persist an incident with runtime context and optional timeline emission."""
    cooldown_key = f"{incident_type}:{severity}:{source}"
    now_s = time.time()
    last_seen = _incident_last_seen.get(cooldown_key, 0.0)
    if now_s - last_seen < settings.incident_cooldown_seconds:
        return
    _incident_last_seen[cooldown_key] = now_s

    timestamp_ms = _epoch_ms()
    runtime = get_runtime_metrics()
    queue_depth = _event_queue.qsize()
    incident_id = TreeBuilder.generate_event_id(
        f"incident:{incident_type}:{source}:{timestamp_ms}:{message}",
    )

    merged_details = {
        **details,
        "thresholds": {
            "cpu_spike_threshold_percent": settings.cpu_spike_threshold_percent,
            "memory_spike_threshold_percent": settings.memory_spike_threshold_percent,
            "async_block_threshold_ms": settings.async_block_threshold_ms,
            "queue_spike_threshold": settings.queue_spike_threshold,
        },
    }

    await storage.insert_incident(
        incident_id=incident_id,
        incident_type=incident_type,
        severity=severity,
        source=source,
        message=message,
        details=json.dumps(merged_details, default=str),
        related_event_id=related_event_id,
        cpu_percent=runtime["cpu_percent"],
        memory_percent=runtime["memory_percent"],
        memory_rss_mb=runtime["memory_rss_mb"],
        event_queue_depth=queue_depth,
        loop_block_ms=loop_block_ms,
        timestamp=timestamp_ms,
    )

    if severity in {"warning", "critical"}:
        logger.warning(
            "incident.recorded",
            incident_type=incident_type,
            message=message,
            cpu_percent=runtime["cpu_percent"],
            memory_percent=runtime["memory_percent"],
            memory_rss_mb=runtime["memory_rss_mb"],
            queue_depth=queue_depth,
            loop_block_ms=loop_block_ms,
        )
    else:
        logger.info(
            "incident.recorded",
            incident_type=incident_type,
            message=message,
            cpu_percent=runtime["cpu_percent"],
            memory_percent=runtime["memory_percent"],
            memory_rss_mb=runtime["memory_rss_mb"],
            queue_depth=queue_depth,
            loop_block_ms=loop_block_ms,
        )

    if emit_timeline_event:
        incident_event = EventRecord(
            id=f"incident_{incident_id}",
            parent_id=None,
            event_type="system_incident",
            domain="system",
            service=incident_type,
            entity_id="sensor.tracely_runtime",
            payload=json.dumps(
                {
                    "incident_id": incident_id,
                    "incident_type": incident_type,
                    "severity": severity,
                    "message": message,
                    "details": merged_details,
                },
                default=str,
            ),
            name=message,
            integration="tracely",
            area="system",
            timestamp=timestamp_ms,
            user_id=None,
            important=1 if severity == "critical" else 0,
            confidence="propagated",
            generated_root=1,
        )
        await storage.insert_event(incident_event)
        _fan_out_sse(incident_event)


async def _refresh_entity_registry(reason: str) -> None:
    """Refresh entities and registries after HA restart/start events."""
    if not ha_client:
        return
    async with _entity_reload_lock:
        try:
            entity_map.clear()
            states = await ha_client.fetch_states()
            entity_map.load_states(states)
            areas = await ha_client.fetch_area_registry()
            entity_map.load_areas(areas)
            devices = await ha_client.fetch_device_registry()
            entity_map.load_device_registry(devices)
            entries = await ha_client.fetch_entity_registry()
            entity_map.load_entity_registry(entries)
            logger.info(
                "entity_map.refreshed",
                reason=reason,
                entity_count=entity_map.count,
            )
        except Exception:
            logger.exception("entity_map.refresh_failed", reason=reason)


async def _handle_ha_lifecycle_event(record: EventRecord) -> None:
    """Track HA start/stop as explicit incidents for forensic debugging."""
    if record.event_type not in {"homeassistant_start", "homeassistant_stop"}:
        return

    logger.info(
        "ha_lifecycle.detected",
        event_type=record.event_type,
        timestamp=record.timestamp,
    )

    if record.event_type == "homeassistant_start":
        _runtime_status["ha_restart_count"] = int(_runtime_status.get("ha_restart_count", 0)) + 1

    try:
        await _record_incident(
            incident_type="ha_lifecycle",
            severity="info",
            source=record.event_type,
            message=f"HA {'started' if record.event_type == 'homeassistant_start' else 'stopped'}",
            details={
                "ha_event_type": record.event_type,
                "event_id": record.id,
                "event_name": record.name,
            },
            related_event_id=record.id,
            loop_block_ms=float(_runtime_status.get("last_async_block_ms", 0.0)),
            emit_timeline_event=True,  # CHANGED: Always emit to timeline for visibility
        )
        logger.info(
            "ha_lifecycle.recorded",
            event_type=record.event_type,
        )
    except Exception as e:
        logger.exception(
            "ha_lifecycle.record_error",
            event_type=record.event_type,
            error=str(e),
        )

    if record.event_type == "homeassistant_start":
        asyncio.create_task(
            _refresh_entity_registry("homeassistant_start"),
            name="refresh-entities-on-ha-start",
        )


async def _runtime_monitor() -> None:
    """Monitor runtime pressure and async-loop blockage for incident logging."""
    interval_s = max(settings.monitor_interval_seconds, 1)
    last_tick = time.perf_counter()

    while True:
        try:
            await asyncio.sleep(interval_s)
            now = time.perf_counter()
            loop_block_ms = max(0.0, (now - last_tick - interval_s) * 1000.0)
            last_tick = now

            runtime = get_runtime_metrics()
            queue_depth = _event_queue.qsize()
            _runtime_status.update(
                {
                    "cpu_percent": runtime["cpu_percent"],
                    "memory_percent": runtime["memory_percent"],
                    "memory_rss_mb": runtime["memory_rss_mb"],
                    "event_queue_depth": queue_depth,
                    "last_async_block_ms": loop_block_ms,
                },
            )

            if loop_block_ms >= settings.async_block_threshold_ms:
                await _record_incident(
                    incident_type="async_blockage",
                    severity="warning",
                    source="runtime_monitor",
                    message=(
                        "Async event loop blockage detected "
                        f"({loop_block_ms:.1f} ms)"
                    ),
                    details={"loop_block_ms": round(loop_block_ms, 2)},
                    loop_block_ms=loop_block_ms,
                    emit_timeline_event=True,
                )

            if runtime["cpu_percent"] >= settings.cpu_spike_threshold_percent:
                await _record_incident(
                    incident_type="cpu_spike",
                    severity="warning",
                    source="runtime_monitor",
                    message=(
                        "CPU usage spike detected "
                        f"({runtime['cpu_percent']:.2f}%)"
                    ),
                    details={"cpu_percent": round(runtime["cpu_percent"], 2)},
                    emit_timeline_event=True,
                )

            if runtime["memory_percent"] >= settings.memory_spike_threshold_percent:
                await _record_incident(
                    incident_type="memory_spike",
                    severity="critical",
                    source="runtime_monitor",
                    message=(
                        "Memory pressure detected "
                        f"({runtime['memory_percent']:.2f}% / {runtime['memory_rss_mb']:.2f} MB RSS)"
                    ),
                    details={
                        "memory_percent": round(runtime["memory_percent"], 2),
                        "memory_rss_mb": round(runtime["memory_rss_mb"], 2),
                    },
                    emit_timeline_event=True,
                )

            if queue_depth >= settings.queue_spike_threshold:
                await _record_incident(
                    incident_type="event_queue_spike",
                    severity="warning",
                    source="runtime_monitor",
                    message=f"Event queue depth spike detected ({queue_depth})",
                    details={"event_queue_depth": queue_depth},
                    emit_timeline_event=True,
                )

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("runtime_monitor.error")


# ─── Lifespan ────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global ha_client, _processor_task, _runtime_monitor_task

    # Logging
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )

    # Storage
    await storage.init()
    logger.info("startup.storage_ready")

    # Event processor
    _processor_task = asyncio.create_task(_event_processor())
    _runtime_monitor_task = asyncio.create_task(_runtime_monitor())

    # HA client
    ha_client = HAClient(settings, on_event=_process_ha_event)
    if settings.effective_token:
        try:
            states = await ha_client.fetch_states()
            entity_map.load_states(states)
            logger.info("startup.entities_loaded", count=entity_map.count)
        except Exception:
            logger.exception("startup.entity_load_failed")

        # Fetch registries to enrich entities with integration/area/device info
        try:
            areas = await ha_client.fetch_area_registry()
            entity_map.load_areas(areas)
            devices = await ha_client.fetch_device_registry()
            entity_map.load_device_registry(devices)
            entries = await ha_client.fetch_entity_registry()
            entity_map.load_entity_registry(entries)
            logger.info("startup.registries_loaded")
        except Exception:
            logger.exception("startup.registry_load_failed")

        await ha_client.start()
        logger.info("startup.ha_client_started")

        # Historical backfill — runs as a background task so startup stays fast.
        # Only triggers when backfill_days > 0.
        if settings.backfill_days > 0:
            asyncio.create_task(
                _run_backfill(ha_client, settings.backfill_days),
                name="backfill",
            )
    else:
        logger.warning(
            "startup.no_token",
            hint="Set HA_TOKEN or SUPERVISOR_TOKEN to connect to Home Assistant",
        )

    # Purge manager
    await purge_manager.start()

    yield

    # Shutdown
    await ha_client.stop()
    if _runtime_monitor_task:
        _runtime_monitor_task.cancel()
        try:
            await _runtime_monitor_task
        except asyncio.CancelledError:
            pass
    if _processor_task:
        _processor_task.cancel()
        try:
            await _processor_task
        except asyncio.CancelledError:
            pass
    await purge_manager.stop()
    await storage.close()
    logger.info("shutdown.complete")


# ─── FastAPI app ─────────────────────────────────────────

app = FastAPI(
    title="Tracely",
    version="1.0.0",
    description="Offline causal event tracing for Home Assistant",
    lifespan=lifespan,
)
app.add_middleware(
    _RateLimitMiddleware,
    max_requests=settings.rate_limit_requests,
    window=settings.rate_limit_window_seconds,
)


class _NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    """Ensure index.html is never browser-cached so addon updates take effect immediately."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(_NoCacheHTMLMiddleware)


# ─── API endpoints ───────────────────────────────────────


@app.get("/api/events", response_model=PaginatedEvents)
async def api_get_events(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    entity: str | None = Query(None),
    domain: str | None = Query(None),
    area: str | None = Query(None),
    user_id: str | None = Query(None),
    event_type: str | None = Query(None),
    integration: str | None = Query(None),
    q: str | None = Query(None),
) -> PaginatedEvents:
    # Parse from/to from raw query params (reserved word in Python)
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    # Default "to" to now when only "from" is provided
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()

    # When full-text search query is present, use FTS with all filters combined
    if q:
        offset = (page - 1) * limit
        rows = await storage.search_fts(
            q, limit=limit, offset=offset,
            from_ts=from_ts, to_ts=to_ts,
            entity=entity, domain=domain,
        )
        total = await storage.search_fts_count(
            q, from_ts=from_ts, to_ts=to_ts,
            entity=entity, domain=domain,
        )
        return PaginatedEvents(
            total=total, page=page, limit=limit,
            items=[_to_response(r) for r in rows],
        )

    rows, total = await storage.get_events(
        page=page, limit=limit, entity=entity, domain=domain,
        area=area, user_id=user_id, event_type=event_type,
        integration=integration, from_ts=from_ts, to_ts=to_ts,
    )
    return PaginatedEvents(
        total=total, page=page, limit=limit,
        items=[_to_response(r) for r in rows],
    )


@app.get("/api/events/stream")
async def api_event_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events stream for live event updates."""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    sse_clients.add(queue)

    async def generate() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_clients.discard(queue)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/events/{event_id}")
async def api_get_event(event_id: str) -> dict[str, Any]:
    event = await storage.get_event(event_id)
    if not event:
        return {"error": "not found"}

    root_id = await storage.find_root(event_id)
    tree = await storage.get_tree(root_id)

    max_depth = 0
    if tree:
        depths: dict[str, int] = {}
        for node in tree:
            pid = node.get("parent_id")
            depths[node["id"]] = depths.get(pid, -1) + 1 if pid else 0
        max_depth = max(depths.values()) if depths else 0

    # Compute tree stats
    tree_stats = None
    if tree:
        domain_counts: dict[str, int] = {}
        entity_counts: dict[str, int] = {}
        timestamps: list[int] = []
        inferred = 0
        verified = 0
        for node in tree:
            d = node.get("domain") or "unknown"
            domain_counts[d] = domain_counts.get(d, 0) + 1
            eid = node.get("entity_id")
            if eid:
                entity_counts[eid] = entity_counts.get(eid, 0) + 1
            ts = node.get("timestamp")
            if isinstance(ts, int):
                timestamps.append(ts)
            conf = node.get("confidence", "propagated")
            if conf == "inferred":
                inferred += 1
            else:
                verified += 1
        duration_ms = (max(timestamps) - min(timestamps)) if timestamps else None
        domains = [k for k in domain_counts if k != "unknown"]
        top = max(entity_counts.items(), key=lambda x: x[1]) if entity_counts else None
        tree_stats = {
            "total_nodes": len(tree),
            "domain_breakdown": domain_counts,
            "domain_count": len(domains),
            "duration_ms": duration_ms,
            "inferred_count": inferred,
            "verified_count": verified,
            "top_entity": {"id": top[0], "count": top[1]} if top else None,
            "entity_count": len(entity_counts),
        }

    return {
        "event": _to_response(event),
        "tree": [_to_response(n) for n in tree],
        "tree_depth": max_depth,
        "root_id": root_id,
        "stats": tree_stats,
    }


@app.get("/api/search", response_model=PaginatedEvents)
async def api_search(
    request: Request,
    q: str = "",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity: str | None = Query(None),
    domain: str | None = Query(None),
) -> PaginatedEvents:
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()
    rows = await storage.search_fts(
        q, limit=limit, offset=offset,
        from_ts=from_ts, to_ts=to_ts,
        entity=entity, domain=domain,
    )
    total = await storage.search_fts_count(
        q, from_ts=from_ts, to_ts=to_ts,
        entity=entity, domain=domain,
    )
    return PaginatedEvents(
        total=total, page=1, limit=limit,
        items=[_to_response(r) for r in rows],
    )


@app.get("/api/trees")
async def api_get_trees() -> dict[str, Any]:
    rows = await storage.get_trees()
    return {"items": rows}


@app.get("/api/entities")
async def api_get_entities() -> dict[str, Any]:
    entities = entity_map.all_entities()
    return {
        "items": [
            {
                "entity_id": e.entity_id,
                "friendly_name": e.friendly_name,
                "domain": e.domain,
                "area": e.area,
                "integration": e.integration,
            }
            for e in entities
        ],
    }


@app.get("/api/entities/{entity_id}/history")
async def api_entity_history(
    entity_id: str, limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Get all events for a specific entity — used by tag drill-down."""
    rows = await storage.get_entity_history(entity_id, limit=limit)
    return {
        "entity_id": entity_id,
        "total": len(rows),
        "items": [_to_response(r) for r in rows],
    }


@app.post("/api/events/{event_id}/bookmark")
async def api_bookmark(
    event_id: str, body: BookmarkRequest,
) -> dict[str, bool]:
    ok = await storage.bookmark(event_id, body.note)
    return {"ok": ok}


@app.get("/api/stats")
async def api_stats() -> dict[str, Any]:
    """Comprehensive activity statistics for the stats dashboard."""
    return await storage.get_activity_stats()


# ─── Active Network Discovery Helpers ────────────────────────────────────────

async def _read_arp_table() -> list[dict[str, Any]]:
    """Read network neighbors from all available sources, merged and deduplicated."""
    seen: dict[str, dict[str, Any]] = {}  # keyed by IP

    # Strategy 1: /proc/net/arp
    try:
        proc_arp = Path("/proc/net/arp")
        if proc_arp.exists():
            for line in proc_arp.read_text().splitlines()[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue
                ip, flags, mac, iface = parts[0], parts[2], parts[3], parts[5]
                if mac == "00:00:00:00:00:00":
                    continue
                seen[ip] = {
                    "ip": ip,
                    "mac": mac.upper(),
                    "interface": iface,
                    "reachable": bool(int(flags, 16) & 0x2),
                }
    except Exception:
        pass

    # Strategy 2: ip neigh show — always run, richer data, more entries
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "neigh", "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        for line in stdout.decode().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ip = parts[0]
            if not re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                continue  # skip IPv6
            iface = parts[2] if len(parts) > 2 else ""
            mac = ""
            if "lladdr" in parts:
                idx = parts.index("lladdr")
                if idx + 1 < len(parts):
                    mac = parts[idx + 1].upper()
            if not mac:
                continue
            state = parts[-1] if parts else ""
            reachable = state in ("REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT")
            if ip not in seen:
                seen[ip] = {"ip": ip, "mac": mac, "interface": iface, "reachable": reachable}
            else:
                seen[ip]["reachable"] = reachable
                seen[ip]["interface"] = seen[ip]["interface"] or iface
    except Exception:
        pass

    # Strategy 3: arp -a — only if nothing found yet
    if not seen:
        try:
            proc = await asyncio.create_subprocess_exec(
                "arp", "-a",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            for line in stdout.decode().splitlines():
                ip_m = re.search(r'\((\d+\.\d+\.\d+\.\d+)\)', line)
                mac_m = re.search(r'at\s+([\da-fA-F:]{17})', line)
                iface_m = re.search(r'on\s+(\S+)', line)
                if ip_m and mac_m:
                    ip = ip_m.group(1)
                    if ip not in seen:
                        seen[ip] = {
                            "ip": ip,
                            "mac": mac_m.group(1).upper(),
                            "interface": iface_m.group(1) if iface_m else "",
                            "reachable": True,
                        }
        except Exception:
            pass

    return list(seen.values())


async def _resolve_hostname(ip: str) -> str:
    """Reverse DNS lookup with 1 s timeout; returns empty string on failure."""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip),
            timeout=1.0,
        )
        return result[0]
    except Exception:
        return ""


_INTERNAL_PREFIXES = (
    "172.17.",   # Docker default bridge
    "172.30.",   # HAOS hassio add-on network
    "172.31.",   # HAOS alternate
    "127.",      # loopback
    "169.254.",  # link-local
    "::1",       # IPv6 loopback
    "fe80:",     # IPv6 link-local
)

def _is_internal_ip(ip: str) -> bool:
    return any(ip.startswith(p) for p in _INTERNAL_PREFIXES)

def _ip_base(ip: str) -> str:
    return ".".join(ip.split(".")[:3])


async def _get_local_subnets() -> list[str]:
    """
    Return ALL unique home-LAN /24 bases on this host (e.g. ['192.168.88', '192.168.89']).
    Skips Docker/HAOS internal ranges. Tries multiple strategies and collects all of them.
    """
    subnets: list[str] = []

    def _add(ip: str) -> None:
        if not _is_internal_ip(ip) and re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
            base = _ip_base(ip)
            if base not in subnets:
                subnets.append(base)

    # Strategy 1: ip addr show — most complete, lists every interface
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "addr", "show",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        for line in stdout.decode().splitlines():
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', line)
            if m:
                _add(m.group(1))
    except Exception:
        pass

    # Strategy 2: ip route show (non-default) — catches subnets with no host IP listed
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "show",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        for line in stdout.decode().splitlines():
            # e.g. "192.168.88.0/24 dev eth0 proto kernel  src 192.168.88.5"
            m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', line)
            if m:
                _add(m.group(1))
    except Exception:
        pass

    # Strategy 3: hostname -I
    if not subnets:
        try:
            proc = await asyncio.create_subprocess_exec(
                "hostname", "-I",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            for ip in stdout.decode().split():
                _add(ip)
        except Exception:
            pass

    # Strategy 4: infer from existing ARP entries
    if not subnets:
        try:
            for e in await _read_arp_table():
                _add(e["ip"])
        except Exception:
            pass

    return subnets


async def _ping_sweep(base: str) -> None:
    """Ping .1–.254 concurrently to warm the ARP table (max 48 parallel)."""
    sem = asyncio.Semaphore(48)

    async def _ping(ip: str) -> None:
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "1", "-W", "1", "-q", ip,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=2)
            except Exception:
                pass

    await asyncio.gather(*[_ping(f"{base}.{i}") for i in range(1, 255)])


async def _tcp_probe_subnet(base: str) -> None:
    """Pure-Python TCP connect probe — no ping binary, no NET_RAW needed.
    Opens connections to common ports to detect live hosts and warm the ARP cache.
    """
    PORTS = (80, 443, 22, 8080, 8123, 53, 139, 445, 8888, 7)
    sem = asyncio.Semaphore(64)

    async def _probe(ip: str) -> None:
        async with sem:
            for port in PORTS:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port), timeout=0.5,
                    )
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    return  # one successful connect is enough to warm ARP
                except Exception:
                    pass

    await asyncio.gather(*[_probe(f"{base}.{i}") for i in range(1, 255)])


async def _scan_subnet(base: str) -> None:
    """Run ping sweep AND TCP probe concurrently for maximum ARP warming."""
    await asyncio.gather(
        _ping_sweep(base),
        _tcp_probe_subnet(base),
    )


@app.get("/api/network-devices")
async def api_network_devices(scan: bool = Query(default=False)) -> dict[str, Any]:
    """
    Network device discovery: ARP table merged with HA entity data.
    Internal Docker/HAOS ranges (172.30.x, 172.17.x) are always filtered out.
    Pass ?scan=true to run a ping sweep across ALL detected LAN subnets (~5–15 s).
    """
    # Build lookup maps from HA entity registry
    ha_by_ip: dict[str, dict[str, Any]] = {}
    ha_by_mac: dict[str, dict[str, Any]] = {}
    if entity_map:
        for e in entity_map.all_entities():
            attrs = e.attributes
            ip = (
                attrs.get("ip_address") or attrs.get("ip") or
                attrs.get("host") or attrs.get("ipv4_address") or
                attrs.get("network_address") or ""
            )
            mac = attrs.get("mac_address") or attrs.get("mac") or ""
            ha_data: dict[str, Any] = {
                "entity_id": e.entity_id,
                "friendly_name": e.friendly_name or e.entity_id,
                "state": e.state or "",
                "integration": e.integration or "",
                "area": e.area or "",
            }
            if ip:
                ha_by_ip[ip.strip().lower()] = ha_data
            if mac:
                ha_by_mac[mac.strip().upper()] = ha_data

    # Always detect local subnets; optionally sweep them all
    subnets = await _get_local_subnets()
    if scan and subnets:
        await asyncio.gather(*[_scan_subnet(s) for s in subnets])

    # Read ARP / neighbor table
    arp_entries = await _read_arp_table()

    # Filter out Docker/HAOS internal addresses — only show real LAN devices
    arp_entries = [e for e in arp_entries if not _is_internal_ip(e["ip"])]

    # Resolve hostnames concurrently
    hostnames = await asyncio.gather(*[_resolve_hostname(e["ip"]) for e in arp_entries])

    devices: list[dict[str, Any]] = []
    seen_ips: set[str] = set()
    for entry, hostname in zip(arp_entries, hostnames):
        ip = entry["ip"]
        if ip in seen_ips:
            continue
        seen_ips.add(ip)
        mac = entry["mac"]
        ha = ha_by_ip.get(ip.strip().lower()) or ha_by_mac.get(mac.strip().upper()) or {}
        devices.append({
            "ip": ip,
            "mac": mac,
            "hostname": hostname,
            "interface": entry["interface"],
            "reachable": entry["reachable"],
            "ha_entity_id": ha.get("entity_id", ""),
            "ha_name": ha.get("friendly_name", ""),
            "ha_state": ha.get("state", ""),
            "ha_integration": ha.get("integration", ""),
            "ha_area": ha.get("area", ""),
        })

    # Sort: reachable first, then by subnet, then numerically by last octet
    def _sort_key(d: dict[str, Any]) -> tuple:
        octets = [int(x) for x in d["ip"].split(".") if x.isdigit()]
        return (0 if d["reachable"] else 1, octets)

    devices.sort(key=_sort_key)

    return {
        "devices": devices,
        "total": len(devices),
        "reachable": sum(1 for d in devices if d["reachable"]),
        "ha_matched": sum(1 for d in devices if d["ha_entity_id"]),
        "subnets": subnets,
        "scanned": scan,
    }


@app.get("/api/system")
async def api_system_health() -> dict[str, Any]:
    """System health: network, entities, integrations, areas, offline periods."""
    entities = entity_map.all_entities() if entity_map else []

    unavailable = []
    device_types: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    area_counts: dict[str, int] = {}
    total_devices = 0
    network_info: list[dict[str, Any]] = []

    for e in entities:
        eid = e.entity_id
        integration = e.integration or ""
        domain = e.domain or (eid.split(".")[0] if "." in eid else "")
        attrs = e.attributes
        state = e.state or attrs.get("state", "")

        if integration:
            device_types[integration] = device_types.get(integration, 0) + 1
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        area = e.area or ""
        if area:
            area_counts[area] = area_counts.get(area, 0) + 1
        total_devices += 1

        if state in ("unavailable", "unknown"):
            unavailable.append({
                "entity_id": eid,
                "friendly_name": e.friendly_name or eid,
                "state": state,
                "domain": domain,
                "integration": integration,
                "area": area,
            })

        # Extract network info from relevant entities (broad key coverage)
        ip_addr = (
            attrs.get("ip_address") or attrs.get("ip") or
            attrs.get("host") or attrs.get("ipv4_address") or
            attrs.get("network_address")
        )
        mac_addr = attrs.get("mac_address") or attrs.get("mac")
        ssid = attrs.get("ssid") or attrs.get("wifi_ssid") or attrs.get("network_name")
        signal = attrs.get("signal_strength") or attrs.get("wifi_signal") or attrs.get("rssi")
        hostname = attrs.get("hostname") or attrs.get("host_name") or ""
        if ip_addr or mac_addr or ssid:
            network_info.append({
                "entity_id": eid,
                "friendly_name": e.friendly_name or eid,
                "ip_address": ip_addr,
                "mac_address": mac_addr,
                "hostname": hostname,
                "ssid": ssid,
                "signal_strength": signal,
                "state": state,
                "integration": integration,
            })

    # Compute offline periods from HA start/stop events
    offline_periods = []
    try:
        stops = await storage.get_events(
            page=1, limit=50, event_type="homeassistant_stop",
        )
        starts = await storage.get_events(
            page=1, limit=50, event_type="homeassistant_start",
        )
        stop_rows = stops[0] if stops else []
        start_rows = starts[0] if starts else []
        stop_times = sorted([r["timestamp"] for r in stop_rows], reverse=True)
        start_times = sorted([r["timestamp"] for r in start_rows], reverse=True)
        for st in stop_times:
            resumed = next((s for s in start_times if s > st), None)
            offline_periods.append({
                "stopped_at": st,
                "resumed_at": resumed,
                "duration_ms": (resumed - st) if resumed else None,
            })
    except Exception:
        pass

    recent_incidents: list[dict[str, Any]] = []
    incidents_total = 0
    try:
        incident_rows, incidents_total = await storage.get_incidents(limit=20)
        recent_incidents = [
            _incident_to_response(row).model_dump()
            for row in incident_rows
        ]
    except Exception:
        logger.exception("api.system.incidents_failed")

    # DB stats
    db_size = 0
    event_count = 0
    try:
        db_size = await storage.get_db_size()
        event_count = await storage.get_event_count()
    except Exception:
        pass

    ws_connected = ha_client.connected if ha_client else False
    uptime_s = int(time.time() - _start_time) if _start_time else 0
    runtime = get_runtime_metrics()
    _runtime_status.update(
        {
            "cpu_percent": runtime["cpu_percent"],
            "memory_percent": runtime["memory_percent"],
            "memory_rss_mb": runtime["memory_rss_mb"],
            "event_queue_depth": _event_queue.qsize(),
        },
    )

    return {
        "ws_connected": ws_connected,
        "total_entities": total_devices,
        "unavailable": unavailable,
        "unavailable_count": len(unavailable),
        "device_types": device_types,
        "domain_counts": domain_counts,
        "area_counts": area_counts,
        "network_info": network_info,
        "offline_periods": offline_periods[:20],
        "recent_incidents": recent_incidents,
        "incidents_total": incidents_total,
        "db_size_bytes": db_size,
        "events_count": event_count,
        "uptime_seconds": uptime_s,
        "cpu_percent": round(float(_runtime_status.get("cpu_percent", 0.0)), 2),
        "memory_percent": round(float(_runtime_status.get("memory_percent", 0.0)), 2),
        "memory_rss_mb": round(float(_runtime_status.get("memory_rss_mb", 0.0)), 2),
        "event_queue_depth": int(_runtime_status.get("event_queue_depth", 0)),
        "last_async_block_ms": round(float(_runtime_status.get("last_async_block_ms", 0.0)), 2),
        "ha_restart_count": int(_runtime_status.get("ha_restart_count", 0)),
    }


@app.get("/api/incidents")
async def api_incidents(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    incident_type: str | None = Query(None),
    severity: str | None = Query(None),
) -> dict[str, Any]:
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()

    offset = (page - 1) * limit
    rows, total = await storage.get_incidents(
        limit=limit,
        offset=offset,
        incident_type=incident_type,
        severity=severity,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_incident_to_response(row).model_dump() for row in rows],
    }


@app.get("/api/lifecycle")
async def api_lifecycle(
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Fetch HA lifecycle events (start, stop, restart) from incidents log."""
    rows, total = await storage.get_incidents(
        limit=limit,
        offset=0,
        incident_type="ha_lifecycle",
        severity=None,
    )
    return {
        "total": total,
        "items": [_incident_to_response(row).model_dump() for row in rows],
    }


@app.get("/health", response_model=HealthResponse)
async def api_health() -> HealthResponse:
    client = ha_client or HAClient(settings, on_event=_process_ha_event)
    _runtime_status["event_queue_depth"] = _event_queue.qsize()
    return await get_health(storage, client, runtime_status=_runtime_status)


@app.get("/api/logs")
async def api_logs(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    """
    Expose HA core log diagnostic data.
    
    Returns:
        {
            "available": bool,
            "size_bytes": int,
            "line_count": int,
            "error_count": int,
            "warning_count": int,
            "last_entry_ts": str,
            "lines": [ {"timestamp": str, "level": str, "message": str}, ... ]
        }
    """
    try:
        summary = logs.get_log_summary(max_bytes=500_000)

        if not summary.get("available") and ha_client:
            remote_log = await ha_client.fetch_error_log(max_bytes=500_000)
            if remote_log:
                summary = logs.summarize_log_text(
                    remote_log,
                    source="ha_api_error_log",
                )
        
        if not summary.get("available"):
            return {
                "available": False,
                "error": summary.get("error", "Log file not accessible"),
            }
        
        # Include parsed log lines
        snapshot = summary.get("snapshot")
        lines = (
            logs.parse_log_lines(snapshot, encoded=True, limit=limit)
            if snapshot
            else []
        )
        
        return {
            "available": True,
            "source": summary.get("source", ""),
            "size_bytes": summary.get("size_bytes", 0),
            "line_count": summary.get("line_count", 0),
            "error_count": summary.get("error_count", 0),
            "warning_count": summary.get("warning_count", 0),
            "last_entry_ts": summary.get("last_entry_ts", ""),
            "lines": lines,
        }
    except Exception as e:
        logger.exception("api.logs_error", error=str(e))
        return {
            "available": False,
            "error": str(e),
        }


@app.get("/metrics")
async def api_metrics() -> Response:
    event_count = await storage.get_event_count()
    incidents_total = await storage.get_incident_count()
    db_size = await storage.get_db_size()
    ws_connected = ha_client.connected if ha_client else False
    _runtime_status["event_queue_depth"] = _event_queue.qsize()
    text = get_metrics_text(
        event_count,
        db_size,
        ws_connected,
        runtime_status=_runtime_status,
        incidents_total=incidents_total,
    )
    return Response(content=text, media_type="text/plain")


# ─── Alert / Notification API endpoints ────────────────


@app.get("/api/alerts")
async def api_alerts(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    alert_type: str | None = Query(None),
    severity: str | None = Query(None),
    acknowledged: bool | None = Query(None),
) -> dict[str, Any]:
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()

    offset = (page - 1) * limit
    rows, total = await storage.get_alerts(
        limit=limit,
        offset=offset,
        alert_type=alert_type,
        severity=severity,
        acknowledged=acknowledged,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        details_raw = row.get("details") or "{}"
        try:
            details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        except (json.JSONDecodeError, TypeError):
            details = {}
        items.append(AlertResponse(
            id=row["id"],
            alert_type=row.get("alert_type", ""),
            severity=row.get("severity", "info"),
            title=row.get("title", ""),
            message=row.get("message", ""),
            entity_id=row.get("entity_id"),
            integration=row.get("integration"),
            details=details,
            acknowledged=bool(row.get("acknowledged", 0)),
            timestamp=datetime.fromtimestamp((row.get("timestamp") or 0) / 1000, tz=timezone.utc).isoformat(),
        ).model_dump())

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items,
    }


@app.get("/api/alerts/counts")
async def api_alert_counts() -> dict[str, int]:
    return await storage.get_alert_counts()


@app.get("/api/alerts/stream")
async def api_alert_stream(request: Request) -> StreamingResponse:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
    alert_sse_clients.add(queue)

    async def _gen() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            alert_sse_clients.discard(queue)

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/api/alerts/{alert_id}/acknowledge")
async def api_acknowledge_alert(alert_id: str) -> dict[str, bool]:
    ok = await storage.acknowledge_alert(alert_id)
    return {"ok": ok}


@app.post("/api/alerts/acknowledge-all")
async def api_acknowledge_all_alerts() -> dict[str, bool]:
    count = await storage.acknowledge_all_alerts()
    return {"ok": True, "count": count}


@app.get("/api/devices/offline")
async def api_offline_devices() -> dict[str, Any]:
    devices = device_monitor.get_offline_devices()
    return {"count": len(devices), "devices": devices}


@app.get("/api/supervisor")
async def api_supervisor_info() -> dict[str, Any]:
    """Fetch supervisor-level info and logs for lifecycle/crash detection."""
    if not ha_client:
        return {"available": False, "error": "HA client not connected"}
    result = await ha_client.fetch_supervisor_logs()
    if not result:
        return {"available": False, "error": "Supervisor API not reachable"}
    return result


# ─── KNX API endpoints ──────────────────────────────────


@app.get("/api/knx/telegrams", response_model=PaginatedKnxTelegrams)
async def api_knx_telegrams(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    group_address: str | None = Query(None),
    direction: str | None = Query(None),
    entity: str | None = Query(None),
) -> PaginatedKnxTelegrams:
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()
    offset = (page - 1) * limit
    rows, total = await storage.get_knx_telegrams(
        limit=limit,
        offset=offset,
        group_address=group_address,
        direction=direction,
        entity_id=entity,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return PaginatedKnxTelegrams(
        total=total,
        page=page,
        limit=limit,
        items=[_knx_to_response(r) for r in rows],
    )


@app.get("/api/knx/stream")
async def api_knx_stream(request: Request) -> StreamingResponse:
    """SSE stream for live KNX telegrams."""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    knx_sse_clients.add(queue)

    async def generate() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            knx_sse_clients.discard(queue)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/knx/diagnostics")
async def api_knx_diagnostics() -> dict[str, Any]:
    """Return KNX event ingestion diagnostics for debugging."""
    return {
        "received": _knx_diag["received"],
        "received_by_source": _knx_diag.get("received_by_source", {}),
        "stored": _knx_diag["stored"],
        "dropped_no_ga": _knx_diag["dropped_no_ga"],
        "last_error": _knx_diag["last_error"],
        "recent_raw_events": list(_knx_diag["recent_raw"]),
        "ws_connected": ha_client.connected if ha_client else False,
        "knx_subscription_active": (
            ha_client._knx_sub_id is not None if ha_client else False
        ),
    }


@app.get("/api/knx/group-addresses")
async def api_knx_group_addresses(
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    rows = await storage.get_knx_group_addresses(limit=limit)
    return {
        "total": len(rows),
        "items": [_knx_ga_to_response(r).model_dump() for r in rows],
    }


@app.get("/api/knx/flow/{group_address:path}")
async def api_knx_flow(
    group_address: str,
    around: str | None = Query(None),
    window_ms: int = Query(5000, ge=500, le=60000),
) -> KnxFlowResponse:
    """Return all KNX telegrams and linked HA events in a time window around a GA."""
    around_ts = _parse_timestamp(around) or _epoch_ms()
    knx_rows, ha_rows = await storage.get_knx_flow(
        group_address, around_ts=around_ts, window_ms=window_ms,
    )
    around_iso = datetime.fromtimestamp(around_ts / 1000, tz=timezone.utc).isoformat()
    return KnxFlowResponse(
        group_address=group_address,
        around_ts=around_iso,
        window_ms=window_ms,
        knx_telegrams=[_knx_to_response(r) for r in knx_rows],
        ha_events=[_to_response(r) for r in ha_rows],
    )


@app.get("/api/knx/activity")
async def api_knx_activity(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    entity: str | None = Query(None),
) -> PaginatedEvents:
    """KNX entity state changes from the events table (integration = knx)."""
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()
    rows, total = await storage.get_events(
        page=page, limit=limit, integration="knx",
        entity=entity, from_ts=from_ts, to_ts=to_ts,
    )
    return PaginatedEvents(
        total=total, page=page, limit=limit,
        items=[_to_response(r) for r in rows],
    )


@app.get("/api/protocol/activity")
async def api_protocol_activity(
    request: Request,
    protocol: str = Query(..., description="Protocol name like knx, zigbee, zwave, mqtt"),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    entity: str | None = Query(None),
) -> PaginatedEvents:
    """Events for a specific protocol/integration from the events table."""
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    from_ts = _parse_timestamp(from_str)
    to_ts = _parse_timestamp(to_str)
    if from_ts is not None and to_ts is None:
        to_ts = _epoch_ms()
    rows, total = await storage.get_events(
        page=page, limit=limit, integration=protocol,
        entity=entity, from_ts=from_ts, to_ts=to_ts,
    )
    return PaginatedEvents(
        total=total, page=page, limit=limit,
        items=[_to_response(r) for r in rows],
    )


# ─── Static frontend files ──────────────────────────────

_frontend_dir = settings.frontend_dir
if os.path.isdir(_frontend_dir):
    app.mount(
        "/",
        StaticFiles(directory=_frontend_dir, html=True),
        name="frontend",
    )


# ─── Entry point ─────────────────────────────────────────

def _find_free_port(preferred: int, host: str = "0.0.0.0") -> int:
    """Try the preferred port first, then a range of fallbacks."""
    import socket

    fallback_ports = [preferred] + [p for p in range(8765, 8785) if p != preferred]
    for port in fallback_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                logger.info("server.port_selected", port=port, preferred=preferred)
                return port
        except OSError:
            logger.warning("server.port_in_use", port=port)
    # Absolute last resort: let OS pick any free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        port = s.getsockname()[1]
        logger.warning("server.port_os_assigned", port=port)
        return port


if __name__ == "__main__":
    _port = _find_free_port(settings.port, settings.host)
    config = uvicorn.Config(
        "backend.main:app",
        host=settings.host,
        port=_port,
        log_level=settings.log_level.lower(),
        # Graceful shutdown
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        logger.info("server.shutdown_requested")
    except Exception:
        logger.exception("server.fatal_error")

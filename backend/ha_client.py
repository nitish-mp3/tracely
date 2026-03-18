"""HA WebSocket client — persistent connection with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import structlog

from .config import Settings

logger = structlog.get_logger(__name__)

HA_EVENT_TYPES = [
    "state_changed",
    "call_service",
    "automation_triggered",
    "script_started",
    "script_finished",
    "logbook_entry",
    "homeassistant_start",
    "homeassistant_stop",
    "knx_event",
]


class HAClient:
    """Persistent WebSocket client to Home Assistant with auto-reconnect."""

    def __init__(
        self,
        settings: Settings,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self._ws_url = settings.effective_ha_url
        self._token = settings.effective_token
        self._on_event = on_event
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._connected = False
        self._running = False
        self._msg_id = 0
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._task: asyncio.Task[None] | None = None
        # Tracks the subscription ID for knx/subscribe_telegrams
        self._knx_sub_id: int | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the WebSocket connection loop."""
        self._running = True
        self._task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Stop the connection loop and clean up."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False

    async def fetch_states(self) -> list[dict[str, Any]]:
        """Fetch all entity states via HTTP API."""
        http_url = (
            self._ws_url
            .replace("ws://", "http://")
            .replace("wss://", "https://")
            .replace("/api/websocket", "/api/states")
            .replace("/core/websocket", "/core/api/states")
        )
        headers = {"Authorization": f"Bearer {self._token}"}
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with self._session.get(http_url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()  # type: ignore[no-any-return]
                logger.warning("ha_client.fetch_states_failed", status=resp.status)
                return []
        except Exception:
            logger.exception("ha_client.fetch_states_error")
            return []

    async def _ws_command(self, command: dict[str, Any]) -> dict[str, Any] | None:
        """Send a one-shot WS command and return the result (needs active connection)."""
        if not self._ws or self._ws.closed:
            # Open a temporary session for the command
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()
            try:
                ws = await self._session.ws_connect(self._ws_url)
                msg = await ws.receive_json()
                if msg.get("type") != "auth_required":
                    await ws.close()
                    return None
                await ws.send_json({"type": "auth", "access_token": self._token})
                msg = await ws.receive_json()
                if msg.get("type") != "auth_ok":
                    await ws.close()
                    return None
                await ws.send_json({"id": 1, **command})
                resp = await ws.receive_json()
                await ws.close()
                if resp.get("success"):
                    return resp.get("result")
                return None
            except aiohttp.WSServerHandshakeError as e:
                logger.warning(
                    "ha_client.ws_command_unavailable",
                    command=command.get("type"),
                    status=e.status,
                )
                return None
            except Exception:
                logger.exception("ha_client.ws_command_error", command=command.get("type"))
                return None
        return None

    async def fetch_entity_registry(self) -> list[dict[str, Any]]:
        """Fetch entity registry via WS command."""
        result = await self._ws_command({"type": "config/entity_registry/list"})
        if isinstance(result, list):
            logger.info("ha_client.entity_registry_fetched", count=len(result))
            return result
        return []

    async def fetch_device_registry(self) -> list[dict[str, Any]]:
        """Fetch device registry via WS command."""
        result = await self._ws_command({"type": "config/device_registry/list"})
        if isinstance(result, list):
            logger.info("ha_client.device_registry_fetched", count=len(result))
            return result
        return []

    async def fetch_area_registry(self) -> list[dict[str, Any]]:
        """Fetch area registry via WS command."""
        result = await self._ws_command({"type": "config/area_registry/list"})
        if isinstance(result, list):
            logger.info("ha_client.area_registry_fetched", count=len(result))
            return result
        return []

    def _http_base(self) -> str:
        """Derive HTTP base URL from the WS URL."""
        base = (
            self._ws_url
            .replace("wss://", "https://")
            .replace("ws://", "http://")
        )
        # Strip the websocket path suffix
        for suffix in ("/api/websocket", "/core/websocket"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        # supervisor uses /core prefix for REST
        if base.rstrip("/").endswith("/core"):
            base = base.rstrip("/")[: -len("/core")]
            base += "/core"
        return base.rstrip("/")

    async def fetch_history(
        self,
        days: int = 7,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> int:
        """
        Backfill historical state-change events from HA's history API.

        Fetches up to `days` of history, converts each state entry into
        a synthetic 'state_changed' event dict compatible with the normal
        ingestion pipeline, and calls `on_event` (or self._on_event) for each.

        Returns the count of events queued.
        """
        cb = on_event or self._on_event
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        from datetime import datetime, timedelta, timezone
        import urllib.parse

        base = self._http_base()
        headers = {"Authorization": f"Bearer {self._token}"}
        start_dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
        start_iso = start_dt.isoformat()

        # Use isoformat path segment (percent-encode colon)
        period_path = urllib.parse.quote(start_iso, safe="T+-")

        total = 0
        # ── History API: state_changed events ─────────────────────
        try:
            url = f"{base}/api/history/period/{period_path}?minimal_response=false&no_attributes=false"
            logger.info("ha_client.backfill_history.fetching", url=url, days=days)
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.warning("ha_client.backfill_history.failed", status=resp.status)
                else:
                    entity_histories: list[list[dict[str, Any]]] = await resp.json()
                    for history_list in entity_histories:
                        # Each list is a series of states for one entity
                        prev_state = None
                        for state in history_list:
                            try:
                                entity_id = state.get("entity_id", "")
                                new_state = state.get("state", "")
                                attributes = state.get("attributes", {})
                                last_changed = state.get("last_changed") or state.get("last_updated", "")
                                context = state.get("context", {})

                                synthetic = {
                                    "event_type": "state_changed",
                                    "time_fired": last_changed,
                                    "context": {
                                        "id": context.get("id", ""),
                                        "parent_id": context.get("parent_id"),
                                        "user_id": context.get("user_id"),
                                    },
                                    "data": {
                                        "entity_id": entity_id,
                                        "old_state": {
                                            "entity_id": entity_id,
                                            "state": prev_state,
                                            "attributes": {},
                                        } if prev_state is not None else None,
                                        "new_state": {
                                            "entity_id": entity_id,
                                            "state": new_state,
                                            "attributes": attributes,
                                            "last_changed": last_changed,
                                        },
                                    },
                                    "_backfill": True,
                                }
                                await cb(synthetic)
                                total += 1
                                prev_state = new_state
                            except Exception:
                                logger.exception("ha_client.backfill_history.entry_error")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ha_client.backfill_history.error")

        # ── Logbook API: automation/script/service events ─────────
        try:
            url = f"{base}/api/logbook/{period_path}"
            logger.info("ha_client.backfill_logbook.fetching", url=url)
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.warning("ha_client.backfill_logbook.failed", status=resp.status)
                else:
                    logbook: list[dict[str, Any]] = await resp.json()
                    for entry in logbook:
                        try:
                            when = entry.get("when", "")
                            domain = entry.get("domain", "")
                            name = entry.get("name", "")
                            message = entry.get("message", "")
                            entity_id = entry.get("entity_id", "")
                            context_id = entry.get("context_id", "")
                            context_user_id = entry.get("context_user_id")

                            # Map to a logbook_entry-style event
                            synthetic = {
                                "event_type": "logbook_entry",
                                "time_fired": when,
                                "context": {
                                    "id": context_id or "",
                                    "parent_id": None,
                                    "user_id": context_user_id,
                                },
                                "data": {
                                    "name": name,
                                    "message": message,
                                    "entity_id": entity_id or None,
                                    "domain": domain or None,
                                },
                                "_backfill": True,
                            }
                            await cb(synthetic)
                            total += 1
                        except Exception:
                            logger.exception("ha_client.backfill_logbook.entry_error")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ha_client.backfill_logbook.error")

        logger.info("ha_client.backfill_complete", total_queued=total)
        return total

    # ─── Connection loop ───────────────────────────────────

    async def _connection_loop(self) -> None:
        """Main connection loop with exponential backoff reconnect."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except aiohttp.WSServerHandshakeError as e:
                logger.warning("ha_client.connection_unavailable", status=e.status)
            except Exception:
                logger.exception("ha_client.connection_error")

            if not self._running:
                break

            self._connected = False
            logger.info(
                "ha_client.reconnecting", delay=self._reconnect_delay,
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay,
            )

    async def _connect_and_listen(self) -> None:
        """Connect to HA WS, authenticate, subscribe, and listen."""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        logger.info("ha_client.connecting", url=self._ws_url)
        self._ws = await self._session.ws_connect(self._ws_url)
        self._msg_id = 0

        # Wait for auth_required
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_required":
            logger.error("ha_client.unexpected_message", msg=msg)
            return

        # Authenticate
        await self._ws.send_json({
            "type": "auth",
            "access_token": self._token,
        })
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_ok":
            logger.error("ha_client.auth_failed", msg=msg)
            return

        logger.info("ha_client.authenticated")
        self._connected = True
        self._reconnect_delay = 1.0  # reset backoff on success

        # Subscribe to event types
        for event_type in HA_EVENT_TYPES:
            self._msg_id += 1
            subscribe_id = self._msg_id
            await self._ws.send_json({
                "id": subscribe_id,
                "type": "subscribe_events",
                "event_type": event_type,
            })
            resp = await self._await_result(subscribe_id)
            if not resp or not resp.get("success", False):
                logger.warning(
                    "ha_client.subscribe_failed",
                    event_type=event_type,
                    resp=resp,
                )

        logger.info("ha_client.subscribed", event_types=HA_EVENT_TYPES)

        # Subscribe to the KNX internal telegram stream (gives ALL telegrams,
        # same source as the HA Group Monitor UI — no fire_event:true needed).
        self._msg_id += 1
        self._knx_sub_id = self._msg_id
        await self._ws.send_json({
            "id": self._knx_sub_id,
            "type": "knx/subscribe_telegrams",
        })
        resp = await self._await_result(self._knx_sub_id)
        if resp and resp.get("success"):
            logger.info("ha_client.knx_telegrams_subscribed", sub_id=self._knx_sub_id)
        else:
            logger.warning("ha_client.knx_telegrams_subscribe_failed", resp=resp)
            self._knx_sub_id = None

        # Listen for events
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._handle_ws_payload(data)
                except json.JSONDecodeError:
                    logger.warning("ha_client.invalid_json")
                except Exception:
                    logger.exception("ha_client.event_handler_error")
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                break

        self._connected = False

    async def _await_result(self, expected_id: int) -> dict[str, Any] | None:
        """Wait for a matching WS result while safely handling interleaved events."""
        if not self._ws:
            return None

        while True:
            payload = await self._ws.receive_json()
            payload_type = payload.get("type")

            if payload_type == "result" and payload.get("id") == expected_id:
                return payload

            if payload_type == "event":
                await self._handle_ws_payload(payload)
                continue

            logger.debug(
                "ha_client.unexpected_during_result_wait",
                expected_id=expected_id,
                payload=payload,
            )

    async def _handle_ws_payload(self, data: dict[str, Any]) -> None:
        """Handle a single parsed WS payload."""
        if data.get("type") != "event":
            return

        event = data.get("event", {})
        if self._knx_sub_id is not None and data.get("id") == self._knx_sub_id:
            synthetic: dict[str, Any] = {
                "event_type": "knx.telegram",
                "data": event,
                "time_fired": event.get("timestamp"),
                "context": {},
            }
            await self._on_event(synthetic)
            return

        await self._on_event(event)

"""Device offline/unavailable monitoring with alert generation.

Watches state_changed events for devices going unavailable/offline and
generates alerts — single device warnings and multi-device critical alerts.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from .config import Settings
from .entity_map import EntityMap, EntityInfo
from .tree_builder import TreeBuilder

logger = structlog.get_logger(__name__)

# Integrations considered critical for offline monitoring
MONITORED_INTEGRATIONS = frozenset({
    "zha", "mqtt", "zigbee2mqtt", "knx", "wiz", "hue", "esphome",
    "shelly", "tasmota", "deconz", "homekit",
})

# States that mean the device is offline/unavailable
OFFLINE_STATES = frozenset({"unavailable", "unknown", "offline", "dead"})

# How long a device must be offline before we alert (seconds)
OFFLINE_GRACE_PERIOD_S = 30

# Window for multi-device correlation (seconds)
MULTI_DEVICE_WINDOW_S = 120

# Minimum devices going offline in the window to trigger critical alert
MULTI_DEVICE_THRESHOLD = 3

# Cooldown per entity to avoid alert spam (seconds)
ENTITY_ALERT_COOLDOWN_S = 300


class DeviceMonitor:
    """Monitors entity state changes and generates offline/online alerts."""

    def __init__(self, settings: Settings, entity_map: EntityMap) -> None:
        self._settings = settings
        self._entity_map = entity_map
        # entity_id -> timestamp when it went offline
        self._offline_entities: dict[str, float] = {}
        # entity_id -> last alert timestamp (cooldown tracking)
        self._last_alert_ts: dict[str, float] = {}
        # Recent offline events for multi-device correlation
        self._recent_offline: list[dict[str, Any]] = []

    def process_state_change(
        self, entity_id: str, old_state: str | None, new_state: str, event_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process a state change and return any alerts to emit.

        Returns a list of alert dicts ready for storage.insert_alert().
        """
        alerts: list[dict[str, Any]] = []
        now = time.time()
        info = self._entity_map.resolve(entity_id)

        # Only monitor tracked integrations (or entities that look like devices)
        if not self._is_monitored(entity_id, info):
            return alerts

        was_offline = old_state in OFFLINE_STATES if old_state else False
        is_offline = new_state in OFFLINE_STATES

        if is_offline and not was_offline:
            # Device went offline
            self._offline_entities[entity_id] = now
            self._recent_offline.append({
                "entity_id": entity_id,
                "timestamp": now,
                "integration": info.integration if info else "",
                "friendly_name": info.friendly_name if info else entity_id,
            })
            # Prune old entries from recent list
            self._recent_offline = [
                e for e in self._recent_offline
                if now - e["timestamp"] < MULTI_DEVICE_WINDOW_S
            ]

            # Single device alert (with cooldown)
            if self._can_alert(entity_id, now):
                friendly = info.friendly_name if info else entity_id
                integration = info.integration if info else self._guess_integration(entity_id)
                alert = self._build_alert(
                    alert_type="device_offline",
                    severity="warning",
                    title=f"{friendly} went offline",
                    message=f"{friendly} ({entity_id}) is now unavailable",
                    entity_id=entity_id,
                    integration=integration,
                    details={
                        "entity_id": entity_id,
                        "friendly_name": friendly,
                        "old_state": old_state,
                        "new_state": new_state,
                        "integration": integration,
                        "area": info.area if info else "",
                    },
                )
                alerts.append(alert)
                self._last_alert_ts[entity_id] = now

            # Check for multi-device offline (critical)
            recent_unique = {e["entity_id"] for e in self._recent_offline}
            if len(recent_unique) >= MULTI_DEVICE_THRESHOLD:
                cooldown_key = "__multi_device__"
                if self._can_alert(cooldown_key, now):
                    affected = [e for e in self._recent_offline if e["entity_id"] in recent_unique]
                    integrations = list({e["integration"] for e in affected if e["integration"]})
                    names = [e["friendly_name"] for e in affected[:10]]
                    alert = self._build_alert(
                        alert_type="multi_device_offline",
                        severity="critical",
                        title=f"{len(recent_unique)} devices went offline",
                        message=f"Multiple devices went unavailable within {MULTI_DEVICE_WINDOW_S}s: {', '.join(names[:5])}{'...' if len(names) > 5 else ''}",
                        entity_id=None,
                        integration=integrations[0] if len(integrations) == 1 else None,
                        details={
                            "affected_count": len(recent_unique),
                            "affected_entities": list(recent_unique),
                            "affected_names": names,
                            "integrations": integrations,
                            "window_seconds": MULTI_DEVICE_WINDOW_S,
                        },
                    )
                    alerts.append(alert)
                    self._last_alert_ts[cooldown_key] = now

        elif was_offline and not is_offline:
            # Device came back online
            offline_since = self._offline_entities.pop(entity_id, None)
            if offline_since and self._can_alert(f"{entity_id}_online", now):
                friendly = info.friendly_name if info else entity_id
                integration = info.integration if info else self._guess_integration(entity_id)
                duration_s = now - offline_since
                alert = self._build_alert(
                    alert_type="device_online",
                    severity="info",
                    title=f"{friendly} back online",
                    message=f"{friendly} ({entity_id}) recovered after {self._format_duration(duration_s)}",
                    entity_id=entity_id,
                    integration=integration,
                    details={
                        "entity_id": entity_id,
                        "friendly_name": friendly,
                        "offline_duration_s": round(duration_s, 1),
                        "integration": integration,
                    },
                )
                alerts.append(alert)
                self._last_alert_ts[f"{entity_id}_online"] = now

        return alerts

    def get_offline_devices(self) -> list[dict[str, Any]]:
        """Return currently tracked offline devices."""
        now = time.time()
        result = []
        for entity_id, since in self._offline_entities.items():
            info = self._entity_map.resolve(entity_id)
            result.append({
                "entity_id": entity_id,
                "friendly_name": info.friendly_name if info else entity_id,
                "integration": info.integration if info else "",
                "area": info.area if info else "",
                "offline_since": since,
                "offline_duration_s": round(now - since, 1),
            })
        result.sort(key=lambda d: d["offline_since"])
        return result

    def _is_monitored(self, entity_id: str, info: EntityInfo | None) -> bool:
        """Check if this entity should be monitored for offline alerts."""
        # Always monitor entities from tracked integrations
        if info and info.integration and info.integration.lower() in MONITORED_INTEGRATIONS:
            return True
        # Heuristic: check entity_id for integration hints
        eid = entity_id.lower()
        for intg in MONITORED_INTEGRATIONS:
            if intg in eid:
                return True
        # Monitor device_tracker, binary_sensor, light, switch, sensor domains
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if domain in {"light", "switch", "binary_sensor", "sensor", "climate",
                      "cover", "fan", "lock", "device_tracker"}:
            if info and info.integration:
                return True
        return False

    def _can_alert(self, key: str, now: float) -> bool:
        last = self._last_alert_ts.get(key, 0)
        return (now - last) >= ENTITY_ALERT_COOLDOWN_S

    def _build_alert(
        self,
        *,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        entity_id: str | None,
        integration: str | None,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp_ms = int(time.time() * 1000)
        alert_id = TreeBuilder.generate_event_id(
            f"alert:{alert_type}:{entity_id or 'multi'}:{timestamp_ms}",
        )
        return {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "entity_id": entity_id,
            "integration": integration,
            "details": json.dumps(details, default=str),
            "timestamp": timestamp_ms,
        }

    @staticmethod
    def _guess_integration(entity_id: str) -> str:
        eid = entity_id.lower()
        for name in ("knx", "zha", "mqtt", "wiz", "hue", "esphome", "shelly", "deconz"):
            if name in eid:
                return name
        return ""

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        mins = int(seconds / 60)
        if mins < 60:
            return f"{mins}m {int(seconds % 60)}s"
        hrs = int(mins / 60)
        return f"{hrs}h {mins % 60}m"

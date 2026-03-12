"""Event normalization — generate human-readable labels for HA events."""

from __future__ import annotations

import structlog

from .entity_map import EntityMap

logger = structlog.get_logger(__name__)


class Normalizer:
    """Generate human-readable names for HA events using entity map context."""

    def __init__(self, entity_map: EntityMap) -> None:
        self._em = entity_map

    def label(
        self,
        event_type: str,
        data: dict,
        entity_id: str | None = None,
    ) -> str:
        """Generate a human-friendly label for an event."""
        match event_type:
            case "state_changed":
                return self._label_state_changed(data, entity_id)
            case "call_service":
                return self._label_call_service(data, entity_id)
            case "automation_triggered":
                return self._label_automation_triggered(data, entity_id)
            case "script_started":
                return self._label_script(data, entity_id, started=True)
            case "script_finished":
                return self._label_script(data, entity_id, started=False)
            case "logbook_entry":
                return self._label_logbook(data)
            case "homeassistant_start":
                return "Home Assistant started"
            case "homeassistant_stop":
                return "Home Assistant stopped"
            case "knx_event":
                return self._label_knx_event(data)
            case _:
                return f"{event_type} event"

    def extract_entity_id(self, event_type: str, data: dict) -> str | None:
        """Extract entity_id from event data based on type."""
        match event_type:
            case "state_changed":
                return data.get("entity_id")
            case "call_service":
                svc_data = data.get("service_data", {})
                eid = svc_data.get("entity_id")
                if isinstance(eid, list):
                    return eid[0] if eid else None
                return eid
            case "automation_triggered":
                return data.get("entity_id")
            case "script_started" | "script_finished":
                return data.get("entity_id")
            case "knx_event":
                ga = data.get("destination_address") or data.get("group_address", "")
                return f"knx.{ga.replace('/', '_')}" if ga else None
            case _:
                return data.get("entity_id")

    def extract_domain_service(
        self, event_type: str, data: dict,
    ) -> tuple[str | None, str | None]:
        """Extract domain and service from event data."""
        if event_type == "call_service":
            return data.get("domain"), data.get("service")
        entity_id = self.extract_entity_id(event_type, data)
        domain = entity_id.split(".")[0] if entity_id and "." in entity_id else None
        return domain, None

    # ─── Private labellers ─────────────────────────────────

    def _label_state_changed(self, data: dict, entity_id: str | None) -> str:
        friendly = self._em.get_friendly_name(entity_id)
        new_state = data.get("new_state") or {}
        old_state = data.get("old_state") or {}

        new_val = new_state.get("state", "unknown") if new_state else "unavailable"
        old_val = old_state.get("state", "unknown") if old_state else "unavailable"

        if new_val in (
            "on", "off", "home", "not_home",
            "open", "closed", "locked", "unlocked",
        ):
            return f"{friendly} changed to {new_val}"
        if old_val != new_val:
            return f"{friendly} changed from {old_val} to {new_val}"
        return f"{friendly} updated"

    def _label_call_service(self, data: dict, entity_id: str | None) -> str:
        domain = data.get("domain", "")
        service = data.get("service", "")
        friendly = self._em.get_friendly_name(entity_id)
        service_label = service.replace("_", " ")

        if entity_id and friendly != entity_id:
            return f"{friendly} — {service_label}"
        if entity_id:
            return f"{domain}.{service} on {entity_id}"
        return f"{domain}.{service} called"

    def _label_automation_triggered(
        self, data: dict, entity_id: str | None,
    ) -> str:
        friendly = self._em.get_friendly_name(entity_id)
        source = data.get("source", "")
        if source:
            return f"Automation '{friendly}' triggered by {source}"
        return f"Automation '{friendly}' triggered"

    def _label_script(
        self, data: dict, entity_id: str | None, *, started: bool,
    ) -> str:
        friendly = self._em.get_friendly_name(entity_id)
        action = "started" if started else "finished"
        return f"Script '{friendly}' {action}"

    def _label_logbook(self, data: dict) -> str:
        name = data.get("name", "")
        message = data.get("message", "")
        if name and message:
            return f"{name}: {message}"
        return name or message or "Logbook entry"

    def _label_knx_event(self, data: dict) -> str:
        ga   = data.get("destination_address") or data.get("group_address", "?")
        src  = data.get("source_address", "")
        ttype = data.get("telegramtype", "")
        direction = data.get("direction", "")
        value = data.get("value")

        # Human-readable telegram type
        tmap = {
            "GroupValueWrite":    "Write",
            "GroupValueRead":     "Read",
            "GroupValueResponse": "Response",
        }
        tshort = tmap.get(ttype, ttype)

        # Direction arrow
        arrow = "←" if direction == "Incoming" else "→"

        # Value label
        if value is None:
            val_label = ""
        elif isinstance(value, bool):
            val_label = ": ON" if value else ": OFF"
        elif isinstance(value, (int, float)):
            val_label = f": {value}"
        else:
            val_label = f": {value!s}"

        if src and direction == "Incoming":
            return f"KNX {ga} {arrow} {tshort}{val_label}  (from {src})"
        return f"KNX {ga} {arrow} {tshort}{val_label}"

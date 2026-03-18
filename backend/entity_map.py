"""In-memory entity/area/integration cache, refreshed from HA."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EntityInfo:
    """Cached info about a single HA entity."""

    entity_id: str
    friendly_name: str = ""
    domain: str = ""
    area: str = ""
    integration: str = ""
    device_id: str = ""
    state: str = ""
    attributes: dict = field(default_factory=dict)


class EntityMap:
    """Thread-safe in-memory entity cache with area/device enrichment."""

    def __init__(self) -> None:
        self._entities: dict[str, EntityInfo] = {}
        self._areas: dict[str, str] = {}  # area_id → area_name
        self._device_map: dict[str, dict] = {}

    def clear(self) -> None:
        """Clear all cached entities and registries before a full refresh."""
        self._entities.clear()
        self._areas.clear()
        self._device_map.clear()

    def resolve(self, entity_id: str | None) -> EntityInfo | None:
        if not entity_id:
            return None
        return self._entities.get(entity_id)

    def get_friendly_name(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        info = self._entities.get(entity_id)
        return info.friendly_name if info else entity_id

    def get_domain(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        return entity_id.split(".")[0] if "." in entity_id else ""

    def get_area(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        info = self._entities.get(entity_id)
        return info.area if info else ""

    def get_integration(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        info = self._entities.get(entity_id)
        return info.integration if info else ""

    # ─── Bulk loaders ──────────────────────────────────────

    def load_states(self, states: list[dict]) -> None:
        """Load entity info from HA /api/states response."""
        count = 0
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id:
                continue
            attrs = state.get("attributes", {})
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            self._entities[entity_id] = EntityInfo(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name", entity_id),
                domain=domain,
                state=state.get("state", ""),
                attributes=attrs,
            )
            count += 1
        logger.info("entity_map.loaded_states", count=count)

    def load_areas(self, areas: list[dict]) -> None:
        """Load area registry from HA."""
        for area in areas:
            area_id = area.get("area_id", "")
            name = area.get("name", "")
            if area_id:
                self._areas[area_id] = name
        logger.info("entity_map.loaded_areas", count=len(self._areas))

    def load_device_registry(self, devices: list[dict]) -> None:
        """Store device info for later entity enrichment."""
        for dev in devices:
            dev_id = dev.get("id", "")
            if dev_id:
                self._device_map[dev_id] = dev

    def load_entity_registry(self, entries: list[dict]) -> None:
        """Enrich entities with registry info (device_id, area, integration)."""
        for entry in entries:
            entity_id = entry.get("entity_id", "")
            if entity_id not in self._entities:
                continue
            info = self._entities[entity_id]
            platform = entry.get("platform", "")
            if platform:
                info.integration = platform
            device_id = entry.get("device_id", "")
            if device_id:
                info.device_id = device_id
                device = self._device_map.get(device_id, {})
                area_id = entry.get("area_id") or device.get("area_id", "")
                if area_id and area_id in self._areas:
                    info.area = self._areas[area_id]

    # ─── Incremental update ────────────────────────────────

    def update_entity(self, entity_id: str, new_state: dict) -> None:
        """Update a single entity from a state_changed event."""
        attrs = new_state.get("attributes", {})
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        existing = self._entities.get(entity_id)
        if existing:
            existing.friendly_name = attrs.get(
                "friendly_name", existing.friendly_name,
            )
            existing.state = new_state.get("state", existing.state)
            existing.attributes = attrs
        else:
            self._entities[entity_id] = EntityInfo(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name", entity_id),
                domain=domain,
                state=new_state.get("state", ""),
                attributes=attrs,
            )

    # ─── Accessors ─────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._entities)

    def all_entities(self) -> list[EntityInfo]:
        return list(self._entities.values())

    def find_entity_by_attribute(self, integration: str, value: str) -> str | None:
        """Return the first entity_id whose attributes contain *value* anywhere.

        Used to match KNX group addresses to HA entities by scanning attribute values.
        Works across any KNX attribute key (group_address_switch, group_address_state, etc.).
        """
        for info in self._entities.values():
            if info.integration and info.integration != integration:
                continue
            for attr_val in info.attributes.values():
                if isinstance(attr_val, str) and attr_val == value:
                    return info.entity_id
                if isinstance(attr_val, list) and value in attr_val:
                    return info.entity_id
        return None

    def find_knx_entity_by_source(self, source_address: str) -> str | None:
        """Return entity_id whose KNX physical/individual address matches *source_address*.

        KNX entities expose their physical bus address as the "source" attribute
        (e.g. "1.1.17").  This is a reliable 1:1 match: one physical device →
        one entity.  Used as the fallback when the GA-based attribute scan fails.
        """
        if not source_address:
            return None
        for info in self._entities.values():
            if info.integration and info.integration != "knx":
                continue
            src = info.attributes.get("source")
            if isinstance(src, str) and src == source_address:
                return info.entity_id
        return None

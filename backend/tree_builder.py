"""Parent/child linking + heuristic linker for events without parent_id."""

from __future__ import annotations

import hashlib
import time

import structlog

from .config import Settings
from .models import EventRecord
from .storage import Storage

logger = structlog.get_logger(__name__)


class TreeBuilder:
    """Links events into causal trees using context propagation or heuristics."""

    def __init__(self, storage: Storage, settings: Settings) -> None:
        self._storage = storage
        self._window_ms = settings.infer_window_ms

    async def link(self, event: EventRecord) -> None:
        """Attempt to link an event to its parent via heuristics when parent_id is NULL."""
        if event.parent_id:
            return  # already linked by context propagation

        parent_id = await self._infer_parent(event)
        if parent_id:
            await self._storage.update_parent(
                event.id, parent_id, confidence="inferred",
            )
            logger.debug(
                "tree_builder.inferred_parent",
                event_id=event.id,
                parent_id=parent_id,
            )

    async def _infer_parent(self, event: EventRecord) -> str | None:
        """Try each heuristic rule in priority order; return first match."""
        ts = event.timestamp

        # Rule 1: context.id match is implicit — HA sets parent_id when propagating

        # Rule 2: Recent call_service on same entity
        if event.entity_id:
            match = await self._storage.find_recent_call_service(
                event.entity_id, ts, self._window_ms,
            )
            if match and match["id"] != event.id:
                return match["id"]

        # Rule 3: Same user_id + same entity
        if event.user_id and event.entity_id:
            match = await self._storage.find_recent_by_user_entity(
                event.user_id, event.entity_id, ts, self._window_ms,
            )
            if match and match["id"] != event.id:
                return match["id"]

        # Rule 4: Same entity, most recent event
        if event.entity_id:
            matches = await self._storage.find_recent_by_entity(
                event.entity_id, ts, self._window_ms,
            )
            for m in matches:
                if m["id"] != event.id:
                    return m["id"]

        # Rule 5: No match — remains a synthetic root
        return None

    async def build_tree_summary(self, root_id: str) -> dict:
        """Build a summary of a tree for the trees index."""
        tree_nodes = await self._storage.get_tree(root_id)
        if not tree_nodes:
            return {}

        domains = list(
            {n.get("domain", "") for n in tree_nodes if n.get("domain")},
        )
        entities = [
            n.get("entity_id", "") for n in tree_nodes if n.get("entity_id")
        ]
        timestamps = [n["timestamp"] for n in tree_nodes]

        top_entity = max(set(entities), key=entities.count) if entities else ""
        duration_ms = (
            (max(timestamps) - min(timestamps)) if len(timestamps) > 1 else 0
        )

        return {
            "event_count": len(tree_nodes),
            "duration_ms": duration_ms,
            "domains": domains,
            "top_entity": top_entity,
        }

    @staticmethod
    def generate_event_id(raw_json: str) -> str:
        """Generate a deterministic event ID from raw JSON + timestamp."""
        data = f"{raw_json}{time.time_ns()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

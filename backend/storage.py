"""SQLite storage layer — WAL mode, async, parameterized queries, FTS5."""

from __future__ import annotations

import os
import time
import zlib
from typing import Any

import aiosqlite
import structlog

from .config import Settings
from .models import EntityRecord, EventRecord

logger = structlog.get_logger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
  id             TEXT    PRIMARY KEY,
  parent_id      TEXT,
  event_type     TEXT    NOT NULL,
  domain         TEXT,
  service        TEXT,
  entity_id      TEXT,
  payload        TEXT    NOT NULL,
  name           TEXT,
  integration    TEXT,
  area           TEXT,
  timestamp      INTEGER NOT NULL,
  user_id        TEXT,
  important      INTEGER DEFAULT 0,
  confidence     TEXT    DEFAULT 'propagated',
  generated_root INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_parent     ON events(parent_id);
CREATE INDEX IF NOT EXISTS idx_time       ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_entity     ON events(entity_id);
CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type);

CREATE TABLE IF NOT EXISTS entities (
  entity_id     TEXT PRIMARY KEY,
  friendly_name TEXT,
  device_id     TEXT,
  area          TEXT,
  integration   TEXT,
  attributes    TEXT,
  last_seen     INTEGER
);

CREATE TABLE IF NOT EXISTS trees (
  tree_id       TEXT PRIMARY KEY,
  root_event_id TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  summary       TEXT
);

CREATE TABLE IF NOT EXISTS raw_events (
  event_id  TEXT PRIMARY KEY,
  raw_json  BLOB
);

CREATE TABLE IF NOT EXISTS config (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS knx_telegrams (
  id              TEXT    PRIMARY KEY,
  timestamp       INTEGER NOT NULL,
  group_address   TEXT    NOT NULL,
  direction       TEXT    NOT NULL,   -- 'Incoming' | 'Outgoing'
  source_address  TEXT,
  telegram_type   TEXT    NOT NULL,   -- GroupValueWrite | GroupValueRead | GroupValueResponse
  raw_data        TEXT,               -- hex string
  decoded_value   TEXT,               -- JSON-encoded value (null if undecodable)
  dpt_type        TEXT,               -- e.g. "1.001"
  linked_entity_id TEXT,              -- HA entity that maps to this GA
  linked_event_id  TEXT,              -- FK to events.id (state_changed or call_service)
  context_id      TEXT                -- HA context.id from knx_event
);
CREATE INDEX IF NOT EXISTS idx_knx_time    ON knx_telegrams(timestamp);
CREATE INDEX IF NOT EXISTS idx_knx_ga      ON knx_telegrams(group_address);
CREATE INDEX IF NOT EXISTS idx_knx_entity  ON knx_telegrams(linked_entity_id);
CREATE INDEX IF NOT EXISTS idx_knx_ctx     ON knx_telegrams(context_id);

CREATE TABLE IF NOT EXISTS knx_group_addresses (
  group_address   TEXT    PRIMARY KEY,
  friendly_name   TEXT,
  dpt_type        TEXT,
  linked_entities TEXT,   -- JSON array of entity_ids
  last_seen       INTEGER,
  total_writes    INTEGER DEFAULT 0,
  total_reads     INTEGER DEFAULT 0,
  total_responses INTEGER DEFAULT 0,
  last_value      TEXT    -- JSON-encoded last decoded value
);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  event_id,
  name,
  entity_id,
  payload
);
"""

CONFIG_DEFAULTS = {
    "purge_keep_days": "30",
    "aggregate_threshold_per_sec": "5",
    "infer_window_ms": "3000",
}


class Storage:
    """Async SQLite storage with WAL mode, FTS5 search, and CTE tree queries."""

    def __init__(self, settings: Settings) -> None:
        self._db_path = settings.db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open database, set pragmas, create schema."""
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        # FTS must be created separately (not inside executescript with other DDL)
        await self._db.execute(FTS_SQL)
        for key, value in CONFIG_DEFAULTS.items():
            await self._db.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self._db.commit()
        logger.info("storage.initialized", db_path=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ─── Events ────────────────────────────────────────────

    async def insert_event(self, event: EventRecord) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR IGNORE INTO events
               (id, parent_id, event_type, domain, service, entity_id,
                payload, name, integration, area, timestamp, user_id,
                important, confidence, generated_root)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.id, event.parent_id, event.event_type,
                event.domain, event.service, event.entity_id,
                event.payload, event.name, event.integration,
                event.area, event.timestamp, event.user_id,
                event.important, event.confidence, event.generated_root,
            ),
        )
        # FTS index
        await self._db.execute(
            "INSERT OR IGNORE INTO events_fts (event_id, name, entity_id, payload) VALUES (?,?,?,?)",
            (event.id, event.name or "", event.entity_id or "", event.payload),
        )
        # Compressed raw archive
        raw_bytes = zlib.compress(event.payload.encode("utf-8"))
        await self._db.execute(
            "INSERT OR IGNORE INTO raw_events (event_id, raw_json) VALUES (?,?)",
            (event.id, raw_bytes),
        )
        await self._db.commit()

    async def insert_events_batch(self, events: list[EventRecord]) -> None:
        assert self._db is not None
        for event in events:
            await self._db.execute(
                """INSERT OR IGNORE INTO events
                   (id, parent_id, event_type, domain, service, entity_id,
                    payload, name, integration, area, timestamp, user_id,
                    important, confidence, generated_root)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.id, event.parent_id, event.event_type,
                    event.domain, event.service, event.entity_id,
                    event.payload, event.name, event.integration,
                    event.area, event.timestamp, event.user_id,
                    event.important, event.confidence, event.generated_root,
                ),
            )
            await self._db.execute(
                "INSERT OR IGNORE INTO events_fts (event_id, name, entity_id, payload) VALUES (?,?,?,?)",
                (event.id, event.name or "", event.entity_id or "", event.payload),
            )
            raw_bytes = zlib.compress(event.payload.encode("utf-8"))
            await self._db.execute(
                "INSERT OR IGNORE INTO raw_events (event_id, raw_json) VALUES (?,?)",
                (event.id, raw_bytes),
            )
        await self._db.commit()

    async def get_events(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        entity: str | None = None,
        domain: str | None = None,
        area: str | None = None,
        user_id: str | None = None,
        event_type: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
        integration: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated event query with optional filters."""
        assert self._db is not None
        conditions: list[str] = []
        params: list[Any] = []

        if entity:
            conditions.append("entity_id = ?")
            params.append(entity)
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if area:
            conditions.append("area = ?")
            params.append(area)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if integration:
            conditions.append("integration = ?")
            params.append(integration)
        if from_ts is not None:
            conditions.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            conditions.append("timestamp <= ?")
            params.append(to_ts)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        count_rows = await self._db.execute_fetchall(
            f"SELECT COUNT(*) as cnt FROM events{where}", params,
        )
        total = count_rows[0]["cnt"] if count_rows else 0

        offset = (page - 1) * limit
        rows = await self._db.execute_fetchall(
            f"SELECT * FROM events{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [dict(r) for r in rows], total

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM events WHERE id = ?", (event_id,),
        )
        return dict(rows[0]) if rows else None

    # ─── Tree queries ──────────────────────────────────────

    async def get_tree(self, root_id: str) -> list[dict[str, Any]]:
        """Recursive CTE to fetch full causal tree from a root."""
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """WITH RECURSIVE tree(id, parent_id, depth) AS (
                 SELECT e.id, e.parent_id, 0
                   FROM events e WHERE e.id = ?
                 UNION ALL
                 SELECT c.id, c.parent_id, tree.depth + 1
                   FROM events c
                   JOIN tree ON c.parent_id = tree.id
                  WHERE tree.depth < 50
               )
               SELECT e.* FROM events e
               JOIN tree ON e.id = tree.id
               ORDER BY e.timestamp""",
            (root_id,),
        )
        return [dict(r) for r in rows]

    async def find_root(self, event_id: str) -> str:
        """Walk up parent_id chain to find the tree root."""
        assert self._db is not None
        current = event_id
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            rows = await self._db.execute_fetchall(
                "SELECT parent_id FROM events WHERE id = ?", (current,),
            )
            if not rows or rows[0]["parent_id"] is None:
                return current
            current = rows[0]["parent_id"]
        return current or event_id

    # ─── FTS search ────────────────────────────────────────

    @staticmethod
    def _fts_safe(query: str) -> str:
        """Strip FTS5 special characters so raw user input can't break the query."""
        import re
        # Remove FTS5 operators that could cause syntax errors
        cleaned = re.sub(r'["*^()\-]', ' ', query)
        # Collapse whitespace
        return ' '.join(cleaned.split())

    async def search_fts(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        from_ts: int | None = None,
        to_ts: int | None = None,
        entity: str | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        assert self._db is not None
        safe_query = self._fts_safe(query)
        if not safe_query:
            return []
        # Get matching event IDs from FTS, then apply column filters
        conditions: list[str] = ["e.id IN (SELECT event_id FROM events_fts WHERE events_fts MATCH ?)"]
        params: list[Any] = [safe_query]
        if entity:
            conditions.append("e.entity_id = ?")
            params.append(entity)
        if domain:
            conditions.append("e.domain = ?")
            params.append(domain)
        if from_ts is not None:
            conditions.append("e.timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            conditions.append("e.timestamp <= ?")
            params.append(to_ts)
        where = " WHERE " + " AND ".join(conditions)
        rows = await self._db.execute_fetchall(
            f"SELECT e.* FROM events e{where} ORDER BY e.timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [dict(r) for r in rows]

    async def search_fts_count(
        self,
        query: str,
        from_ts: int | None = None,
        to_ts: int | None = None,
        entity: str | None = None,
        domain: str | None = None,
    ) -> int:
        assert self._db is not None
        safe_query = self._fts_safe(query)
        if not safe_query:
            return 0
        conditions: list[str] = ["e.id IN (SELECT event_id FROM events_fts WHERE events_fts MATCH ?)"]
        params: list[Any] = [safe_query]
        if entity:
            conditions.append("e.entity_id = ?")
            params.append(entity)
        if domain:
            conditions.append("e.domain = ?")
            params.append(domain)
        if from_ts is not None:
            conditions.append("e.timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            conditions.append("e.timestamp <= ?")
            params.append(to_ts)
        where = " WHERE " + " AND ".join(conditions)
        rows = await self._db.execute_fetchall(
            f"SELECT COUNT(*) FROM events e{where}",
            params,
        )
        return rows[0][0] if rows else 0

    # ─── Bookmark ──────────────────────────────────────────

    async def bookmark(self, event_id: str, note: str) -> bool:
        assert self._db is not None
        cursor = await self._db.execute(
            "UPDATE events SET important = 1 WHERE id = ?", (event_id,),
        )
        await self._db.commit()
        return (cursor.rowcount or 0) > 0

    # ─── Parent linking helpers ────────────────────────────

    async def update_parent(
        self, event_id: str, parent_id: str, confidence: str = "inferred",
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            "UPDATE events SET parent_id = ?, confidence = ? WHERE id = ?",
            (parent_id, confidence, event_id),
        )
        await self._db.commit()

    async def find_recent_by_entity(
        self, entity_id: str, before_ts: int, window_ms: int,
    ) -> list[dict[str, Any]]:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """SELECT * FROM events
               WHERE entity_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp DESC LIMIT 10""",
            (entity_id, before_ts - window_ms, before_ts),
        )
        return [dict(r) for r in rows]

    async def find_recent_by_context(
        self, context_id: str, before_ts: int, window_ms: int,
    ) -> dict[str, Any] | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """SELECT * FROM events
               WHERE id = ? AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT 1""",
            (context_id, before_ts - window_ms),
        )
        return dict(rows[0]) if rows else None

    async def find_recent_by_user_entity(
        self, user_id: str, entity_id: str, before_ts: int, window_ms: int,
    ) -> dict[str, Any] | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """SELECT * FROM events
               WHERE user_id = ? AND entity_id = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp DESC LIMIT 1""",
            (user_id, entity_id, before_ts - window_ms, before_ts),
        )
        return dict(rows[0]) if rows else None

    async def find_recent_call_service(
        self, entity_id: str, before_ts: int, window_ms: int,
    ) -> dict[str, Any] | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """SELECT * FROM events
               WHERE event_type = 'call_service' AND entity_id = ?
                 AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp DESC LIMIT 1""",
            (entity_id, before_ts - window_ms, before_ts),
        )
        return dict(rows[0]) if rows else None

    # ─── Entities ──────────────────────────────────────────

    async def upsert_entity(self, entity: EntityRecord) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO entities
                 (entity_id, friendly_name, device_id, area, integration, attributes, last_seen)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(entity_id) DO UPDATE SET
                 friendly_name=excluded.friendly_name,
                 device_id=excluded.device_id,
                 area=excluded.area,
                 integration=excluded.integration,
                 attributes=excluded.attributes,
                 last_seen=excluded.last_seen""",
            (
                entity.entity_id, entity.friendly_name, entity.device_id,
                entity.area, entity.integration, entity.attributes, entity.last_seen,
            ),
        )
        await self._db.commit()

    async def get_all_entities(self) -> list[dict[str, Any]]:
        assert self._db is not None
        rows = await self._db.execute_fetchall("SELECT * FROM entities")
        return [dict(r) for r in rows]

    # ─── Trees index ───────────────────────────────────────

    async def upsert_tree(
        self, tree_id: str, root_event_id: str, created_at: int,
        summary: str | None = None,
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO trees (tree_id, root_event_id, created_at, summary)
               VALUES (?,?,?,?)
               ON CONFLICT(tree_id) DO UPDATE SET summary=excluded.summary""",
            (tree_id, root_event_id, created_at, summary),
        )
        await self._db.commit()

    async def get_trees(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM trees ORDER BY created_at DESC LIMIT ?", (limit,),
        )
        return [dict(r) for r in rows]

    # ─── Entity history ────────────────────────────────────

    async def get_entity_history(
        self, entity_id: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get all events for an entity ordered by time descending."""
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            """SELECT * FROM events
               WHERE entity_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (entity_id, limit),
        )
        return [dict(r) for r in rows]

    # ─── Stats ─────────────────────────────────────────────

    async def get_event_count(self) -> int:
        assert self._db is not None
        rows = await self._db.execute_fetchall("SELECT COUNT(*) as cnt FROM events")
        return rows[0]["cnt"] if rows else 0

    async def get_last_event_ts(self) -> int | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT MAX(timestamp) as ts FROM events",
        )
        return rows[0]["ts"] if rows and rows[0]["ts"] else None

    async def get_db_size(self) -> int:
        try:
            return os.path.getsize(self._db_path)
        except OSError:
            return 0

    async def get_activity_stats(self) -> dict[str, Any]:
        """Comprehensive activity statistics for the stats dashboard."""
        assert self._db is not None

        # Total events
        total_count = await self.get_event_count()

        # Events per entity (top 50)
        rows = await self._db.execute_fetchall(
            """SELECT entity_id, COUNT(*) as cnt
               FROM events WHERE entity_id IS NOT NULL
               GROUP BY entity_id ORDER BY cnt DESC LIMIT 50""",
        )
        entity_counts = [{"entity_id": r["entity_id"], "count": r["cnt"]} for r in rows]

        # Events per domain
        rows = await self._db.execute_fetchall(
            """SELECT domain, COUNT(*) as cnt
               FROM events WHERE domain IS NOT NULL
               GROUP BY domain ORDER BY cnt DESC""",
        )
        domain_counts = [{"domain": r["domain"], "count": r["cnt"]} for r in rows]

        # Events per event_type
        rows = await self._db.execute_fetchall(
            """SELECT event_type, COUNT(*) as cnt
               FROM events GROUP BY event_type ORDER BY cnt DESC""",
        )
        type_counts = [{"event_type": r["event_type"], "count": r["cnt"]} for r in rows]

        # Hourly distribution (last 24h)
        now_ms = int(time.time() * 1000)
        day_ago = now_ms - 86400000
        rows = await self._db.execute_fetchall(
            """SELECT (timestamp / 3600000) % 24 as hour, COUNT(*) as cnt
               FROM events WHERE timestamp >= ?
               GROUP BY hour ORDER BY hour""",
            (day_ago,),
        )
        hourly = [{"hour": r["hour"], "count": r["cnt"]} for r in rows]

        # Daily distribution (last 30 days)
        month_ago = now_ms - 2592000000
        rows = await self._db.execute_fetchall(
            """SELECT timestamp / 86400000 as day, COUNT(*) as cnt
               FROM events WHERE timestamp >= ?
               GROUP BY day ORDER BY day""",
            (month_ago,),
        )
        daily = [{"day": r["day"], "count": r["cnt"]} for r in rows]

        # Today vs yesterday
        today_start = (now_ms // 86400000) * 86400000
        yesterday_start = today_start - 86400000
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM events WHERE timestamp >= ?",
            (today_start,),
        )
        today_count = rows[0]["cnt"] if rows else 0
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM events WHERE timestamp >= ? AND timestamp < ?",
            (yesterday_start, today_start),
        )
        yesterday_count = rows[0]["cnt"] if rows else 0

        # Confidence breakdown
        rows = await self._db.execute_fetchall(
            """SELECT confidence, COUNT(*) as cnt
               FROM events GROUP BY confidence""",
        )
        confidence = {r["confidence"]: r["cnt"] for r in rows}

        # Most active time of day (last 7 days)
        week_ago = now_ms - 604800000
        rows = await self._db.execute_fetchall(
            """SELECT (timestamp / 3600000) % 24 as hour, COUNT(*) as cnt
               FROM events WHERE timestamp >= ?
               GROUP BY hour ORDER BY cnt DESC LIMIT 1""",
            (week_ago,),
        )
        peak_hour = rows[0]["hour"] if rows else None

        return {
            "total_events": total_count,
            "entity_counts": entity_counts,
            "domain_counts": domain_counts,
            "type_counts": type_counts,
            "hourly_24h": hourly,
            "daily_30d": daily,
            "today_count": today_count,
            "yesterday_count": yesterday_count,
            "confidence": confidence,
            "peak_hour": peak_hour,
        }

    # ─── Purge ─────────────────────────────────────────────

    async def purge_old_events(self, before_ts: int) -> int:
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM events_fts WHERE event_id IN "
            "(SELECT id FROM events WHERE timestamp < ?)",
            (before_ts,),
        )
        await self._db.execute(
            "DELETE FROM raw_events WHERE event_id IN "
            "(SELECT id FROM events WHERE timestamp < ?)",
            (before_ts,),
        )
        cursor = await self._db.execute(
            "DELETE FROM events WHERE timestamp < ?", (before_ts,),
        )
        await self._db.commit()
        return cursor.rowcount or 0

    # ─── Config ────────────────────────────────────────────

    async def get_config_value(self, key: str) -> str | None:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT value FROM config WHERE key = ?", (key,),
        )
        return rows[0]["value"] if rows else None

    # ─── KNX ───────────────────────────────────────────────

    async def insert_knx_telegram(self, telegram: dict[str, Any]) -> None:
        """Insert a KNX telegram and upsert its GA summary row."""
        assert self._db is not None
        await self._db.execute(
            """INSERT OR IGNORE INTO knx_telegrams
               (id, timestamp, group_address, direction, source_address,
                telegram_type, raw_data, decoded_value, dpt_type,
                linked_entity_id, linked_event_id, context_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                telegram["id"],
                telegram["timestamp"],
                telegram["group_address"],
                telegram["direction"],
                telegram.get("source_address"),
                telegram["telegram_type"],
                telegram.get("raw_data"),
                telegram.get("decoded_value"),  # already JSON string
                telegram.get("dpt_type"),
                telegram.get("linked_entity_id"),
                telegram.get("linked_event_id"),
                telegram.get("context_id"),
            ),
        )
        # Upsert GA summary
        col = {
            "GroupValueWrite":    "total_writes",
            "GroupValueRead":     "total_reads",
            "GroupValueResponse": "total_responses",
        }.get(telegram["telegram_type"], "total_writes")
        await self._db.execute(
            f"""INSERT INTO knx_group_addresses
                  (group_address, last_seen, {col}, last_value)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(group_address) DO UPDATE SET
                  last_seen = excluded.last_seen,
                  {col} = {col} + 1,
                  last_value = COALESCE(excluded.last_value, last_value)""",
            (
                telegram["group_address"],
                telegram["timestamp"],
                telegram.get("decoded_value"),
            ),
        )
        await self._db.commit()

    async def get_knx_telegrams(
        self,
        limit: int = 100,
        offset: int = 0,
        group_address: str | None = None,
        direction: str | None = None,
        entity_id: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        assert self._db is not None
        conditions: list[str] = []
        params: list[Any] = []
        if group_address:
            conditions.append("group_address = ?")
            params.append(group_address)
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if entity_id:
            conditions.append("linked_entity_id = ?")
            params.append(entity_id)
        if from_ts is not None:
            conditions.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            conditions.append("timestamp <= ?")
            params.append(to_ts)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        count_rows = await self._db.execute_fetchall(
            f"SELECT COUNT(*) as cnt FROM knx_telegrams{where}", params,
        )
        total = count_rows[0]["cnt"] if count_rows else 0
        rows = await self._db.execute_fetchall(
            f"SELECT * FROM knx_telegrams{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [dict(r) for r in rows], total

    async def get_knx_group_addresses(
        self, limit: int = 200,
    ) -> list[dict[str, Any]]:
        assert self._db is not None
        rows = await self._db.execute_fetchall(
            "SELECT * FROM knx_group_addresses ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def get_knx_flow(
        self, group_address: str, around_ts: int, window_ms: int = 5000,
    ) -> list[dict[str, Any]]:
        """Return all events (KNX + HA) in a time window around a GA activity."""
        assert self._db is not None
        start = around_ts - window_ms
        end   = around_ts + window_ms
        # KNX telegrams for this GA in the window
        knx_rows = await self._db.execute_fetchall(
            """SELECT id, timestamp, 'knx_telegram' as event_type,
                      group_address as entity_id, direction,
                      telegram_type, decoded_value, source_address,
                      linked_entity_id, linked_event_id, context_id,
                      NULL as name
               FROM knx_telegrams
               WHERE group_address = ? AND timestamp BETWEEN ? AND ?
               ORDER BY timestamp""",
            (group_address, start, end),
        )
        # Linked HA events in the same window for affected entities
        if knx_rows:
            entity_ids = list({
                r["linked_entity_id"] for r in knx_rows if r["linked_entity_id"]
            })
            if entity_ids:
                placeholders = ",".join("?" * len(entity_ids))
                ha_rows = await self._db.execute_fetchall(
                    f"""SELECT id, timestamp, event_type, entity_id, name,
                               domain, service, confidence, parent_id, user_id
                        FROM events
                        WHERE entity_id IN ({placeholders})
                          AND timestamp BETWEEN ? AND ?
                        ORDER BY timestamp""",
                    [*entity_ids, start, end],
                )
            else:
                ha_rows = []
        else:
            ha_rows = []
        return [dict(r) for r in knx_rows], [dict(r) for r in ha_rows]

    async def update_knx_ga_entity(
        self, group_address: str, entity_id: str,
    ) -> None:
        """Update the entity mapping for a GA after discovering it from state changes."""
        assert self._db is not None
        await self._db.execute(
            """UPDATE knx_telegrams
               SET linked_entity_id = ?
               WHERE group_address = ? AND linked_entity_id IS NULL""",
            (entity_id, group_address),
        )
        await self._db.commit()

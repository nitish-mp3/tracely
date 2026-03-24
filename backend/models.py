"""Pydantic v2 models for API, internal data, and DB records."""

from __future__ import annotations

from pydantic import BaseModel


# ─── Database / internal records ─────────────────────────


class EventRecord(BaseModel):
    id: str
    parent_id: str | None = None
    event_type: str
    domain: str | None = None
    service: str | None = None
    entity_id: str | None = None
    payload: str  # JSON string
    name: str | None = None
    integration: str | None = None
    area: str | None = None
    timestamp: int  # epoch ms
    user_id: str | None = None
    important: int = 0
    confidence: str = "propagated"
    generated_root: int = 0


class EntityRecord(BaseModel):
    entity_id: str
    friendly_name: str | None = None
    device_id: str | None = None
    area: str | None = None
    integration: str | None = None
    attributes: str | None = None  # JSON
    last_seen: int | None = None


class TreeSummary(BaseModel):
    tree_id: str
    root_event_id: str
    created_at: int
    summary: str | None = None  # JSON


# ─── API response models ────────────────────────────────


class EventResponse(BaseModel):
    id: str
    parent_id: str | None = None
    event_type: str
    domain: str | None = None
    service: str | None = None
    entity_id: str | None = None
    payload: dict  # parsed JSON
    name: str | None = None
    integration: str | None = None
    area: str | None = None
    timestamp: str  # ISO 8601
    user_id: str | None = None
    important: bool = False
    confidence: str = "propagated"
    generated_root: bool = False


class PaginatedEvents(BaseModel):
    total: int
    page: int
    limit: int
    items: list[EventResponse]


class TreeStats(BaseModel):
    total_nodes: int
    domain_breakdown: dict[str, int]
    domain_count: int
    duration_ms: int | None = None
    inferred_count: int = 0
    verified_count: int = 0
    top_entity: dict[str, str | int] | None = None
    entity_count: int = 0


class TreeResponse(BaseModel):
    event: EventResponse
    tree: list[EventResponse]
    tree_depth: int
    root_id: str
    stats: TreeStats | None = None


class LogInfo(BaseModel):
    """Log file diagnostic info."""
    available: bool
    source: str = ""
    size_bytes: int = 0
    line_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    last_entry_ts: str = ""
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    db_size_bytes: int
    last_event_ts: str | None = None
    events_count: int
    ws_connected: bool
    uptime_seconds: float
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_rss_mb: float = 0.0
    event_queue_depth: int = 0
    last_async_block_ms: float = 0.0
    incidents_total: int = 0
    ha_restart_count: int = 0
    ha_core_log: LogInfo | None = None


class IncidentResponse(BaseModel):
    id: str
    incident_type: str
    severity: str
    source: str
    message: str
    details: dict
    related_event_id: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_rss_mb: float | None = None
    event_queue_depth: int | None = None
    loop_block_ms: float | None = None
    timestamp: str


class BookmarkRequest(BaseModel):
    note: str = ""


# ─── KNX models ────────────────────────────────────────


class KnxTelegramResponse(BaseModel):
    id: str
    timestamp: str          # ISO 8601
    group_address: str
    direction: str          # "Incoming" | "Outgoing"
    source_address: str | None = None
    telegram_type: str      # "GroupValueWrite" | "GroupValueRead" | "GroupValueResponse"
    raw_data: str | None = None
    decoded_value: str | None = None
    dpt_type: str | None = None
    linked_entity_id: str | None = None
    linked_entity_name: str | None = None
    linked_event_id: str | None = None
    context_id: str | None = None


class KnxGroupAddressResponse(BaseModel):
    group_address: str
    friendly_name: str | None = None
    dpt_type: str | None = None
    linked_entities: str | None = None     # JSON array string
    last_seen: str | None = None           # ISO 8601
    total_writes: int = 0
    total_reads: int = 0
    total_responses: int = 0
    last_value: str | None = None


class PaginatedKnxTelegrams(BaseModel):
    total: int
    page: int
    limit: int
    items: list[KnxTelegramResponse]


class KnxFlowResponse(BaseModel):
    group_address: str
    around_ts: str               # ISO 8601 centre of the window
    window_ms: int
    knx_telegrams: list[KnxTelegramResponse]
    ha_events: list[EventResponse]


# ─── Alert models ──────────────────────────────────────


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    message: str
    entity_id: str | None = None
    integration: str | None = None
    details: dict
    acknowledged: bool = False
    timestamp: str  # ISO 8601

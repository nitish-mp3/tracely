"""Health and metrics endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from .models import HealthResponse

if TYPE_CHECKING:
    from .ha_client import HAClient
    from .storage import Storage

logger = structlog.get_logger(__name__)

_start_time = time.time()


async def get_health(storage: Storage, ha_client: HAClient) -> HealthResponse:
    """Build health check response."""
    event_count = await storage.get_event_count()
    last_ts = await storage.get_last_event_ts()
    db_size = await storage.get_db_size()

    last_event_iso = None
    if last_ts:
        last_event_iso = datetime.fromtimestamp(
            last_ts / 1000, tz=timezone.utc,
        ).isoformat()

    return HealthResponse(
        status="ok",
        db_size_bytes=db_size,
        last_event_ts=last_event_iso,
        events_count=event_count,
        ws_connected=ha_client.connected,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


def get_metrics_text(
    events_total: int,
    db_size_bytes: int,
    ws_connected: bool,
) -> str:
    """Generate Prometheus text format metrics."""
    lines = [
        "# HELP tracely_events_total Total number of events stored",
        "# TYPE tracely_events_total gauge",
        f"tracely_events_total {events_total}",
        "",
        "# HELP tracely_db_size_bytes Database file size in bytes",
        "# TYPE tracely_db_size_bytes gauge",
        f"tracely_db_size_bytes {db_size_bytes}",
        "",
        "# HELP tracely_ws_connected WebSocket connection status",
        "# TYPE tracely_ws_connected gauge",
        f"tracely_ws_connected {1 if ws_connected else 0}",
        "",
        "# HELP tracely_uptime_seconds Addon uptime in seconds",
        "# TYPE tracely_uptime_seconds gauge",
        f"tracely_uptime_seconds {round(time.time() - _start_time, 1)}",
    ]
    return "\n".join(lines) + "\n"

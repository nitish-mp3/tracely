"""Health and metrics endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import structlog

try:
    import psutil
except Exception:  # pragma: no cover - fallback when psutil is unavailable
    psutil = None

from .models import HealthResponse, LogInfo
from . import logs

if TYPE_CHECKING:
    from .ha_client import HAClient
    from .storage import Storage

logger = structlog.get_logger(__name__)

_start_time = time.time()
_process = psutil.Process() if psutil else None


def get_runtime_metrics() -> dict[str, float]:
    """Return process-level runtime metrics with graceful fallback."""
    if not _process:
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_rss_mb": 0.0,
        }
    try:
        mem = _process.memory_info()
        return {
            "cpu_percent": float(_process.cpu_percent(interval=None)),
            "memory_percent": float(_process.memory_percent()),
            "memory_rss_mb": float(mem.rss / (1024 * 1024)),
        }
    except Exception:
        logger.exception("health.runtime_metrics_error")
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_rss_mb": 0.0,
        }


async def get_health(
    storage: Storage,
    ha_client: HAClient,
    runtime_status: dict[str, Any] | None = None,
) -> HealthResponse:
    """Build health check response."""
    event_count = await storage.get_event_count()
    incidents_total = await storage.get_incident_count()
    last_ts = await storage.get_last_event_ts()
    db_size = await storage.get_db_size()
    runtime = get_runtime_metrics()
    runtime_status = runtime_status or {}

    last_event_iso = None
    if last_ts:
        last_event_iso = datetime.fromtimestamp(
            last_ts / 1000, tz=timezone.utc,
        ).isoformat()

    # Capture HA core log summary
    log_summary = logs.get_log_summary(max_bytes=100_000)
    ha_core_log = None
    if log_summary.get("available"):
        ha_core_log = LogInfo(
            available=True,
            size_bytes=log_summary.get("size_bytes", 0),
            line_count=log_summary.get("line_count", 0),
            error_count=log_summary.get("error_count", 0),
            warning_count=log_summary.get("warning_count", 0),
            last_entry_ts=log_summary.get("last_entry_ts", ""),
        )
    else:
        ha_core_log = LogInfo(
            available=False,
            error=log_summary.get("error"),
        )

    return HealthResponse(
        status="ok",
        db_size_bytes=db_size,
        last_event_ts=last_event_iso,
        events_count=event_count,
        ws_connected=ha_client.connected,
        uptime_seconds=round(time.time() - _start_time, 1),
        cpu_percent=round(runtime["cpu_percent"], 2),
        memory_percent=round(runtime["memory_percent"], 2),
        memory_rss_mb=round(runtime["memory_rss_mb"], 2),
        event_queue_depth=int(runtime_status.get("event_queue_depth", 0)),
        last_async_block_ms=round(float(runtime_status.get("last_async_block_ms", 0.0)), 2),
        incidents_total=incidents_total,
        ha_restart_count=int(runtime_status.get("ha_restart_count", 0)),
        ha_core_log=ha_core_log,
    )


def get_metrics_text(
    events_total: int,
    db_size_bytes: int,
    ws_connected: bool,
    runtime_status: dict[str, Any],
    incidents_total: int,
) -> str:
    """Generate Prometheus text format metrics."""
    runtime = get_runtime_metrics()
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
        "",
        "# HELP tracely_cpu_percent Current process CPU usage percent",
        "# TYPE tracely_cpu_percent gauge",
        f"tracely_cpu_percent {runtime['cpu_percent']:.2f}",
        "",
        "# HELP tracely_memory_percent Current process memory usage percent",
        "# TYPE tracely_memory_percent gauge",
        f"tracely_memory_percent {runtime['memory_percent']:.2f}",
        "",
        "# HELP tracely_memory_rss_mb Current process RSS memory in MB",
        "# TYPE tracely_memory_rss_mb gauge",
        f"tracely_memory_rss_mb {runtime['memory_rss_mb']:.2f}",
        "",
        "# HELP tracely_event_queue_depth Current HA event queue depth",
        "# TYPE tracely_event_queue_depth gauge",
        f"tracely_event_queue_depth {int(runtime_status.get('event_queue_depth', 0))}",
        "",
        "# HELP tracely_last_async_block_ms Last detected async loop blockage in ms",
        "# TYPE tracely_last_async_block_ms gauge",
        f"tracely_last_async_block_ms {float(runtime_status.get('last_async_block_ms', 0.0)):.2f}",
        "",
        "# HELP tracely_incidents_total Total number of recorded incidents",
        "# TYPE tracely_incidents_total gauge",
        f"tracely_incidents_total {incidents_total}",
        "",
        "# HELP tracely_ha_restarts_total Number of detected Home Assistant starts",
        "# TYPE tracely_ha_restarts_total counter",
        f"tracely_ha_restarts_total {int(runtime_status.get('ha_restart_count', 0))}",
    ]
    return "\n".join(lines) + "\n"

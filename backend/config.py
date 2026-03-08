"""Tracely configuration — Pydantic Settings, env-driven."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # HA connection
    ha_url: str = ""
    ha_token: str = ""
    supervisor_token: str = ""

    # Database
    db_path: str = "/data/tracely.db"

    # Frontend
    frontend_dir: str = "/app/frontend/dist"

    # Server
    host: str = "0.0.0.0"
    port: int = 8099

    # Logging
    log_level: str = "info"
    redact_pii: bool = True

    # Retention
    purge_keep_days: int = 30

    # Heuristics
    aggregate_threshold_per_sec: int = 5
    infer_window_ms: int = 3000
    dedup_window_ms: int = 500

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    model_config = {"env_prefix": "", "extra": "ignore"}

    @property
    def effective_ha_url(self) -> str:
        """Resolve the HA WebSocket URL with auto-discovery."""
        if self.ha_url:
            return self.ha_url
        if self.supervisor_token or os.environ.get("SUPERVISOR_TOKEN"):
            return "ws://supervisor/core/websocket"
        return "ws://localhost:8123/api/websocket"

    @property
    def effective_token(self) -> str:
        """Resolve the best available auth token."""
        return (
            self.ha_token
            or self.supervisor_token
            or os.environ.get("SUPERVISOR_TOKEN", "")
        )

    @property
    def is_supervised(self) -> bool:
        """True when running under HA Supervisor (token auto-provided)."""
        return bool(self.supervisor_token or os.environ.get("SUPERVISOR_TOKEN"))

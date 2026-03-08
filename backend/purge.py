"""Background purge and compression jobs."""

from __future__ import annotations

import asyncio
import time

import structlog

from .config import Settings
from .storage import Storage

logger = structlog.get_logger(__name__)


class PurgeManager:
    """Manages background data retention: periodic purge + emergency purge."""

    def __init__(self, storage: Storage, settings: Settings) -> None:
        self._storage = storage
        self._keep_days = settings.purge_keep_days
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._purge_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _purge_loop(self) -> None:
        """Run purge every 10 minutes."""
        while self._running:
            try:
                await asyncio.sleep(600)  # 10 minutes
                await self._run_purge()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("purge.error")

    async def _run_purge(self) -> None:
        cutoff_ms = int((time.time() - self._keep_days * 86400) * 1000)
        deleted = await self._storage.purge_old_events(cutoff_ms)
        if deleted > 0:
            logger.info(
                "purge.completed", deleted=deleted, keep_days=self._keep_days,
            )

    async def emergency_purge(self) -> None:
        """Delete oldest 10% of events when disk is full."""
        total = await self._storage.get_event_count()
        if total == 0:
            return
        logger.warning("purge.emergency", total_events=total)
        # Shift the cutoff to keep 90% of the time range
        cutoff_ms = int(
            (time.time() - self._keep_days * 86400 * 0.9) * 1000,
        )
        deleted = await self._storage.purge_old_events(cutoff_ms)
        logger.warning("purge.emergency_completed", deleted=deleted)

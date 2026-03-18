"""Independent heartbeat monitor for HA health detection."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class HeartbeatMonitor:
    """
    Probe HA health independently via HTTP.

    Creates synthetic STOP event after N consecutive failures.
    """

    def __init__(
        self,
        ha_url: str,
        token: str,
        interval_seconds: int = 10,
        failure_threshold: int = 3,
        timeout_seconds: int = 5,
        on_failure: Callable[[], None] | None = None,
    ) -> None:
        self.ha_url = ha_url.rstrip("/")
        self.token = token
        self.interval_seconds = max(1, interval_seconds)
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.on_failure = on_failure

        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._consecutive_failures = 0
        self._last_failure_time: float | None = None
        self._session: aiohttp.ClientSession | None = None
        self.healthy = True

    async def start(self) -> None:
        """Start heartbeat loop."""
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "heartbeat_monitor.started",
            ha_url=self.ha_url,
            interval=self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("heartbeat_monitor.stopped")

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                success = await self._check_health()

                if success:
                    self._consecutive_failures = 0
                    if not self.healthy:
                        self.healthy = True
                        logger.info("heartbeat_monitor.recovered")
                else:
                    self._consecutive_failures += 1
                    self._last_failure_time = time.time()

                    if self._consecutive_failures == self.failure_threshold:
                        self.healthy = False
                        logger.warning(
                            "heartbeat_monitor.unreachable",
                            consecutive_failures=self._consecutive_failures,
                        )
                        if self.on_failure:
                            self.on_failure()

            except Exception:
                logger.exception("heartbeat_monitor.loop_error")

            await asyncio.sleep(self.interval_seconds)

    async def _check_health(self) -> bool:
        """
        Ping HA health endpoint.

        Returns True if response is 2xx, False otherwise.
        """
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        endpoint = f"{self.ha_url}/api/"
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            async with self._session.get(
                endpoint,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as resp:
                success = 200 <= resp.status < 300
                if not success:
                    logger.debug(
                        "heartbeat_monitor.bad_status",
                        status=resp.status,
                    )
                return success

        except asyncio.TimeoutError:
            logger.debug("heartbeat_monitor.timeout", endpoint=endpoint)
            return False
        except Exception as e:
            logger.debug(
                "heartbeat_monitor.request_error",
                error=str(e),
            )
            return False

    def get_status(self) -> dict:
        """Return current heartbeat status."""
        return {
            "healthy": self.healthy,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
        }

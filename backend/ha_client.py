"""HA WebSocket client — persistent connection with auto-reconnect."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import structlog

from .config import Settings

logger = structlog.get_logger(__name__)

HA_EVENT_TYPES = [
    "state_changed",
    "call_service",
    "automation_triggered",
    "script_started",
    "script_finished",
    "logbook_entry",
    "homeassistant_start",
    "homeassistant_stop",
]


class HAClient:
    """Persistent WebSocket client to Home Assistant with auto-reconnect."""

    def __init__(
        self,
        settings: Settings,
        on_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self._ws_url = settings.effective_ha_url
        self._token = settings.effective_token
        self._on_event = on_event
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._connected = False
        self._running = False
        self._msg_id = 0
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the WebSocket connection loop."""
        self._running = True
        self._task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Stop the connection loop and clean up."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False

    async def fetch_states(self) -> list[dict[str, Any]]:
        """Fetch all entity states via HTTP API."""
        http_url = (
            self._ws_url
            .replace("ws://", "http://")
            .replace("wss://", "https://")
            .replace("/api/websocket", "/api/states")
            .replace("/core/websocket", "/core/api/states")
        )
        headers = {"Authorization": f"Bearer {self._token}"}
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with self._session.get(http_url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()  # type: ignore[no-any-return]
                logger.warning("ha_client.fetch_states_failed", status=resp.status)
                return []
        except Exception:
            logger.exception("ha_client.fetch_states_error")
            return []

    # ─── Connection loop ───────────────────────────────────

    async def _connection_loop(self) -> None:
        """Main connection loop with exponential backoff reconnect."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ha_client.connection_error")

            if not self._running:
                break

            self._connected = False
            logger.info(
                "ha_client.reconnecting", delay=self._reconnect_delay,
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay,
            )

    async def _connect_and_listen(self) -> None:
        """Connect to HA WS, authenticate, subscribe, and listen."""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

        logger.info("ha_client.connecting", url=self._ws_url)
        self._ws = await self._session.ws_connect(self._ws_url)
        self._msg_id = 0

        # Wait for auth_required
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_required":
            logger.error("ha_client.unexpected_message", msg=msg)
            return

        # Authenticate
        await self._ws.send_json({
            "type": "auth",
            "access_token": self._token,
        })
        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_ok":
            logger.error("ha_client.auth_failed", msg=msg)
            return

        logger.info("ha_client.authenticated")
        self._connected = True
        self._reconnect_delay = 1.0  # reset backoff on success

        # Subscribe to event types
        for event_type in HA_EVENT_TYPES:
            self._msg_id += 1
            await self._ws.send_json({
                "id": self._msg_id,
                "type": "subscribe_events",
                "event_type": event_type,
            })
            resp = await self._ws.receive_json()
            if not resp.get("success", False):
                logger.warning(
                    "ha_client.subscribe_failed",
                    event_type=event_type,
                    resp=resp,
                )

        logger.info("ha_client.subscribed", event_types=HA_EVENT_TYPES)

        # Listen for events
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("type") == "event":
                        await self._on_event(data.get("event", {}))
                except json.JSONDecodeError:
                    logger.warning("ha_client.invalid_json")
                except Exception:
                    logger.exception("ha_client.event_handler_error")
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                break

        self._connected = False

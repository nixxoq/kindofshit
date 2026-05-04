from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import connect

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
StatusHandler = Callable[[str], Awaitable[None]]


class WebSocketListener:
    def __init__(
        self,
        ws_url: str,
        token: str,
        on_event: EventHandler,
        on_status: StatusHandler | None = None,
    ) -> None:
        self.ws_url = ws_url
        self.token = token
        self.on_event = on_event
        self.on_status = on_status
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def _status(self, message: str) -> None:
        if self.on_status is not None:
            await self.on_status(message)

    async def run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                await self._status("connecting")
                async with connect(
                    self.ws_url,
                    additional_headers={"Authorization": f"Bearer {self.token}"},
                    ping_interval=20,
                    ping_timeout=20,
                ) as websocket:
                    delay = 1.0
                    await self._status("online")
                    async for raw_event in websocket:
                        if self._stop.is_set():
                            break
                        try:
                            event = json.loads(raw_event)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if isinstance(event, dict):
                            await self.on_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._status(f"offline: {exc}")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except TimeoutError:
                    delay = min(delay * 2, 10.0)

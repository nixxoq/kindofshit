from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    async def send_event(self, user_id: int, payload: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in self._connections.get(user_id, set()):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(user_id, websocket)

    async def broadcast(self, user_ids: list[int], payload: dict) -> None:
        seen: set[int] = set()
        for user_id in user_ids:
            if user_id in seen:
                continue
            seen.add(user_id)
            await self.send_event(user_id, payload)


connection_manager = ConnectionManager()

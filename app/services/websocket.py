from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis, ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._redis: Redis | None = None
        self._pool: ConnectionPool | None = None
        self._pubsub = None
        self._listen_task: asyncio.Task | None = None

    async def setup(self) -> None:
        settings = get_settings()
        self._pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=5000,
            socket_timeout=30,
            socket_connect_timeout=30,
            retry_on_timeout=True,
        )
        self._redis = Redis(connection_pool=self._pool)
        self._listen_task = asyncio.create_task(self._listen_redis())

    async def teardown(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()

    async def _listen_redis(self) -> None:
        while True:
            try:
                self._pubsub = self._redis.pubsub()
                await self._pubsub.psubscribe("user:*")
                async for message in self._pubsub.listen():
                    if message["type"] == "pmessage":
                        channel = message["channel"]
                        try:
                            user_id = int(channel.partition(":")[2])
                            if user_id in self._connections:
                                payload = json.loads(message["data"])
                                await self._send_to_local(user_id, payload)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await asyncio.sleep(1)
                continue

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def _send_to_local(self, user_id: int, payload: dict) -> None:
        if user_id not in self._connections:
            return
        stale = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(user_id, ws)

    async def broadcast(self, user_ids: list[int], payload: dict) -> None:
        if not self._redis:
            return
        data = json.dumps(jsonable_encoder(payload))
        pipe = self._redis.pipeline()
        for uid in set(user_ids):
            pipe.publish(f"user:{uid}", data)
        await pipe.execute()


connection_manager = ConnectionManager()

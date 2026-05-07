from __future__ import annotations

from fastapi import APIRouter, WebSocket, status
from starlette.websockets import WebSocketDisconnect

from app.api.dependencies import authenticate_websocket
from app.schemas.websocket import ErrorEventData, ReadyEventData
from app.services.websocket import connection_manager

import json
from datetime import datetime, timezone
from app.db.models import User

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    try:
        auth = await authenticate_websocket(websocket)
    except Exception:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "data": ErrorEventData(detail="Invalid token").model_dump(mode="json"),
            }
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await connection_manager.connect(auth.user.id, websocket)
    await websocket.send_json(
        {
            "type": "ready",
            "data": ReadyEventData(user_id=auth.user.id).model_dump(mode="json"),
        }
    )

    try:
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
                continue

            try:
                payload = json.loads(message)
                if payload.get("type") == "status_update":
                    is_online = payload["data"].get("is_online", False)
                    now = datetime.now(timezone.utc)

                    await User.filter(id=auth.user.id).update(
                        is_online=is_online, last_seen=now
                    )

                    all_users = await User.all().values_list("id", flat=True)
                    await connection_manager.broadcast(
                        list(all_users),
                        {
                            "type": "user.status_updated",
                            "data": {
                                "user_id": auth.user.id,
                                "is_online": is_online,
                                "last_seen": now.isoformat(),
                            },
                        },
                    )
                    continue
            except Exception:
                pass

            await websocket.send_json(
                {
                    "type": "error",
                    "data": ErrorEventData(
                        detail="Unsupported client event"
                    ).model_dump(mode="json"),
                }
            )
    except WebSocketDisconnect:
        connection_manager.disconnect(auth.user.id, websocket)

        now = datetime.now(timezone.utc)
        await User.filter(id=auth.user.id).update(is_online=False, last_seen=now)

        all_users = await User.all().values_list("id", flat=True)
        await connection_manager.broadcast(
            list(all_users),
            {
                "type": "user.status_updated",
                "data": {
                    "user_id": auth.user.id,
                    "is_online": False,
                    "last_seen": now.isoformat(),
                },
            },
        )

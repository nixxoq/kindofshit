from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.models import User, AuthToken
from app.services.auth import AuthenticatedContext, authenticate_token, parse_public_id
from app.services.websocket import connection_manager

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise ValueError("Missing Authorization header")
    if authorization_header.lower().startswith("bearer "):
        return authorization_header[7:].strip()
    return authorization_header.strip()


async def get_current_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    raw_token = credentials.credentials
    r = connection_manager._redis
    if r:
        try:
            cached = await r.get(f"session:{raw_token}")
            if cached:
                data = json.loads(cached)
                user = User(
                    id=data["u_id"], username=data["un"], display_name=data["dn"]
                )
                token = AuthToken(id=data["t_id"], public_id=parse_public_id(raw_token))
                return AuthenticatedContext(user=user, token=token)
        except Exception as exc:
            logger.warning(f"Session cache read error: {exc}")

    try:
        context = await authenticate_token(raw_token)
        if r:
            try:
                val = json.dumps(
                    {
                        "u_id": context.user.id,
                        "un": context.user.username,
                        "dn": context.user.display_name,
                        "t_id": context.token.id,
                    }
                )
                await r.setex(f"session:{raw_token}", 600, val)
            except Exception:
                pass
        return context
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


async def authenticate_websocket(websocket: WebSocket) -> AuthenticatedContext:
    try:
        raw_token = _extract_bearer_token(websocket.headers.get("authorization"))
        r = connection_manager._redis
        if r:
            try:
                cached = await r.get(f"session:{raw_token}")
                if cached:
                    data = json.loads(cached)
                    user = User(
                        id=data["u_id"], username=data["un"], display_name=data["dn"]
                    )
                    token = AuthToken(
                        id=data["t_id"], public_id=parse_public_id(raw_token)
                    )
                    return AuthenticatedContext(user=user, token=token)
            except Exception:
                pass

        context = await authenticate_token(raw_token)
        if r:
            try:
                val = json.dumps(
                    {
                        "u_id": context.user.id,
                        "un": context.user.username,
                        "dn": context.user.display_name,
                        "t_id": context.token.id,
                    }
                )
                await r.setex(f"session:{raw_token}", 600, val)
            except Exception:
                pass
        return context
    except Exception:
        raise ValueError("Invalid token")

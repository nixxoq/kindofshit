from __future__ import annotations

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import AuthenticatedContext, authenticate_token


bearer_scheme = HTTPBearer(auto_error=False)


def _extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise ValueError("Missing Authorization header")

    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ValueError("Invalid Authorization header")
    return token


async def get_current_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    try:
        return await authenticate_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


async def authenticate_websocket(websocket: WebSocket) -> AuthenticatedContext:
    try:
        token = _extract_bearer_token(websocket.headers.get("authorization"))
        return await authenticate_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

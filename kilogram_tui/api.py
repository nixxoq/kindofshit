from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from kilogram_tui.models import (
    DirectMessage,
    Message,
    MessagePage,
    PublicUser,
    SessionState,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class KilogramAPIError(RuntimeError):
    pass


class UnauthorizedError(KilogramAPIError):
    pass


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def websocket_url_for(base_url: str) -> str:
    parsed = urlparse(normalize_base_url(base_url))
    scheme = parsed.scheme.lower()
    if scheme == "http":
        ws_scheme = "ws"
    elif scheme == "https":
        ws_scheme = "wss"
    elif scheme in {"ws", "wss"}:
        ws_scheme = scheme
    else:
        raise ValueError(f"Unsupported API URL scheme: {parsed.scheme}")

    return urlunparse(
        parsed._replace(scheme=ws_scheme, path="/ws", params="", query="", fragment="")
    )


class KilogramAPI:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.token = token
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)

    @property
    def ws_url(self) -> str:
        return websocket_url_for(self.base_url)

    def auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        merged_headers = {**self.auth_headers(), **headers}
        response = await self.client.request(
            method, path, headers=merged_headers, **kwargs
        )
        if response.status_code == 401:
            raise UnauthorizedError("Invalid token")
        if response.is_error:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise KilogramAPIError(str(detail))
        return response

    async def register(
        self, username: str, display_name: str, password: str
    ) -> SessionState:
        response = await self._request(
            "POST",
            "/api/register",
            json={
                "username": username,
                "display_name": display_name,
                "password": password,
            },
        )
        data = response.json()
        self.token = str(data["token"])
        return SessionState(
            base_url=self.base_url,
            token=self.token,
            user_id=int(data["id"]),
            username=username,
        )

    async def login(self, username: str, password: str) -> SessionState:
        response = await self._request(
            "POST",
            "/api/login",
            json={"username": username, "password": password},
        )
        data = response.json()
        self.token = str(data["token"])
        return SessionState(
            base_url=self.base_url,
            token=self.token,
            user_id=int(data["user_id"]),
            username=str(data["username"]),
        )

    async def list_dms(self) -> list[DirectMessage]:
        response = await self._request("GET", "/api/dms")
        return [DirectMessage.from_json(item) for item in response.json()]

    async def search_users(self, query: str, limit: int = 10) -> list[PublicUser]:
        response = await self._request(
            "GET",
            "/api/users/search",
            params={"q": query, "limit": limit},
        )
        return [PublicUser.from_json(item) for item in response.json()]

    async def open_dm(
        self, recipient_id: int, peer: PublicUser | None = None
    ) -> DirectMessage:
        response = await self._request(
            "POST",
            "/api/dms/open",
            json={"recipient_id": recipient_id},
        )
        return DirectMessage.from_json(response.json(), peer=peer)

    async def mark_as_read(self, dm_id: int) -> None:
        await self._request("POST", f"/api/dms/{dm_id}/read")

    async def message_history(
        self,
        dm_id: int,
        limit: int = 50,
        before: int | None = None,
    ) -> MessagePage:
        params = {"limit": limit}
        if before is not None:
            params["before"] = before
        response = await self._request(
            "GET",
            f"/api/dms/{dm_id}/messages",
            params=params,
        )
        return MessagePage.from_json(response.json())

    async def send_message(self, dm_id: int, content: str) -> Message:
        response = await self._request(
            "POST",
            f"/api/dms/{dm_id}/messages",
            json={"content": content},
        )
        return Message.from_json(response.json())

    async def edit_message(self, dm_id: int, message_id: int, content: str) -> Message:
        response = await self._request(
            "PATCH",
            f"/api/dms/{dm_id}/messages/{message_id}",
            json={"content": content},
        )
        return Message.from_json(response.json())

    async def delete_message(self, dm_id: int, message_id: int) -> None:
        await self._request("DELETE", f"/api/dms/{dm_id}/messages/{message_id}")

    async def toggle_pin_message(
        self, dm_id: int, message_id: int, is_pinned: bool
    ) -> Message:
        response = await self._request(
            "PATCH",
            f"/api/dms/{dm_id}/messages/{message_id}/pin",
            json={"is_pinned": is_pinned},
        )
        return Message.from_json(response.json())

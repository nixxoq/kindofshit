from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageAuthor:
    id: int
    username: str
    display_name: str

    @classmethod
    def from_json(cls, data: dict) -> "MessageAuthor":
        return cls(
            id=int(data["id"]),
            username=str(data["username"]),
            display_name=str(data["display_name"]),
        )


@dataclass(frozen=True)
class SessionState:
    base_url: str
    token: str
    user_id: int
    username: str
    hidden_dm_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class PublicUser:
    id: int
    username: str
    display_name: str

    is_online: bool = False
    last_seen: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "PublicUser":
        return cls(
            id=int(data["id"]),
            username=str(data["username"]),
            display_name=str(data["display_name"]),

            is_online=bool(data.get("is_online", False)),
            last_seen=data.get("last_seen"),
        )


@dataclass(frozen=True)
class DirectMessage:
    id: int
    peer_user_id: int
    created_at: str
    peer: PublicUser | None = None

    @classmethod
    def from_json(cls, data: dict, peer: PublicUser | None = None) -> "DirectMessage":
        peer_data = data.get("peer")
        resolved_peer = peer
        if resolved_peer is None and isinstance(peer_data, dict):
            resolved_peer = PublicUser.from_json(peer_data)
        return cls(
            id=int(data["id"]),
            peer_user_id=int(data["peer_user_id"]),
            created_at=str(data["created_at"]),
            peer=resolved_peer,
        )

    @property
    def title(self) -> str:
        if self.peer is None:
            return f"user:{self.peer_user_id}"
        return f"{self.peer.display_name} ({self.peer.username})"


@dataclass(frozen=True)
class Message:
    id: int
    dm_id: int
    author_id: int
    author: MessageAuthor
    content: str
    created_at: str
    edited_at: str | None = None
    is_pinned: bool = False

    @classmethod
    def from_json(cls, data: dict) -> "Message":
        return cls(
            id=int(data["id"]),
            dm_id=int(data["dm_id"]),
            author_id=int(data["author_id"]),
            author=MessageAuthor.from_json(data["author"]),
            content=str(data["content"]),
            created_at=str(data["created_at"]),
            edited_at=data.get("edited_at"),
            is_pinned=bool(data.get("is_pinned", False)),
        )


@dataclass(frozen=True)
class MessagePage:
    items: list[Message]
    next_before: int | None

    @classmethod
    def from_json(cls, data: dict) -> "MessagePage":
        return cls(
            items=[Message.from_json(item) for item in data.get("items", [])],
            next_before=data.get("next_before"),
        )

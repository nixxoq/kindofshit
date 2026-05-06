from __future__ import annotations

import json
from typing import cast

from tortoise.expressions import Q
from tortoise import timezone

from app.db.models import DirectMessage, Message, User
from app.schemas.account import UserPublicResponse
from app.schemas.dm import DMResponse
from app.schemas.message import (
    MessageAuthorResponse,
    MessageHistoryResponse,
    MessageResponse,
)
from app.services.crypto import decrypt_message_text, encrypt_message_text
from app.utils import MessageError
from app.services.websocket import connection_manager


def normalize_dm_pair(user_a_id: int, user_b_id: int) -> tuple[int, int]:
    return cast(tuple[int, int], tuple(sorted((user_a_id, user_b_id))))


async def get_user_or_none(user_id: int) -> User | None:
    return await User.get_or_none(id=user_id)


async def open_or_create_dm(current_user: User, recipient: User) -> DirectMessage:
    low_id, high_id = normalize_dm_pair(current_user.id, recipient.id)
    dm, _ = await DirectMessage.get_or_create(user_low_id=low_id, user_high_id=high_id)
    return dm


async def list_dms_for_user(user_id: int) -> list[DirectMessage]:
    return (
        await DirectMessage.filter(Q(user_low_id=user_id) | Q(user_high_id=user_id))
        .order_by("-updated_at")
        .all()
    )


async def get_dm_by_id(dm_id: int) -> DirectMessage | None:
    r = connection_manager._redis
    if r:
        cached = await r.get(f"dm_meta:{dm_id}")
        if cached:
            data = json.loads(cached)
            return DirectMessage(
                id=dm_id, user_low_id=data["l"], user_high_id=data["h"]
            )

    dm = await DirectMessage.get_or_none(id=dm_id)
    if dm and r:
        await r.setex(
            f"dm_meta:{dm_id}",
            600,
            json.dumps({"l": dm.user_low_id, "h": dm.user_high_id}),
        )
    return dm


def is_dm_participant(dm: DirectMessage, user_id: int) -> bool:
    return user_id == dm.user_low_id or user_id == dm.user_high_id


async def _throttle_dm_update(dm_id: int) -> None:
    r = connection_manager._redis
    if not r:
        await DirectMessage.filter(id=dm_id).update(updated_at=timezone.now())
        return

    lock_key = f"dm_upd_lock:{dm_id}"
    if not await r.exists(lock_key):
        await r.setex(lock_key, 10, "1")
        await DirectMessage.filter(id=dm_id).update(updated_at=timezone.now())


def serialize_public_user(user: User) -> UserPublicResponse:
    return UserPublicResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_online=user.is_online,
        last_seen=user.last_seen,
    )


async def serialize_dm(dm: DirectMessage, current_user_id: int) -> DMResponse:
    peer_user_id = (
        dm.user_high_id if dm.user_low_id == current_user_id else dm.user_low_id
    )
    peer = await User.get(id=peer_user_id)
    return DMResponse(
        id=dm.id,
        peer_user_id=peer_user_id,
        peer=serialize_public_user(peer),
        created_at=dm.created_at,
    )


def serialize_message(message: Message, author: User) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        dm_id=message.dm_id,
        author_id=message.author_id,
        author=MessageAuthorResponse(
            id=author.id,
            username=author.username,
            display_name=author.display_name,
        ),
        content=decrypt_message_text(
            message.ciphertext, message.nonce, message.key_version
        ),
        created_at=message.created_at,
        edited_at=message.edited_at,
        is_pinned=message.is_pinned
    )


async def create_message(dm: DirectMessage, author: User, content: str) -> Message:
    ciphertext, nonce, key_version = encrypt_message_text(content)
    message = await Message.create(
        dm_id=dm.id,
        author_id=author.id,
        ciphertext=ciphertext,
        nonce=nonce,
        key_version=key_version,
    )
    await _throttle_dm_update(dm.id)
    return message


async def list_messages(
    dm: DirectMessage, limit: int, before: int | None
) -> MessageHistoryResponse:
    query = Message.filter(dm_id=dm.id).order_by("-id")
    if before is not None:
        query = query.filter(id__lt=before)

    messages = await query.prefetch_related("author").limit(limit + 1)
    has_more = len(messages) > limit
    messages = messages[:limit]

    items = [serialize_message(message, message.author) for message in messages]
    next_before = messages[-1].id if has_more and messages else None
    return MessageHistoryResponse(items=items, next_before=next_before)


async def delete_message(dm: DirectMessage, author: User, message_id: int) -> dict:
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)
    if not message or message.author_id != author.id:
        return {
            "error": (
                MessageError.FORBIDDEN if message else MessageError.MESSAGE_NOT_FOUND
            )
        }

    await message.delete()
    await _throttle_dm_update(dm.id)
    return {"status": "ok"}


async def edit_message(
    dm: DirectMessage, author: User, message_id: int, new_content: str
) -> dict:
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)
    if not message or message.author_id != author.id:
        return {
            "error": (
                MessageError.FORBIDDEN if message else MessageError.MESSAGE_NOT_FOUND
            )
        }

    ciphertext, nonce, key_version = encrypt_message_text(new_content)
    await Message.filter(id=message_id).update(
        ciphertext=ciphertext,
        nonce=nonce,
        key_version=key_version,
        edited_at=timezone.now(),
    )
    await _throttle_dm_update(dm.id)

    updated_message = await Message.get(id=message_id)
    return {"status": "ok", "message": serialize_message(updated_message, author)}

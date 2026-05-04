from __future__ import annotations

from typing import cast

from tortoise.exceptions import IntegrityError
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


def normalize_dm_pair(user_a_id: int, user_b_id: int) -> tuple[int, int]:
    return cast(tuple[int, int], tuple(sorted((user_a_id, user_b_id))))


async def get_user_or_none(user_id: int) -> User | None:
    return await User.get_or_none(id=user_id)


async def open_or_create_dm(current_user: User, recipient: User) -> DirectMessage:
    low_id, high_id = normalize_dm_pair(current_user.id, recipient.id)
    dm = await DirectMessage.get_or_none(user_low_id=low_id, user_high_id=high_id)
    if dm is not None:
        return dm

    try:
        return await DirectMessage.create(user_low_id=low_id, user_high_id=high_id)
    except IntegrityError:
        return await DirectMessage.get(user_low_id=low_id, user_high_id=high_id)


async def list_dms_for_user(user_id: int) -> list[DirectMessage]:
    return (
        await DirectMessage.filter(Q(user_low_id=user_id) | Q(user_high_id=user_id))
        .order_by("-updated_at")
        .all()
    )


async def get_dm_by_id(dm_id: int) -> DirectMessage | None:
    return await DirectMessage.get_or_none(id=dm_id)


def is_dm_participant(dm: DirectMessage, user_id: int) -> bool:
    return user_id in {dm.user_low_id, dm.user_high_id}


def serialize_public_user(user: User) -> UserPublicResponse:
    return UserPublicResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
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
    await dm.save(update_fields=["updated_at"])
    return message


async def list_messages(
    dm: DirectMessage, limit: int, before: int | None
) -> MessageHistoryResponse:
    query = Message.filter(dm_id=dm.id).order_by("-id")
    if before is not None:
        query = query.filter(id__lt=before)

    messages = await query.prefetch_related("author").limit(limit)
    items = [serialize_message(message, message.author) for message in messages]
    next_before = messages[-1].id if messages else None
    return MessageHistoryResponse(items=items, next_before=next_before)


async def delete_message(dm: DirectMessage, author: User, message_id: int) -> dict:
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)

    if not message:
        return {"error": MessageError.MESSAGE_NOT_FOUND}

    if message.author_id != author.id:
        return {"error": MessageError.FORBIDDEN}

    await message.delete()
    dm.updated_at = timezone.now()

    await dm.save(update_fields=["updated_at"])
    return {"status": "ok"}


async def edit_message(
    dm: DirectMessage, author: User, message_id: int, new_content: str
) -> dict:
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)

    if not message:
        return {"error": MessageError.MESSAGE_NOT_FOUND}

    if message.author_id != author.id:
        return {"error": MessageError.FORBIDDEN}

    old_content = decrypt_message_text(
        message.ciphertext, message.nonce, message.key_version
    )
    if new_content == old_content:
        return {"status": "ok", "message": serialize_message(message, author)}

    ciphertext, nonce, key_version = encrypt_message_text(new_content)

    message.ciphertext = ciphertext
    message.nonce = nonce
    message.key_version = key_version
    message.edited_at = timezone.now()

    await message.save(
        update_fields=["ciphertext", "nonce", "key_version", "edited_at"]
    )

    dm.updated_at = timezone.now()
    await dm.save(update_fields=["updated_at"])

    return {"status": "ok", "message": serialize_message(message, author)}

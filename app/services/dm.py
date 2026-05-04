from __future__ import annotations

from typing import cast

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise import timezone

from app.db.models import DirectMessage, Message, User
from app.schemas.dm import DMResponse
from app.schemas.message import MessageHistoryResponse, MessageResponse
from app.services.crypto import decrypt_message_text, encrypt_message_text


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


def serialize_dm(dm: DirectMessage, current_user_id: int) -> DMResponse:
    peer_user_id = (
        dm.user_high_id if dm.user_low_id == current_user_id else dm.user_low_id
    )
    return DMResponse(id=dm.id, peer_user_id=peer_user_id, created_at=dm.created_at)


def serialize_message(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        dm_id=message.dm_id,
        author_id=message.author_id,
        content=decrypt_message_text(
            message.ciphertext, message.nonce, message.key_version
        ),
        created_at=message.created_at,
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

    messages = await query.limit(limit)
    items = [serialize_message(message) for message in messages]
    next_before = messages[-1].id if messages else None
    return MessageHistoryResponse(items=items, next_before=next_before)


async def delete_message(dm: DirectMessage, author: User, message_id: int):
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)

    if message is None:
        return {"error" : "message is not found"}
    
    if message.author_id != author.id:
        return {"error" : "wrong author"}
    
    await message.delete()
    await dm.save(update_fields=["updated_at"])
    await dm.refresh_from_db()

    return {
        "status" : "ok",
        "updated_at" : dm.updated_at
        }


async def edit_message(dm: DirectMessage, author: User, message_id: int, new_content: str):
    message = await Message.get_or_none(id=message_id, dm_id=dm.id)

    if message is None:
        return {"error" : "message is not found"}
    
    if message.author_id != author.id:
        return {"error" : "wrong author"}

    old_content = decrypt_message_text(message.ciphertext, message.nonce, message.key_version)
    if (new_content == old_content):
        return serialize_message(message)
   
    ciphertext, nonce, key_version = encrypt_message_text(new_content)

    message.ciphertext = ciphertext
    message.nonce = nonce
    message.key_version = key_version
    message.edited_at = timezone.now()

    await message.save(update_fields=["ciphertext", "nonce", "key_version", "edited_at"])

    return serialize_message(message)
    
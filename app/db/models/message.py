from __future__ import annotations

from tortoise import fields

from app.db.base import BaseDB


class Message(BaseDB):
    dm = fields.ForeignKeyField(
        "models.DirectMessage", related_name="messages", on_delete=fields.CASCADE
    )
    author = fields.ForeignKeyField(
        "models.User", related_name="messages", on_delete=fields.CASCADE
    )
    ciphertext = fields.BinaryField()
    nonce = fields.BinaryField()
    key_version = fields.IntField(default=1)
    edited_at = fields.DatetimeField(null=True)
    is_pinned = fields.BooleanField(default=False)

    class Meta:
        table = "messages"

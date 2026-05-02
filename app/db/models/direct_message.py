from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import User
    
from tortoise import fields

from app.db.base import BaseDB


class DirectMessage(BaseDB):
    user_low = fields.ForeignKeyField(
        "models.User",
        related_name="direct_messages_as_low",
        on_delete=fields.CASCADE,
    )
    user_high = fields.ForeignKeyField(
        "models.User",
        related_name="direct_messages_as_high",
        on_delete=fields.CASCADE,
    )

    class Meta:
        table = "direct_messages"
        unique_together = (("user_low", "user_high"),)
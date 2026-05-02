from __future__ import annotations

from tortoise import fields

from app.db.base import BaseDB


class AuthToken(BaseDB):
    user = fields.ForeignKeyField("models.User", related_name="auth_tokens", on_delete=fields.CASCADE)
    public_id = fields.CharField(max_length=128, unique=True, db_index=True)
    token_hash = fields.CharField(max_length=64)
    name = fields.CharField(max_length=128)
    last_used_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True)
    is_seed = fields.BooleanField(default=False)

    class Meta:
        table = "auth_tokens"

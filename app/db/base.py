from __future__ import annotations

from tortoise import Model, fields

from app.services.snowflake import generate_snowflake


class BaseDB(Model):
    id = fields.BigIntField(primary_key=True, default=generate_snowflake, generated=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True

from __future__ import annotations

from tortoise import fields

from app.db.base import BaseDB


class User(BaseDB):
    username = fields.CharField(max_length=64, unique=True)
    display_name = fields.CharField(max_length=128)
    is_test_user = fields.BooleanField(default=True)
    hashed_password = fields.CharField(description="hash salt", max_length=256)

    class Meta:
        table = "users"

    
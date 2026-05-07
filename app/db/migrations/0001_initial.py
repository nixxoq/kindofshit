from tortoise import migrations
from tortoise.migrations import operations as ops
from app.services.snowflake import generate_snowflake
from tortoise.fields.base import OnDelete
from tortoise import fields


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    fields.BigIntField(
                        primary_key=True,
                        default=generate_snowflake,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ("username", fields.CharField(unique=True, max_length=64)),
                ("display_name", fields.CharField(max_length=128)),
                ("is_test_user", fields.BooleanField(default=True)),
                (
                    "hashed_password",
                    fields.CharField(description="hash salt", max_length=256),
                ),
                ("is_online", fields.BooleanField(default=False)),
                (
                    "last_seen",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
            ],
            options={"table": "users", "app": "models", "pk_attr": "id"},
            bases=["BaseDB"],
        ),
        ops.CreateModel(
            name="AuthToken",
            fields=[
                (
                    "id",
                    fields.BigIntField(
                        primary_key=True,
                        default=generate_snowflake,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                (
                    "user",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="auth_tokens",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "public_id",
                    fields.CharField(unique=True, db_index=True, max_length=128),
                ),
                ("token_hash", fields.CharField(max_length=64)),
                ("name", fields.CharField(max_length=128)),
                (
                    "last_used_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                (
                    "revoked_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("is_seed", fields.BooleanField(default=False)),
            ],
            options={"table": "auth_tokens", "app": "models", "pk_attr": "id"},
            bases=["BaseDB"],
        ),
        ops.CreateModel(
            name="DirectMessage",
            fields=[
                (
                    "id",
                    fields.BigIntField(
                        primary_key=True,
                        default=generate_snowflake,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                (
                    "user_low",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_low_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="direct_messages_as_low",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "user_high",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_high_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="direct_messages_as_high",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
            ],
            options={
                "table": "direct_messages",
                "app": "models",
                "unique_together": (("user_low", "user_high"),),
                "pk_attr": "id",
            },
            bases=["BaseDB"],
        ),
        ops.CreateModel(
            name="Message",
            fields=[
                (
                    "id",
                    fields.BigIntField(
                        primary_key=True,
                        default=generate_snowflake,
                        unique=True,
                        db_index=True,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                (
                    "dm",
                    fields.ForeignKeyField(
                        "models.DirectMessage",
                        source_field="dm_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="messages",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "author",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="author_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="messages",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("ciphertext", fields.BinaryField()),
                ("nonce", fields.BinaryField()),
                ("key_version", fields.IntField(default=1)),
                (
                    "edited_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("is_pinned", fields.BooleanField(default=False)),
            ],
            options={"table": "messages", "app": "models", "pk_attr": "id"},
            bases=["BaseDB"],
        ),
    ]

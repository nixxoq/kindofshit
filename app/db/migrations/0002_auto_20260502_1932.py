from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0001_initial")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User",
            name="hashed_password",
            field=fields.CharField(description="hash salt", max_length=256),
        ),
    ]

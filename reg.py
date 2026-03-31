import asyncio
from tortoise import Tortoise, fields
from tortoise.models import Model
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

#CONST
PASSWORD_LEN = 255

ph = PasswordHasher()
# Database
class User(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password_hash = fields.CharField(max_length=PASSWORD_LEN)

    def __str__(self):
        return f"{self.id}: {self.username}"
    

# Registration
async def register(username, password):
    user = await User.get_or_none(username=username)
    if user:
        return {"error": "user_exists"}
    
    hashed = ph.hash(password)

    new_user = await User.create(username=username, password_hash=hashed)

    return {"status": "ok", "user_id": new_user.id}


# Login
async def login(username, password):
    user = await User.get_or_none(username=username)

    if not user:
        return {"error": "user_not_found"}

    try:
        ph.verify(user.password_hash, password)

        if ph.check_needs_rehash(user.password_hash):
            user.password_hash = ph.hash(password)
            await user.save()

        return {"status": "ok", "user_id": user.id}

    except VerifyMismatchError:
        return {"error": "wrong_password"}


async def main():
    await Tortoise.init(
        #db_url="postgres://postgres:1234@localhost:5432/mydb",
        db_url="sqlite://db.sqlite3",
        modules={"models": ["__main__"]}
    )

    await Tortoise.generate_schemas()

    await register("max", "1234")
    await login("max", "1234")


asyncio.run(main())
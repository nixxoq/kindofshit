from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from tortoise import timezone

from app.config import get_settings
from app.db.models import AuthToken, User
from app.schemas.account import AccountCreationRequest, LoginPayload
from app.utils import AuthError

ph = PasswordHasher()


async def login(payload: LoginPayload) -> dict:
    user = await User.get_or_none(username=payload.username)

    if not user:
        return {"error": AuthError.USER_NOT_FOUND}

    try:
        ph.verify(user.hashed_password, payload.password)

        if ph.check_needs_rehash(user.hashed_password):
            user.hashed_password = ph.hash(payload.password)
            await user.save(update_fields=["hashed_password"])

        await AuthToken.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )

        token = await create_auth_token(user, name="Login Token")

        return {
            "status": "ok",
            "user_id": user.id,
            "username": user.username,
            "token": token,
        }

    except VerifyMismatchError:
        return {"error": AuthError.WRONG_PASSWORD}


async def register(payload: AccountCreationRequest) -> dict:
    if await User.exists(username=payload.username):
        return {"error": AuthError.USER_EXISTS}

    hashed = ph.hash(password=payload.password)

    new_user = await User.create(
        username=payload.username,
        display_name=payload.display_name,
        hashed_password=hashed,
        is_test_user=False,
    )

    token = await create_auth_token(new_user, name="Registration")

    return {
        "status": "ok",
        "id": new_user.id,
        "created_at": new_user.created_at,
        "token": token,
    }


@dataclass
class AuthenticatedContext:
    user: User
    token: AuthToken


async def create_auth_token(user: User, name: str = "login") -> str:
    public_id = secrets.token_hex(8)
    secret_part = secrets.token_urlsafe(32)
    raw_token = f"kgm_{public_id}.{secret_part}"

    await AuthToken.create(
        user=user,
        public_id=public_id,
        token_hash=hash_token(raw_token=raw_token),
        name=name,
        is_seed=False,
    )

    return raw_token


def hash_token(raw_token: str) -> str:
    secret = get_settings().auth_secret_bytes
    return hmac.new(secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def parse_public_id(raw_token: str) -> str:
    if not raw_token.startswith("kgm_") or "." not in raw_token:
        raise ValueError("Invalid token format")

    prefix, _, _ = raw_token.partition(".")
    public_id = prefix.removeprefix("kgm_")
    if not public_id:
        raise ValueError("Invalid token format")

    return public_id


def extract_raw_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    authorization = authorization.strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return authorization


async def authenticate_token(raw_token: str) -> AuthenticatedContext:
    public_id = parse_public_id(raw_token)

    token = await AuthToken.get_or_none(
        public_id=public_id, revoked_at__isnull=True
    ).select_related("user")
    if token is None:
        raise ValueError("Invalid token")

    if not hmac.compare_digest(token.token_hash, hash_token(raw_token)):
        raise ValueError("Invalid token")

    token.last_used_at = timezone.now()
    await token.save(update_fields=["last_used_at"])
    return AuthenticatedContext(user=token.user, token=token)


async def authenticate_authorization_header(
    authorization: str | None,
) -> AuthenticatedContext:
    raw_token = extract_raw_token(authorization)
    if not raw_token:
        raise ValueError("Missing token")
    return await authenticate_token(raw_token)

from __future__ import annotations

from app.services.auth import hash_token, parse_public_id


def test_parse_public_id() -> None:
    assert parse_public_id("kgm_alice.local-alice-secret-token") == "alice"


def test_hash_token_is_stable() -> None:
    token = "kgm_alice.local-alice-secret-token"
    assert hash_token(token) == hash_token(token)

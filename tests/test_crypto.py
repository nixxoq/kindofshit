from __future__ import annotations

from app.services.crypto import decrypt_message_text, encrypt_message_text


def test_encrypt_decrypt_roundtrip() -> None:
    ciphertext, nonce, key_version = encrypt_message_text("hello kilogram")
    assert ciphertext != b"hello kilogram"
    assert decrypt_message_text(ciphertext, nonce, key_version) == "hello kilogram"

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


def _cipher() -> AESGCM:
    return AESGCM(get_settings().encryption_key_bytes)


def encrypt_message_text(content: str) -> tuple[bytes, bytes, int]:
    nonce = os.urandom(12)
    ciphertext = _cipher().encrypt(nonce, content.encode("utf-8"), None)
    return ciphertext, nonce, 1


def decrypt_message_text(ciphertext: bytes, nonce: bytes, key_version: int) -> str:
    if key_version != 1:
        raise ValueError(f"Unsupported key version: {key_version}")
    plaintext = _cipher().decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")

"""Optional at-rest encryption of embedding blobs (Fernet = AES-128-CBC + HMAC-SHA256).

The key must come from the environment / a secret manager, never from the repository or the database.
"""
from __future__ import annotations

from ..exceptions import ConfigError


class VectorCipher:
    def __init__(self, key: bytes | str):
        try:
            from cryptography.fernet import Fernet
        except ImportError as e:
            raise ConfigError("encryption requested but `cryptography` is not installed "
                              "(pip install cryptography)") from e
        try:
            self._f = Fernet(key)
        except Exception as e:
            raise ConfigError("invalid encryption key (expected a Fernet key; see README)") from e

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._f.decrypt(data)

    @staticmethod
    def generate_key() -> str:
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()

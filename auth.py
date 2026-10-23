"""Credential hashing and validation helpers."""

import hashlib
import hmac
import re
import secrets

PBKDF2_ITERATIONS = 200_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_USERNAMES = {"anonimous", "sar", "sza"}


def hash_password(password, salt=None, iterations=PBKDF2_ITERATIONS):
    """Return ``(hash_hex, salt_hex, iterations)`` for a password."""
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, iterations
    )
    return digest.hex(), salt_bytes.hex(), iterations


def verify_password(password, expected_hash, salt, iterations):
    """Verify a password against its stored hash in constant time."""
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return hmac.compare_digest(digest.hex(), expected_hash)


def validate_username(username):
    """Return whether a username is safe and not reserved."""
    return (
        isinstance(username, str)
        and bool(USERNAME_RE.fullmatch(username))
        and username not in RESERVED_USERNAMES
    )


def validate_password(password):
    """Return whether a password meets the minimum policy."""
    return isinstance(password, str) and len(password) >= 8

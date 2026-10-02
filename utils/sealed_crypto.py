"""Encryption for the fields a sealed consultation hides (RA 11166, RA 10173)."""
import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "enc:v1:"
KEY_BYTES = 32
NONCE_BYTES = 12


class SealedDataError(Exception):
    """A sealed value could not be opened: wrong or missing key, or damaged value."""


def key_problem(value):
    """A short message saying what is wrong with SEALED_DATA_KEY, or None if it is fine."""
    fix = "Run: python setup_env.py   (it adds the key to .env)"
    if not value:
        return "SEALED_DATA_KEY is not set. " + fix
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return "SEALED_DATA_KEY is not valid base64. " + fix
    if len(raw) != KEY_BYTES:
        return f"SEALED_DATA_KEY must be {KEY_BYTES} bytes after decoding. " + fix
    return None


def new_key():
    """A new random key, base64-encoded, for .env."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def _key():
    # Read on each call, so a test can swap the key without reloading modules.
    value = os.environ.get("SEALED_DATA_KEY", "")
    if key_problem(value):
        raise SealedDataError("SEALED_DATA_KEY is missing or invalid.")
    return base64.b64decode(value)


def _associated_data(row_id, field, table="consultations"):
    return f"{table}:{int(row_id)}:{field}".encode("utf-8")


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(plaintext, row_id, field, table="consultations"):
    """Encrypt one field value. None and "" stay as they are: there is nothing to hide.

    Always encrypts what it is given. A caller that may meet a value that is
    already encrypted checks is_encrypted() first, so a value copied from
    another row can never be stored as though it belonged here.
    """
    if plaintext is None or plaintext == "":
        return plaintext
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_key()).encrypt(
        nonce, str(plaintext).encode("utf-8"), _associated_data(row_id, field, table)
    )
    return PREFIX + base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(token, row_id, field, table="consultations"):
    """Decrypt one stored value. Raises SealedDataError if it cannot be opened."""
    if token is None or token == "" or not is_encrypted(token):
        return token
    try:
        raw = base64.b64decode(token[len(PREFIX):], validate=True)
    except (binascii.Error, ValueError) as error:
        raise SealedDataError("The stored value is damaged.") from error
    if len(raw) <= NONCE_BYTES:
        raise SealedDataError("The stored value is damaged.")
    try:
        plain = AESGCM(_key()).decrypt(
            raw[:NONCE_BYTES], raw[NONCE_BYTES:], _associated_data(row_id, field, table)
        )
    except InvalidTag as error:
        raise SealedDataError("The key does not open this value.") from error
    return plain.decode("utf-8")

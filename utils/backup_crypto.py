"""Encryption for backup files (Task 5c, M25)."""
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from utils import sealed_crypto

MAGIC = b"IDSBAK1"
NONCE_BYTES = 12
EXTENSION = ".idsbackup"
HKDF_INFO = b"ids-bphcsn-backup-v1"


def backup_key():
    """The 32-byte backup key, derived from SEALED_DATA_KEY."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=HKDF_INFO).derive(sealed_crypto._key())


def encrypt_backup(data):
    """The bytes of an .idsbackup file holding `data`."""
    nonce = os.urandom(NONCE_BYTES)
    return MAGIC + nonce + AESGCM(backup_key()).encrypt(nonce, data, MAGIC)

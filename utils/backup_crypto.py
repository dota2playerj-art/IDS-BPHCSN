"""Encryption for backup files (Task 5c, M25).

The Administrator's backup download is the whole database. It used to be served
as a plain SQLite file, so anyone holding it could read every patient's record
with a database tool. It is now encrypted as one block:

    IDSBAK1 | 12-byte nonce | AES-256-GCM ciphertext and tag

The header is the associated data, so a file with a changed header does not
open. The extension is .idsbackup.

THE KEY. One key and one envelope for the team: the backup key is derived from
SEALED_DATA_KEY with HKDF-SHA256 (info "ids-bphcsn-backup-v1"). It is a
different key from the one that seals fields, so the two uses never share a key,
and nothing about how sealed fields are encrypted changes.

THE APP ONLY ENCRYPTS. Opening a backup is done by hand at the health-center PC
with restore_backup.py, which is not part of the web app. So no screen can open
a backup, and models/consultations.py open_sealed_value() is still the only
code in the app that decrypts anything.
"""
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

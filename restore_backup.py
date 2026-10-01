"""Open an encrypted backup (.idsbackup) at the health-center computer.

usage:
    python restore_backup.py <file.idsbackup>              decrypt and check only
    python restore_backup.py <file.idsbackup> --replace    then replace app.db

Run it from the project folder, on a computer whose .env holds this system's
SEALED_DATA_KEY (the key in the Doctor's envelope). The backup key is derived
from it, as utils/backup_crypto.py explains.

WHAT IT DOES
------------
1. Decrypts the file into a NEW database in the IDS-BPHCSN-backups folder next
   to the project. app.db is not touched.
2. Runs PRAGMA integrity_check on that new file and says what SQLite answered.
3. Only with --replace, and only when the check says "ok": copies the current
   app.db into IDS-BPHCSN-backups first, then replaces app.db with the restored
   copy, and tells you to restart the app.

A wrong key or a damaged file gives one plain line and changes nothing.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import config  # loads .env into the environment
from utils import sealed_crypto
from utils.backup_crypto import MAGIC, NONCE_BYTES, backup_key

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
CANNOT_OPEN = ("Could not open this backup: the key on this computer does not "
               "match it, or the file is damaged. Nothing was changed.")


class RestoreError(Exception):
    """A plain sentence saying why the backup could not be restored."""


def decrypt_backup(data):
    """The database bytes inside an .idsbackup file. Raises RestoreError."""
    if not data.startswith(MAGIC) or len(data) <= len(MAGIC) + NONCE_BYTES:
        raise RestoreError("This is not an IDS-BPHCSN backup file (.idsbackup). "
                           "Nothing was changed.")
    problem = sealed_crypto.key_problem(os.environ.get("SEALED_DATA_KEY", ""))
    if problem:
        raise RestoreError(problem)
    nonce = data[len(MAGIC):len(MAGIC) + NONCE_BYTES]
    try:
        return AESGCM(backup_key()).decrypt(nonce, data[len(MAGIC) + NONCE_BYTES:], MAGIC)
    except InvalidTag as error:
        raise RestoreError(CANNOT_OPEN) from error


def _integrity(path):
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("PRAGMA integrity_check")]
    finally:
        conn.close()


def _copy_database(source_path, target_path):
    """Copy one SQLite database onto another with SQLite's own backup interface."""
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def restore(backup_file, replace=False, backup_dir=BACKUP_DIR, database=None, say=print):
    """Decrypt, check and optionally restore one backup. Returns an exit code."""
    database = database or config.DATABASE
    backup_dir = Path(backup_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        data = Path(backup_file).read_bytes()
    except OSError:
        say(f"Could not read {backup_file}. Nothing was changed.")
        return 1
    try:
        plain = decrypt_backup(data)
    except RestoreError as error:
        say(str(error))
        return 1

    backup_dir.mkdir(parents=True, exist_ok=True)
    restored = backup_dir / f"restored_{Path(backup_file).stem}_{stamp}.db"
    restored.write_bytes(plain)
    say(f"Decrypted into {restored}")
    result = _integrity(restored)
    if result != ["ok"]:
        say("integrity_check: FAILED — " + "; ".join(result[:5]))
        say("app.db was not replaced.")
        return 1
    say("integrity_check: ok")

    if not replace:
        say("app.db was not changed. To use this copy, run this again with --replace.")
        return 0

    before = backup_dir / f"{Path(database).name}.PRERESTORE_BACKUP_{stamp}"
    _copy_database(database, before)
    say(f"Copied the current app.db to {before}")
    _copy_database(restored, database)
    say("app.db now holds the restored backup. Restart the app now.")
    return 0


def main(argv):
    args = [a for a in argv if a != "--replace"]
    if len(args) != 1:
        print("usage: python restore_backup.py <file.idsbackup> [--replace]")
        return 2
    return restore(args[0], replace="--replace" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

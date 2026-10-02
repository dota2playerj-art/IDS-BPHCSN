"""Encrypt every old plain database, check the copy, then remove the plain file.

Run it from the project folder, on a computer whose .env holds this system's
SEALED_DATA_KEY. It prints counts only, never a name or a value.
"""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import config  # loads .env into the environment
from models.backup import create_backup_bytes
from restore_backup import RestoreError, decrypt_backup
from utils.backup_crypto import EXTENSION, encrypt_backup

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
PREVIOUS_NAME = "previous-app.db"
INDEX_NAME = "archive_index.json"
SQLITE_HEADER = b"SQLite format 3\x00"

# seed_demo_data.py sets PRAGMA user_version to this number on the database it
# builds. It is how this script tells the fictional demo database from one that
# may hold real people. The app never reads user_version.
DEMO_MARKER = 5001


def is_plain_sqlite(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def is_demo_database(path):
    try:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("PRAGMA user_version").fetchone()[0] == DEMO_MARKER
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def fingerprint(path):
    """({table: row count}, hash of every table's rows) of one database file.

    The rows are sorted before hashing, so a copy that was compacted and had its
    rows stored in another order still matches when the contents are the same.
    """
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        names = sorted(row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        counts, digest = {}, hashlib.sha256()
        for name in names:
            rows = sorted(repr(tuple(row)) for row in conn.execute(f'SELECT * FROM "{name}"'))
            counts[name] = len(rows)
            digest.update(name.encode())
            for row in rows:
                digest.update(row.encode("utf-8", "replace"))
        return counts, digest.hexdigest()
    finally:
        conn.close()


def _integrity_ok(path):
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("PRAGMA integrity_check")] == ["ok"]
    finally:
        conn.close()


def verify_archive(archive_path, original_path):
    """True when the archive decrypts to a sound database with the original's contents."""
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp = handle.name
    handle.close()
    try:
        try:
            Path(temp).write_bytes(decrypt_backup(Path(archive_path).read_bytes()))
        except (RestoreError, OSError):
            return False
        try:
            return _integrity_ok(temp) and fingerprint(temp) == fingerprint(original_path)
        except sqlite3.Error:
            return False
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass


def _load_index(backup_dir):
    path = Path(backup_dir) / INDEX_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"archives": []}


def _save_index(backup_dir, index):
    (Path(backup_dir) / INDEX_NAME).write_text(
        json.dumps(index, indent=1), encoding="utf-8")


def _existing_archive(backup_dir, index, content_hash):
    for entry in index["archives"]:
        if entry["hash"] == content_hash and (Path(backup_dir) / entry["name"]).exists():
            return Path(backup_dir) / entry["name"]
    return None


def archive_file(path, backup_dir):
    """Archive and verify one plain file. Returns (archive path or None, status).

    status is "archived", "already archived" or "failed". Nothing is removed here.
    """
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    index = _load_index(backup_dir)
    try:
        _, content_hash = fingerprint(path)
    except sqlite3.Error:
        return None, "failed"

    existing = _existing_archive(backup_dir, index, content_hash)
    if existing is not None:
        if verify_archive(existing, path):
            return existing, "already archived"
        return None, "failed"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"archive-{Path(path).name}-{stamp}{EXTENSION}"
    try:
        target.write_bytes(encrypt_backup(create_backup_bytes(path)))
    except (OSError, RuntimeError, sqlite3.Error):
        target.unlink(missing_ok=True)
        return None, "failed"
    if not verify_archive(target, path):
        return target, "failed"
    index["archives"].append({"hash": content_hash, "name": target.name})
    _save_index(backup_dir, index)
    return target, "archived"


def candidates(project=PROJECT, backup_dir=BACKUP_DIR):
    """The plain SQLite files to archive: (path, is_app_db)."""
    found = []
    app_db = Path(project) / "app.db"
    if app_db.exists() and is_plain_sqlite(app_db) and not is_demo_database(app_db):
        found.append((app_db, True))
    backup_dir = Path(backup_dir)
    if backup_dir.is_dir():
        for path in sorted(backup_dir.iterdir()):
            if (path.is_file() and path.suffix != EXTENSION and path.name != PREVIOUS_NAME
                    and path.name != INDEX_NAME and is_plain_sqlite(path)):
                found.append((path, False))
    return found


def run(project=PROJECT, backup_dir=BACKUP_DIR, remove_previous=False, say=print):
    """Archive what is found. Returns the counts as a dict."""
    backup_dir = Path(backup_dir)
    counts = {"found": 0, "archived": 0, "verified": 0, "removed": 0, "failed": 0}

    if remove_previous:
        previous = backup_dir / PREVIOUS_NAME
        if previous.exists():
            counts["found"] = 1
            archive, status = archive_file(previous, backup_dir)
            if status == "failed":
                counts["failed"] = 1
            else:
                counts["archived"] += status == "archived"
                counts["verified"] = 1
                previous.unlink()
                counts["removed"] = 1
    else:
        for path, is_app_db in candidates(project, backup_dir):
            counts["found"] += 1
            archive, status = archive_file(path, backup_dir)
            if status == "failed":
                counts["failed"] += 1
                continue
            counts["archived"] += status == "archived"
            counts["verified"] += 1
            if is_app_db:
                # Not deleted: moved aside, so the demo database can be built.
                previous = backup_dir / PREVIOUS_NAME
                if previous.exists():
                    previous.unlink()
                os.replace(path, previous)
            else:
                path.unlink()
            counts["removed"] += 1

    say("files found: {found}, archived: {archived}, verified: {verified}, "
        "removed: {removed}, failed: {failed}".format(**counts))
    if counts["failed"]:
        say("Files that failed the check were kept as they are.")
    return counts


def main(argv):
    if any(a not in ("--remove-previous",) for a in argv):
        print("usage: python archive_plain_databases.py [--remove-previous]")
        return 2
    counts = run(remove_previous="--remove-previous" in argv)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

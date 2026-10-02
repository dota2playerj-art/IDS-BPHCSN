"""Taking a consistent copy of the database while the system is running.

This project makes that easy to hit rather than unlikely. database/connection.py
opens a NEW connection per call and closes it after, so a request that saves a
consultation and a request that downloads a backup are two connections to the
same file with no coordination between them beyond SQLite's own locking -- and
utils/unavailable.py's `backup` reason said exactly this, that doing it from the
screen "needs a job that can copy the file safely while the system is running".
"""
import os
import sqlite3
import tempfile

from flask import current_app, has_app_context

import config

# SQLite answers PRAGMA integrity_check with exactly this single row when the
# database is sound, and with one row per problem when it is not.
_INTEGRITY_OK = "ok"


def database_path():
    """The file being backed up, resolved the way every query resolves it.

    Deliberately the same rule database/connection.py uses -- the running app's
    configuration inside an app context, config.DATABASE outside one -- so a
    backup cannot be taken of a different file from the one the request just read
    its figures out of.
    """
    if has_app_context():
        return current_app.config["DATABASE"]
    return config.DATABASE


def database_size_bytes():
    """How large the live database is right now, or None if it cannot be read.

    This is what Screen 13 shows in place of the "248 MB" that used to sit under
    Backup Size -- a figure nothing had measured, on a file of well under a
    megabyte. It is the size of the source rather than of any copy; the backup is
    the same set of pages, so it is within a page or two of what a download will
    weigh, and the screen says which of the two it is measuring.
    """
    try:
        return os.path.getsize(database_path())
    except OSError:
        return None


def format_size(size):
    """1234567 -> '1.2 MB'. None -> None, so a caller can render its own absence."""
    if size is None:
        return None
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _integrity_problems(path):
    """[] when SQLite says the database at `path` is sound; the complaints if not."""
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows if row[0] != _INTEGRITY_OK]


def create_backup_bytes(path=None):
    """A verified, consistent copy of the database. Returns bytes.

    Raises RuntimeError if the copy fails its own integrity check, which is the
    one outcome that must never be served: a corrupt backup handed over as a good
    one is the failure this whole module exists to avoid.

    `path` names another database to copy. archive_plain_databases.py passes one,
    so an old file is compacted, checked and encrypted by exactly this code. The
    web app never passes it: the default is the live database.

    The temporary file is removed in a finally block, so it does not survive an
    exception either. It is created with delete=False and closed immediately
    because sqlite3.connect() needs to open the path itself -- Windows will not
    let a second handle open a file NamedTemporaryFile is still holding.
    """
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_path = handle.name
    handle.close()

    source = sqlite3.connect(path or database_path())
    try:
        destination = sqlite3.connect(temp_path)
        try:
            # pages=0 means "the whole database in one step". See the module note.
            source.backup(destination, pages=0)
            # Rebuild the copy so it holds live rows only. A page copy also
            # carries free space, which can still hold old text, such as a
            # diagnosis from before it was sealed and encrypted.
            destination.execute("VACUUM")
        finally:
            destination.close()
    finally:
        source.close()

    try:
        problems = _integrity_problems(temp_path)
        if problems:
            raise RuntimeError(
                "The backup copy failed SQLite's integrity check and was not "
                "served: " + "; ".join(problems)
            )
        with open(temp_path, "rb") as copy:
            return copy.read()
    finally:
        # Removed whether the check passed, failed, or raised. A file holding
        # every patient record in the system must not be left in the temp
        # directory because a response went wrong.
        try:
            os.unlink(temp_path)
        except OSError:
            pass

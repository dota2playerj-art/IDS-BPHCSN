"""Taking a consistent copy of the database while the system is running.

WHY THIS IS NOT shutil.copyfile()
----------------------------------
An SQLite database is not a file you can copy at an arbitrary moment and expect
to be able to open. A write is a sequence of page writes plus a journal, and a
plain byte-for-byte copy taken partway through one produces a file whose pages
come from two different points in time -- the classic outcome is a copy that
opens, reads normally for a while, and then reports "database disk image is
malformed" against the one table somebody needed. Worse, the failure is silent
at copy time: nothing about the copy operation reports that it caught the
database mid-write, so the first anybody knows is when the backup is needed.

This project makes that easy to hit rather than unlikely. database/connection.py
opens a NEW connection per call and closes it after, so a request that saves a
consultation and a request that downloads a backup are two connections to the
same file with no coordination between them beyond SQLite's own locking -- and
utils/unavailable.py's `backup` reason said exactly this, that doing it from the
screen "needs a job that can copy the file safely while the system is running".

SQLite HAS THAT JOB, AND IT IS THE ONLINE BACKUP API
-----------------------------------------------------
sqlite3.Connection.backup() drives SQLite's own backup interface
(sqlite3_backup_step). It copies page by page from inside the database engine,
holding a read lock while it works, and if another connection writes to the
source during the copy the backup restarts from the beginning rather than
producing a mixed file. What comes out is a complete database as of a single
consistent point -- never half of one write. It is the method SQLite's own
documentation names for backing up a live database, and it needs no scheduler,
no exclusive lock on the application, and no downtime.

The whole copy happens in one step here -- `pages=0` copies the database in a
single call rather than in slices with sleeps between them. That choice is about
size: app.db is well under a megabyte, so a single step is milliseconds, and
stepping it would mean holding the operation open longer for no benefit. A
database large enough for that to matter would be a different decision.

AND THE COPY IS CHECKED BEFORE IT IS HANDED OVER
-------------------------------------------------
create_backup_bytes() runs PRAGMA integrity_check on the finished copy and
refuses to return it if SQLite does not answer "ok". This is cheap at this size
and it closes the one gap the paragraphs above cannot: the reason a naive copy is
dangerous is that its damage is invisible until the file is needed, so a backup
routine that never verifies its own output has the same defect however carefully
it was made. A backup that cannot be opened is worse than no backup, because it
is believed in.

WHY IT GOES THROUGH A TEMPORARY FILE AND COMES BACK AS BYTES
-------------------------------------------------------------
The backup API writes into a database, and a database needs a path -- so the
copy is made to a temporary file, verified there, read into memory, and the
temporary file is deleted before anything is sent. Serving the bytes rather than
the path means there is no window in which a file holding every patient record
sits in the system temp directory waiting for a response to finish streaming,
and no cleanup that can be skipped if the response fails.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It does not restore. Reading a database out is a copy; writing one back in
replaces every patient record in the system with whatever was in the uploaded
file, and doing that from a web form -- with no verification of what was
uploaded, no way to undo it, and the running application holding open
connections to the file being replaced -- is a different and far more dangerous
piece of work. The Restore control on Screen 13 stays disabled and now says so
in those terms.

It also does not schedule. Nothing in this project runs on a timer; there is no
scheduler, no cron entry and no job for one to run, which is why the Backup
Schedule row on that screen reads None rather than a frequency.
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


def create_backup_bytes():
    """A verified, consistent copy of the database. Returns bytes.

    Raises RuntimeError if the copy fails its own integrity check, which is the
    one outcome that must never be served: a corrupt backup handed over as a good
    one is the failure this whole module exists to avoid.

    The temporary file is removed in a finally block, so it does not survive an
    exception either. It is created with delete=False and closed immediately
    because sqlite3.connect() needs to open the path itself -- Windows will not
    let a second handle open a file NamedTemporaryFile is still holding.
    """
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_path = handle.name
    handle.close()

    source = sqlite3.connect(database_path())
    try:
        destination = sqlite3.connect(temp_path)
        try:
            # pages=0 means "the whole database in one step". See the module note.
            source.backup(destination, pages=0)
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

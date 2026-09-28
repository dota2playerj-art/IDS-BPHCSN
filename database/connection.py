"""SQLite connection handling."""
import sqlite3
from contextlib import contextmanager

from flask import current_app, has_app_context

import config


def _database_path():
    """Resolve the database file.

    Inside a request (or any app context) the running app's configuration wins, so
    a test or a future instance config can point somewhere else. Outside one --
    populate_records.py runs as a plain script -- fall back to the project default.
    """
    if has_app_context():
        return current_app.config["DATABASE"]
    return config.DATABASE


def _schema_path():
    if has_app_context():
        return current_app.config["SCHEMA"]
    return config.SCHEMA


def get_db():
    """Open a new connection. Use db_connection() instead: it always closes it."""
    conn = sqlite3.connect(_database_path())
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_connection():
    """Open a connection for one block of work, and always close it.

        with db_connection() as conn:
            conn.execute(...)
            conn.commit()

    The caller still commits, exactly as before. Nothing is committed here.

    If the block raises, any write not yet committed is rolled back, and the
    connection is closed before the error goes on. An open connection with an
    unfinished write holds SQLite's write lock, so leaving one open made every
    later write fail with "database is locked".
    """
    conn = get_db()
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

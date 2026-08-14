"""SQLite connection handling."""
import sqlite3

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
    conn = sqlite3.connect(_database_path())
    conn.row_factory = sqlite3.Row
    return conn

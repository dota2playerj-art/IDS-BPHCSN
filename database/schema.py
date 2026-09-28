"""Schema creation and first-run bootstrap."""
import os

from database.connection import _database_path, _schema_path, db_connection


def init_db():
    """Create every table from schema.sql the first time the app runs.

    A no-op once app.db exists, which is the case on every request after the
    first. Behaviour is unchanged from the original single-file app.py.
    """
    if not os.path.exists(_database_path()):
        with db_connection() as conn:
            with open(_schema_path(), "r", encoding="utf-8") as handle:
                conn.executescript(handle.read())
            conn.commit()
        # Imported here rather than at module scope: models.users reads from this
        # package, so a top-level import would tie the two together at import time
        # purely for one bootstrap call.
        from models.users import seed_demo_users

        seed_demo_users()

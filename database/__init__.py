"""Database access layer: connection handling and schema initialisation."""
from database.connection import get_db
from database.schema import init_db

__all__ = ["get_db", "init_db"]

"""Application configuration.

Kept as a plain module so it can be consumed two ways: Flask picks up the
upper-case names via ``app.config.from_object(config)``, and standalone scripts
(``populate_records.py``) import the paths directly without booting the app.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.environ.get("SECRET_KEY", "ids-bphcsn-dev-secret")
DATABASE = os.path.join(BASE_DIR, "app.db")
SCHEMA = os.path.join(BASE_DIR, "schema.sql")

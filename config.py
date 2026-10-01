"""Application configuration.

Kept as a plain module so it can be consumed two ways: Flask picks up the
upper-case names via ``app.config.from_object(config)``, and standalone scripts
(``populate_records.py``) import the paths directly without booting the app.

Secrets come from the environment, never from this file. A .env file in the
project folder is read at import. Run ``python setup_env.py`` once to create it.
A value already set in the environment wins over the .env file.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Checked by secret_key_problem() when the app starts. There is no fallback:
# a key written in the code is a key everyone with the code knows.
SECRET_KEY = os.environ.get("SECRET_KEY", "")
SECRET_KEY_MIN_LENGTH = 32
# The value this file used to fall back to. It is public, so it is refused.
_OLD_FALLBACK_KEY = "ids-bphcsn-dev-secret"

# SEALED_DATA_KEY, the key for sealed consultation fields, is also read from
# .env, but only by utils/sealed_crypto.py. It is kept apart from SECRET_KEY,
# so a new session key can never make medical records unreadable.

# Debug mode shows code, and lets code run from the browser, when an error
# happens. It is on only when IDS_DEBUG is exactly 1. Anything else is off.
DEBUG = os.environ.get("IDS_DEBUG", "").strip() == "1"

DATABASE = os.path.join(BASE_DIR, "app.db")
SCHEMA = os.path.join(BASE_DIR, "schema.sql")

# Session limits. The server enforces them on every request (utils/security.py).
# The computers are shared, so a session must not stay open for the next person.
# Small-count rule (Task 5d). For the Administrator and the Barangay Official, a
# row of a ranking by diagnosis, complaint, condition or medicine whose count is
# from 1 up to one less than this folds into one "Other" row. A count of 1 over a
# short date range can point at one person. See utils/small_counts.py.
SMALL_COUNT_THRESHOLD = 5

# Signed out after this long with no activity.
IDLE_TIMEOUT = timedelta(minutes=30)
# Signed out this long after signing in, whatever happens.
ABSOLUTE_TIMEOUT = timedelta(hours=12)
# The browser shows "Are you still there?" this long before the idle limit.
IDLE_WARNING = timedelta(minutes=2)
# The browser sends at most one keep-alive in this time while the user is active.
KEEPALIVE_INTERVAL = timedelta(minutes=5)
# How long the form token (CSRF, utils/csrf.py) on a page stays valid. As long
# as the longest session, so a token never runs out while its session is open.
# The session limits above still end the session itself.
WTF_CSRF_TIME_LIMIT = int(ABSOLUTE_TIMEOUT.total_seconds())


def secret_key_problem(value):
    """A short message saying what is wrong with a SECRET_KEY, or None if it is fine."""
    fix = "Run: python setup_env.py   (it creates a .env file with a new key)"
    if not value:
        return "SECRET_KEY is not set. " + fix
    if value == _OLD_FALLBACK_KEY:
        return "SECRET_KEY is the old public default. " + fix
    if len(value) < SECRET_KEY_MIN_LENGTH:
        return (f"SECRET_KEY is too short. It needs at least "
                f"{SECRET_KEY_MIN_LENGTH} characters. " + fix)
    return None

"""Shared setup for every suite in tests/.

Every suite imports this module FIRST, before it imports anything from the app.
"""
import atexit
import base64
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

# The tests make their own secret key, so they never need a .env file. Set
# before config is imported. A .env file never overrides a value already set.
os.environ["SECRET_KEY"] = secrets.token_hex(32)
os.environ["IDS_DEBUG"] = "0"
# The same for the sealed-record key: a test-only key, never the one in .env.
os.environ["SEALED_DATA_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")

REPO = Path(__file__).resolve().parent.parent
LIVE_DB = REPO / "app.db"
SCHEMA = REPO / "schema.sql"

# run_all.py stops the whole run when a suite exits with this code.
GUARD_EXIT_CODE = 97

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------
def guard_path(path):
    """Stop the run at once if `path` is the live database or is in the project.

    The test database must live in a temporary folder outside the project. A
    path inside the project could be app.db itself, or a file someone might
    commit by mistake. Both are refused.
    """
    resolved = Path(path).resolve()
    live = LIVE_DB.resolve()
    if resolved == live or REPO in resolved.parents:
        message = (
            "\n" + "!" * 78 + "\n"
            "STOPPED: a test tried to use a database inside the project folder.\n"
            f"  path given:    {resolved}\n"
            f"  live database: {live}\n"
            "Tests must only use the temporary database made by tests/_support.py.\n"
            "Nothing was run against this path.\n" + "!" * 78
        )
        print(message, flush=True)
        _stop()
    return str(resolved)


def _stop():
    """Leave at once with GUARD_EXIT_CODE, after removing our own temp folder."""
    if globals().get("_OWN_DIR"):
        shutil.rmtree(globals()["TEST_DIR"], ignore_errors=True)
    os._exit(GUARD_EXIT_CODE)


def attach(app):
    """Check that a created app and the config module both use the test database.

    Call this right after the suite creates or imports its app. It stops the run
    if either one points anywhere else.
    """
    import config

    for label, value in (("app.config['DATABASE']", app.config.get("DATABASE")),
                         ("config.DATABASE", config.DATABASE)):
        if value is None or Path(value).resolve() != Path(DB_PATH).resolve():
            print(f"STOPPED: {label} is {value!r}, not the test database "
                  f"{DB_PATH!r}.", flush=True)
            _stop()
        guard_path(value)
    return app


# ---------------------------------------------------------------------------
# Test accounts. Test-only passwords, used nowhere else.
# ---------------------------------------------------------------------------
# The ids match the demo database the suites were first written against
# (1 Administrator, 2 Staff, 3 Official, 4 a second Staff account, 5 Doctor),
# because several suites address accounts by id.
ACCOUNTS = [
    # id, username, full name, role, password
    (1, "admin", "Kagawad Juan Dela Cruz", "Admin", "TestOnly-Admin-Key-8841"),
    (2, "staff", "Health Center Staff", "Health Center Staff", "TestOnly-Staff-Key-5127"),
    (3, "official", "Barangay Official", "Barangay Official", "TestOnly-Official-Key-3390"),
    (4, "bhwtest", "Test Health Worker", "Health Center Staff", "TestOnly-Bhw-Key-6602"),
    (5, "doctor", "RHU Physician (demo)", "Doctor", "TestOnly-Doctor-Key-7215"),
]
PASSWORDS = {username: password for _, username, _, _, password in ACCOUNTS}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
TODAY = date.today()

# id, first name, last name, birth date, sex, status. Ids are fixed because
# some suites name a patient by id (8, 12 and 16 in the dispensing suite).
PATIENTS = [
    (1, "Maria", "Santos", "1985-03-14", "Female", "Active"),
    (2, "Jose", "Reyes", "1978-07-02", "Male", "Active"),
    (3, "Ana", "Cruz", "1992-11-20", "Female", "Active"),
    (4, "Pedro", "Bautista", "1969-01-09", "Male", "Active"),
    (5, "Rosa", "Garcia", "1988-05-30", "Female", "Active"),
    (6, "Carlos", "Mendoza", "1975-09-12", "Male", "Active"),
    (7, "Liza", "Torres", "1990-02-25", "Female", "Active"),
    (8, "Ramon", "Flores", "1982-12-03", "Male", "Active"),
    (9, "Elena", "Ramos", "1995-06-18", "Female", "Active"),
    (10, "Miguel", "Aquino", "1972-04-07", "Male", "Active"),
    (11, "Teresa", "Villanueva", "1965-08-22", "Female", "Active"),
    (12, "Andres", "Castillo", "1987-10-15", "Male", "Active"),
    (13, "Grace", "Navarro", "1999-01-30", "Female", "Active"),
    (14, "Roberto", "Dela Cruz", "1958-03-11", "Male", "Active"),
    # A young child: the paediatric form and the EPI schedule apply.
    (15, "Sofia", "Lim", (TODAY - timedelta(days=3 * 365)).isoformat(), "Female", "Active"),
    (16, "Daniel", "Soriano", "1984-07-19", "Male", "Active"),
    # An infant under one year old: the EPI suite needs one.
    (17, "Paolo", "Morales", (TODAY - timedelta(days=120)).isoformat(), "Male", "Active"),
    (18, "Carmen", "Pascual", "1950-11-05", "Female", "Inactive"),
    (19, "Ernesto", "Salazar", "1940-06-14", "Male", "Deceased"),
    # The last Active patient is an adult: the staff suite picks the highest id.
    (20, "Isabel", "Fernandez", "1993-09-09", "Female", "Active"),
]

# The medicines on the shelf. Ten with plenty of stock, one supply, one that is
# low on stock, and one that has expired (the dispensing suite needs both).
INVENTORY = [
    # code, generic name (item name for a supply), strength (size), form, category, unit,
    # stock, low threshold, expiry. Each item has one batch, lot "B-<code>".
    ("MED-001", "Paracetamol", "500 mg", "tablet", "Medicine", "tablet", 900, 100, "2028-06-30"),
    ("MED-002", "Amoxicillin", "500 mg", "capsule", "Medicine", "capsule", 850, 100, "2028-03-31"),
    ("MED-003", "Cetirizine", "10 mg", "tablet", "Medicine", "tablet", 800, 50, "2028-01-31"),
    ("MED-004", "Losartan", "50 mg", "tablet", "Medicine", "tablet", 750, 50, "2027-12-31"),
    ("MED-005", "Metformin", "500 mg", "tablet", "Medicine", "tablet", 700, 50, "2027-11-30"),
    ("MED-006", "Amlodipine", "5 mg", "tablet", "Medicine", "tablet", 650, 50, "2027-10-31"),
    ("MED-007", "Ascorbic acid", "500 mg", "tablet", "Medicine", "tablet", 600, 50, "2027-09-30"),
    ("MED-008", "Oral rehydration salts", "20.5 g", "sachet", "Medicine", "sachet", 550, 50, "2027-08-31"),
    ("MED-009", "Mefenamic acid", "500 mg", "capsule", "Medicine", "capsule", 500, 50, "2027-07-31"),
    ("MED-010", "Salbutamol", "2 mg", "tablet", "Medicine", "tablet", 450, 50, "2027-06-30"),
    ("SUP-001", "Cotton balls", "", None, "Supply", "pack", 300, 20, None),
    ("MED-011", "Ferrous sulfate", "325 mg", "tablet", "Medicine", "tablet", 4, 30, "2027-05-31"),
    ("MED-012", "Lagundi", "60 mL", "syrup", "Medicine", "bottle", 40, 10, "2024-12-31"),
]

DIAGNOSES = [
    ("Acute upper respiratory infection", "Rest, fluids, paracetamol as needed"),
    ("Essential hypertension", "Continue losartan; recheck blood pressure in two weeks"),
    ("Type 2 diabetes mellitus", "Continue metformin; diet counselling"),
    ("Acute gastroenteritis", "Oral rehydration salts; return if symptoms worsen"),
    ("Allergic rhinitis", "Cetirizine once daily for seven days"),
    ("Muscle strain", "Warm compress; mefenamic acid for pain"),
    ("Iron deficiency anaemia", "Ferrous sulfate daily; recheck in one month"),
]
COMPLAINTS = [
    "Cough and colds for three days",
    "Headache and dizziness",
    "Follow-up for blood sugar",
    "Loose stools since yesterday",
    "Sneezing and itchy eyes",
    "Lower back pain",
    "Easy fatigue",
]

CONSULTATION_COUNT = 37
ADULT_PATIENTS = [p[0] for p in PATIENTS if p[5] == "Active" and p[0] not in (15, 17)]


def _consultation_patient(consultation_id):
    # Consultations 34, 36 and 37 are named by the Doctor-role suite, and it
    # expects them on three different patients.
    fixed = {34: 5, 36: 6, 37: 7}
    if consultation_id in fixed:
        return fixed[consultation_id]
    return ADULT_PATIENTS[(consultation_id - 1) % len(ADULT_PATIENTS)]


def _consultation_date(consultation_id):
    # Every consultation gets its own past date, so a one-day report range
    # holds exactly the visits a suite put there. 2026-08-28 is never used,
    # because the Doctor-role suite moves three visits onto that day.
    return (date(2026, 6, 1) + timedelta(days=consultation_id)).isoformat()


def build_fixture_database(path):
    """Create the schema and the fixture rows in a new database at `path`."""
    guard_path(path)
    if os.path.exists(path):
        raise RuntimeError(f"refusing to build over an existing file: {path}")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    for user_id, username, full_name, role, password in ACCOUNTS:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, full_name, role, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, username, generate_password_hash(password), full_name, role),
        )

    for patient_id, first, last, birth, sex, status in PATIENTS:
        conn.execute(
            "INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, "
            "sex, civil_status, address, municipality, province, contact_number, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (patient_id, f"PAT-{patient_id:03d}", first, last, birth, sex,
             "Single", "Purok 1, Barangay Poblacion", "San Francisco",
             "Surigao del Norte", f"0900000{patient_id:04d}", status),
        )

    for code, generic, strength, form, category, unit, stock, threshold, expiry in INVENTORY:
        name = " ".join(part for part in (generic, strength, form) if part)
        cursor = conn.execute(
            "INSERT INTO inventory_items (item_code, name, generic_name, category, "
            "dosage_strength, dosage_form, unit, low_stock_threshold, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active')",
            (code, name, generic, category, strength or None, form, unit, threshold),
        )
        conn.execute(
            "INSERT INTO inventory_batches (inventory_item_id, lot_number, expiry_date, "
            "quantity_received, quantity_remaining, date_received, source) "
            "VALUES (?, ?, ?, ?, ?, '2026-05-15', 'DOH')",
            (cursor.lastrowid, f"B-{code}", expiry, stock, stock),
        )

    for cid in range(1, CONSULTATION_COUNT + 1):
        patient_id = _consultation_patient(cid)
        day = _consultation_date(cid)
        diagnosis, plan = DIAGNOSES[(cid - 1) % len(DIAGNOSES)]
        complaint = COMPLAINTS[(cid - 1) % len(COMPLAINTS)]
        conn.execute(
            "INSERT INTO appointments (id, patient_id, scheduled_by, appointment_type, "
            "appointment_date, appointment_time, status, is_walkin, checked_in_at) "
            "VALUES (?, ?, 2, 'Walk-in Consultation', ?, '09:00', 'Completed', 1, ?)",
            (cid, patient_id, day, f"{day} 09:00:00"),
        )
        conn.execute(
            "INSERT INTO consultations (id, patient_id, recorded_by, appointment_id, "
            "consultation_date, chief_complaint, diagnosis, treatment_plan, "
            "temperature, blood_pressure, pulse_rate, respiratory_rate, weight) "
            "VALUES (?, ?, 5, ?, ?, ?, ?, ?, 36.8, '120/80', 80, 18, 60.0)",
            (cid, patient_id, cid, f"{day} 09:30:00", complaint, diagnosis, plan),
        )

    # One dispensing row on consultation 36, so its Dispensing History tab has
    # something to join the diagnosis onto.
    conn.execute(
        "INSERT INTO medicine_dispensing (patient_id, consultation_id, inventory_item_id, "
        "medicine_name, unit, quantity_dispensed, date_dispensed, dispensed_by) "
        "VALUES (?, 36, 1, 'Paracetamol 500 mg tablet', 'tablet', 10, ?, 2)",
        (_consultation_patient(36), _consultation_date(36)),
    )
    conn.execute(
        "INSERT INTO medicine_dispensing_batches (dispensing_id, batch_id, quantity) "
        "VALUES (last_insert_rowid(), 1, 10)"
    )
    conn.execute(
        "UPDATE inventory_batches SET quantity_remaining = quantity_remaining - 10 "
        "WHERE inventory_item_id = 1"
    )

    # The infant's birth doses, given here.
    birth = PATIENTS[16][3]
    for code in ("BCG", "HEPB"):
        conn.execute(
            "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, "
            "date_administered, administered_by) VALUES (17, ?, 1, 'given_here', ?, 2)",
            (code, birth),
        )

    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# The database for this process
# ---------------------------------------------------------------------------
def _make_test_dir():
    given = os.environ.get("IDS_TEST_DIR")
    if given:
        folder = Path(given)
        guard_path(folder / "probe.db")
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder), False
    folder = tempfile.mkdtemp(prefix="ids-bphcsn-test-")
    guard_path(Path(folder) / "probe.db")
    return folder, True


TEST_DIR, _OWN_DIR = _make_test_dir()
DB_PATH = guard_path(os.path.join(TEST_DIR, "test.db"))
build_fixture_database(DB_PATH)

# The error log goes in the temporary folder too, not in the project (Task 10, D8).
os.environ["IDS_LOG_DIR"] = os.path.join(TEST_DIR, "logs")

# Point the app at the test database BEFORE any app module is imported.
import config  # noqa: E402

config.DATABASE = DB_PATH
os.environ["IDS_TEST_DB"] = DB_PATH


def _cleanup():
    if _OWN_DIR:
        shutil.rmtree(TEST_DIR, ignore_errors=True)


atexit.register(_cleanup)


# ---------------------------------------------------------------------------
# The form token (CSRF). Every POST must carry the token from a page the app
# served (utils/csrf.py). A browser takes it from the page. The suites post
# without rendering the page first, so their clients add a real token to every
# POST that does not carry one: made by Flask-WTF's own generate_csrf(), for the
# client's own session. The app still checks every request. tests/verify_csrf.py
# uses a plain FlaskClient to test the refusals.
# ---------------------------------------------------------------------------
from flask import Flask  # noqa: E402
from flask.testing import FlaskClient  # noqa: E402
from werkzeug.datastructures import Headers  # noqa: E402

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRFToken"
TOKEN_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_token_for(client):
    """A valid form token for this client's session, as a page would carry it."""
    from flask.ctx import RequestContext
    from flask_wtf.csrf import generate_csrf
    from werkzeug.test import EnvironBuilder

    with client.session_transaction() as sess:
        # A request context holding this client's session, so the token is
        # stored in, and tied to, that session. Saved when the block ends.
        ctx = RequestContext(client.application, EnvironBuilder().get_environ(),
                             session=sess)
        ctx.push()
        try:
            return generate_csrf()
        finally:
            ctx.pop()


class TokenClient(FlaskClient):
    """A test client that sends the form token with every POST, like a page does."""

    def open(self, *args, **kwargs):
        method = str(kwargs.get("method", "GET")).upper()
        data = kwargs.get("data")
        headers = Headers(kwargs.get("headers") or {})
        carries = CSRF_HEADER in headers or (hasattr(data, "keys") and CSRF_FIELD in data)
        if method in TOKEN_METHODS and not carries:
            headers[CSRF_HEADER] = csrf_token_for(self)
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


Flask.test_client_class = TokenClient


def open_session(sess):
    """Give a session a suite builds by hand the two times a real sign-in records.

    The server treats a session without them as past the 12-hour limit
    (utils/security.py). A real sign-in sets them in routes/auth.py.
    """
    import time

    moment = int(time.time())
    sess["signed_in_at"] = moment
    sess["last_active"] = moment


def clear_password_change(username):
    """Clear must_change_password for an account a suite just created or reset.

    A new or reset account must set its own password before it can use any
    other screen. tests/verify_security_basics.py tests that rule. The other
    suites clear the flag, as if the person had already set their own
    password, so they can keep testing what they were written for.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE users SET must_change_password = 0 WHERE username = ?",
                     (username,))
        conn.commit()
    finally:
        conn.close()


def work_path(name):
    """A path for a scratch file inside this suite's temporary folder."""
    return guard_path(os.path.join(TEST_DIR, name))


def live_db_counts():
    """Row counts from the live app.db, opened READ-ONLY, or None if it is absent.

    Used only by the Add User suite, to show the run did not write to the live
    database. The file is opened with mode=ro, so this cannot change it.
    """
    if not LIVE_DB.exists():
        return None
    uri = LIVE_DB.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE module='User Management'"
            ).fetchone()[0],
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# A frozen "today" (Task 15). The real date moves on; a scenario written for one
# day (a baby born Sep 3, 2026, seen on Oct 3, 2026) needs the same day every run.
# utils.dates.now() and today() are replaced in every module that imported them,
# for the length of the `with` block, and put back after it.
# ---------------------------------------------------------------------------
import contextlib  # noqa: E402


@contextlib.contextmanager
def frozen_today(day, hour=10):
    import sys as _sys
    from datetime import datetime as _dt

    import utils.dates as dates

    moment = _dt(day.year, day.month, day.day, hour, 0, tzinfo=dates.CLINIC_TIMEZONE)
    originals = {"now": dates.now, "today": dates.today}
    fakes = {"now": lambda: moment, "today": lambda: moment.date()}
    swapped = []
    for module in list(_sys.modules.values()):
        for name in ("now", "today"):
            if getattr(module, name, None) is originals[name]:
                setattr(module, name, fakes[name])
                swapped.append((module, name))
    try:
        yield
    finally:
        for module, name in swapped:
            setattr(module, name, originals[name])

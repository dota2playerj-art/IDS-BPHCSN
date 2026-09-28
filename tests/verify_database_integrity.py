"""Database integrity: a fresh install works, and a failed write frees its lock.

Three things, each a defect found on 2026-09-28 (PROJECT_STATUS.md H5, M16):

A. On a database built from schema.sql, Health Center Staff and the Doctor
   can both record a consultation. Before the fix, schema.sql made
   consultations.updated_at NOT NULL, the insert wrote NULL, and every new
   consultation failed with HTTP 500.
B. A write that fails does not leave its connection open. Before the fix, the
   open connection kept SQLite's write lock, and the next write failed with
   "database is locked".
C. A fresh install's consultations table has the expected structure,
   including a nullable updated_at, so schema.sql cannot drift back.

Runs on a fresh test database built by tests/_support.py.
"""
import sqlite3
import sys
import time

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import config  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH

STAFF_ID, DOCTOR_ID = 2, 5
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail and not ok:
        for line in str(detail).splitlines()[:12]:
            print(f"       {line}")
    return ok


def section(title):
    print(f"\n--- {title} ---")


def db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn


def q1(sql, args=()):
    conn = db()
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def new_queue_entry(patient_id):
    """A walk-in checked in today and In Consultation: what Record accepts."""
    conn = db()
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (?, ?, date('now','localtime'), "
        "'In Consultation', 1, datetime('now','localtime'))",
        (patient_id, STAFF_ID))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


print("=" * 78)
print("IDS-BPHCSN — database integrity: fresh install, and failed writes")
print("=" * 78)

# ===========================================================================
section("A. A FRESH DATABASE RECORDS A CONSULTATION")
for who, user_id, form in (
        ("Health Center Staff", STAFF_ID, {
            "chief_complaint": "Integrity check: staff intake",
            "temperature": "37.0", "blood_pressure": "120/80", "weight": "61"}),
        ("Doctor", DOCTOR_ID, {
            "chief_complaint": "Integrity check: doctor visit",
            "temperature": "37.2", "weight": "62",
            "diagnosis": "Integrity check diagnosis",
            "treatment_plan": "Integrity check plan"})):
    appt = new_queue_entry(4)
    r = client_as(user_id).post(f"/staff/consultation/record/{appt}", data=form)
    row = q1("SELECT * FROM consultations WHERE appointment_id = ?", (appt,))
    check(f"{who}: record POST saved and redirected (no 500)",
          r.status_code == 302, f"status {r.status_code}")
    check(f"{who}: the consultation row exists, recorded by this account",
          row is not None and row["recorded_by"] == user_id,
          dict(row) if row else None)
    check(f"{who}: updated_at equals created_at, so it reads as never edited",
          row is not None and row["updated_at"] is not None
          and row["updated_at"] == row["created_at"],
          dict(row) if row else None)
    check(f"{who}: the queue entry was completed",
          q1("SELECT status FROM appointments WHERE id = ?", (appt,))[0] == "Completed")
doctor_row = q1("SELECT diagnosis FROM consultations "
                "WHERE chief_complaint = 'Integrity check: doctor visit'")
check("Doctor: the diagnosis was stored",
      doctor_row is not None and doctor_row[0] == "Integrity check diagnosis")

# ===========================================================================
section("B. A FAILED WRITE DOES NOT LOCK THE DATABASE")
from models.audit import log_action  # noqa: E402
from models.users import create_user  # noqa: E402

users_before = q1("SELECT COUNT(*) FROM users")[0]
failure = None
with app.app_context():
    try:
        # create_user() inserts without checking first; the route validates.
        # "staff" already exists, so the INSERT starts a write and then fails
        # on the UNIQUE username constraint.
        create_user({"username": "staff", "full_name": "Duplicate Probe",
                     "role": "Health Center Staff"})
    except sqlite3.Error as exc:
        # Kept on purpose. Flask keeps a failed request's traceback the same
        # way, and the traceback keeps the failing function's connection alive.
        failure = exc
check("the forced write failed with a database error",
      isinstance(failure, sqlite3.IntegrityError), repr(failure))
check("the failed write changed nothing",
      q1("SELECT COUNT(*) FROM users")[0] == users_before)

started = time.monotonic()
second = None
with app.app_context():
    try:
        second = log_action(user_id=1, action="Integrity check",
                            module="Settings", details="written after a failed write")
    except sqlite3.OperationalError as exc:
        second = exc
waited = time.monotonic() - started
check("the next write succeeds while the failure is still held",
      isinstance(second, int) and second > 0, repr(second))
check("and it did not wait on a lock (under 2 seconds)", waited < 2.0,
      f"waited {waited:.1f}s")
r = client_as(STAFF_ID).post(
    f"/staff/consultation/record/{new_queue_entry(3)}",
    data={"chief_complaint": "Integrity check: after a failed write"})
check("a real consultation save still works afterwards", r.status_code == 302,
      f"status {r.status_code}")
failure = None

# ===========================================================================
section("C. A FRESH INSTALL'S consultations TABLE HAS THE EXPECTED STRUCTURE")
# (name, type, notnull, default, pk), in order, as the migrated live database
# has them apart from column order. updated_at is nullable with no default:
# create_consultation() inserts NULL and then copies created_at into it.
EXPECTED_COLUMNS = [
    ("id", "INTEGER", 0, None, 1),
    ("patient_id", "INTEGER", 1, None, 0),
    ("recorded_by", "INTEGER", 1, None, 0),
    ("appointment_id", "INTEGER", 0, None, 0),
    ("consultation_date", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ("chief_complaint", "TEXT", 0, None, 0),
    ("diagnosis", "TEXT", 0, None, 0),
    ("treatment_plan", "TEXT", 0, None, 0),
    ("remarks", "TEXT", 0, None, 0),
    ("temperature", "REAL", 0, None, 0),
    ("blood_pressure", "TEXT", 0, None, 0),
    ("pulse_rate", "INTEGER", 0, None, 0),
    ("respiratory_rate", "INTEGER", 0, None, 0),
    ("weight", "REAL", 0, None, 0),
    ("height", "REAL", 0, None, 0),
    ("head_circumference", "REAL", 0, None, 0),
    ("follow_up_date", "TEXT", 0, None, 0),
    ("is_restricted", "INTEGER", 1, "0", 0),
    ("restricted_by", "INTEGER", 0, None, 0),
    ("restricted_at", "TEXT", 0, None, 0),
    ("created_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ("updated_at", "TEXT", 0, None, 0),
]
# (table, from, to, on_update, on_delete)
EXPECTED_FOREIGN_KEYS = sorted([
    ("appointments", "appointment_id", "id", "NO ACTION", "SET NULL"),
    ("patients", "patient_id", "id", "NO ACTION", "CASCADE"),
    ("users", "recorded_by", "id", "NO ACTION", "RESTRICT"),
    ("users", "restricted_by", "id", "NO ACTION", "NO ACTION"),
])

# Build a second database exactly as a new install does: init_db() runs
# schema.sql and then seeds the first accounts.
fresh_path = _support.work_path("fresh_install.db")
from database.schema import init_db  # noqa: E402

saved = config.DATABASE
config.DATABASE = fresh_path
try:
    init_db()  # outside an app context it uses config.DATABASE
finally:
    config.DATABASE = saved
fresh = sqlite3.connect(fresh_path)
columns = [tuple(r[1:6]) for r in fresh.execute("PRAGMA table_info(consultations)")]
fkeys = sorted(tuple(r[2:7]) for r in fresh.execute("PRAGMA foreign_key_list(consultations)"))
seeded = fresh.execute("SELECT COUNT(*) FROM users").fetchone()[0]
fresh.close()

check("a new install creates the database and seeds accounts", seeded >= 1, seeded)
updated = next((c for c in columns if c[0] == "updated_at"), None)
check("updated_at is nullable, with no default",
      updated is not None and updated[2] == 0 and updated[3] is None, updated)
check("every consultations column matches the expected structure",
      columns == EXPECTED_COLUMNS,
      "\n".join(f"got {g}  expected {e}" for g, e in zip(columns, EXPECTED_COLUMNS) if g != e)
      or f"{len(columns)} columns, expected {len(EXPECTED_COLUMNS)}")
check("the consultations foreign keys match the expected structure",
      fkeys == EXPECTED_FOREIGN_KEYS, f"got {fkeys}")

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print("  FAILED:", name)
print("=" * 78)
sys.exit(0 if not failed else 1)

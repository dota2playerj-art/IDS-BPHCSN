"""Migration: give appointments the two queue states and the check-in fields.

Screen 08 is being turned into the live consultation queue, so an appointment now
has to be able to say "this patient has arrived and is waiting" and "this patient
is with the clinician right now". The existing status vocabulary had neither: it
went straight from Scheduled/Confirmed to Completed, with nothing in between.

Two statuses are added to the CHECK:

    Waiting           checked in and in the queue
    In Consultation   currently being seen

"Waiting" is not a new coinage -- appointment_scheduling.html already ships a
.badge-waiting style and a "Waiting" option in its status filter, so this adopts
the word the frozen UI was already written around. "In Consultation" follows the
same Title Case as every other value.

Idempotent -- re-running is a no-op. Run:  python migrate_add_appointment_queue.py

WHY THIS ONE IS NOT PURELY ALTER TABLE
--------------------------------------
migrate_add_patient_columns.py and migrate_add_inventory_columns.py only ever
needed ALTER TABLE ... ADD COLUMN, which SQLite supports directly. This migration
needs that too, for the two new columns -- and that half follows their pattern
exactly, including the byte-for-byte verification below.

But it also has to widen a CHECK constraint on a column that already exists, and
SQLite has no ALTER TABLE ... ALTER COLUMN / DROP CONSTRAINT. The only supported
way is the table rebuild documented at sqlite.org/lang_altertable.html#otheralter:
create the replacement, copy every row, drop the original, rename. That is done
here inside one transaction with foreign keys disabled for the swap, followed by
a foreign_key_check, and the row-by-row comparison at the end proves the copy was
lossless rather than assuming it.

The rebuild is skipped entirely when the CHECK already lists both new statuses,
so the expensive path runs at most once.

TWO NEW COLUMNS
---------------
* is_walkin -- 1 when the visit had no prior booking. The queue and any later
  reporting need to tell a walk-in from a kept appointment, and the distinction
  cannot be recovered afterwards: once a scheduled patient is checked in, their
  row looks exactly like a walk-in's apart from this flag.

* checked_in_at -- when the patient physically arrived. created_at cannot serve
  here. For a walk-in the two coincide, but for a patient who booked last week
  created_at is the booking time, so ordering the queue by it would put every
  pre-booked patient ahead of every walk-in regardless of who actually turned up
  first. The queue orders by this column.
"""
import sqlite3
import sys

import config

# (column_name, column_definition) in the order they are added. Same shape as the
# two prior migrations.
NEW_COLUMNS = [
    ("is_walkin", "INTEGER NOT NULL DEFAULT 0"),
    ("checked_in_at", "TEXT"),
]

# The full status vocabulary after this migration, in queue order.
APPOINTMENT_STATUSES = (
    "Scheduled", "Confirmed", "Waiting", "In Consultation",
    "Completed", "Cancelled", "No-show",
)

# The two this migration introduces; their presence in the live CHECK is what
# makes the rebuild a no-op on a second run.
ADDED_STATUSES = ("Waiting", "In Consultation")

_STATUS_CHECK = ", ".join(f"'{status}'" for status in APPOINTMENT_STATUSES)

# The replacement table. Identical to the original apart from the widened CHECK
# and the two new columns, which by this point ADD COLUMN has already created --
# they are spelled out here because the rebuild defines the table from scratch.
NEW_TABLE_SQL = f"""
CREATE TABLE appointments_migrated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    scheduled_by INTEGER NOT NULL,
    appointment_type TEXT,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT,
    assigned_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN ({_STATUS_CHECK})),
    notes TEXT,
    is_walkin INTEGER NOT NULL DEFAULT 0,
    checked_in_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (scheduled_by) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL
)
"""

# Every column, named explicitly on both sides of the copy so the transfer cannot
# depend on column order -- ADD COLUMN appends, so the live order differs from the
# grouped order above.
COPY_COLUMNS = (
    "id", "patient_id", "scheduled_by", "appointment_type", "appointment_date",
    "appointment_time", "assigned_staff_id", "status", "notes",
    "is_walkin", "checked_in_at", "created_at", "updated_at",
)

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_appointments_date "
    "ON appointments(appointment_date, status)",
    # The queue reads one day's rows and orders them by arrival.
    "CREATE INDEX IF NOT EXISTS idx_appointments_queue "
    "ON appointments(appointment_date, status, checked_in_at)",
)


def existing_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(appointments)")}


def status_check_sql(conn):
    """The stored CREATE TABLE text for appointments."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'appointments'"
    ).fetchone()
    return row[0] if row else ""


def check_covers_queue_statuses(conn):
    """True when the live CHECK already admits both new statuses."""
    sql = status_check_sql(conn)
    return all(f"'{status}'" in sql for status in ADDED_STATUSES)


def rebuild_with_wider_check(conn):
    """Replace appointments with an identical table whose CHECK is wider.

    The sequence is the one SQLite documents for altering a constraint. Foreign
    keys are disabled around the swap so the DROP cannot cascade, and re-enabled
    after a foreign_key_check confirms nothing was orphaned.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(NEW_TABLE_SQL)
        columns = ", ".join(COPY_COLUMNS)
        conn.execute(
            f"INSERT INTO appointments_migrated ({columns}) "
            f"SELECT {columns} FROM appointments"
        )
        conn.execute("DROP TABLE appointments")
        conn.execute("ALTER TABLE appointments_migrated RENAME TO appointments")
        for statement in INDEXES:
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys = ON")
        raise

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.execute("PRAGMA foreign_keys = ON")
    return violations


def main():
    # isolation_level=None: this script issues its own BEGIN/COMMIT around the
    # rebuild, and PRAGMA foreign_keys is ignored inside a transaction, so the
    # implicit one Python would otherwise open has to be out of the way.
    conn = sqlite3.connect(config.DATABASE, isolation_level=None)
    conn.row_factory = sqlite3.Row

    before_count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    before_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM appointments ORDER BY id")
    }
    print(f"appointments before migration: {before_count}")

    # --- Part 1: the two new columns, exactly the prior migrations' pattern ---
    present = existing_columns(conn)
    added, skipped = [], []
    for name, definition in NEW_COLUMNS:
        if name in present:
            skipped.append(name)
            continue
        conn.execute(f"ALTER TABLE appointments ADD COLUMN {name} {definition}")
        added.append(name)

    print(f"columns added:   {added if added else '(none)'}")
    print(f"already present: {skipped if skipped else '(none)'}")

    # --- Part 2: widen the status CHECK, which needs the documented rebuild ---
    problems = []
    if check_covers_queue_statuses(conn):
        print("status CHECK: already admits Waiting / In Consultation — rebuild skipped")
    else:
        print("status CHECK: rebuilding table to admit Waiting / In Consultation")
        violations = rebuild_with_wider_check(conn)
        if violations:
            problems.append(f"foreign_key_check reported {len(violations)} violation(s)")
        else:
            print("foreign_key_check: clean")

    after_count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    after_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM appointments ORDER BY id")
    }
    print(f"appointments after migration:  {after_count}")

    if before_count != after_count:
        problems.append(f"row count changed: {before_count} -> {after_count}")

    for appointment_id, old in before_rows.items():
        new = after_rows.get(appointment_id)
        if new is None:
            problems.append(f"appointment id={appointment_id} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(
                    f"id={appointment_id}.{column}: {value!r} -> {new[column]!r}"
                )

    # Every status the table now holds must be one the new CHECK admits, and the
    # two added columns must have taken their defaults on existing rows.
    unknown = conn.execute(
        "SELECT DISTINCT status FROM appointments WHERE status NOT IN "
        f"({', '.join('?' for _ in APPOINTMENT_STATUSES)})",
        APPOINTMENT_STATUSES,
    ).fetchall()
    if unknown:
        problems.append(f"rows hold statuses outside the CHECK: {[r[0] for r in unknown]}")

    null_walkin = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE is_walkin IS NULL"
    ).fetchone()[0]
    if null_walkin:
        problems.append(f"{null_walkin} rows have a NULL is_walkin")

    if not check_covers_queue_statuses(conn):
        problems.append("status CHECK still does not admit the queue statuses")

    # The constraint has to actually reject a bad value, not merely list good
    # ones. The probe needs a real patient and a real user to point at, because
    # the row has to survive the foreign keys long enough to reach the CHECK --
    # otherwise an FK failure would be mistaken for the CHECK doing its job. A
    # database migrated before anyone has been registered simply has nothing to
    # point at, so the probe is skipped there rather than reported as a failure.
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1) AS patient_id, "
        "       (SELECT id FROM users LIMIT 1) AS user_id"
    ).fetchone()

    if anchor["patient_id"] is None or anchor["user_id"] is None:
        print("status CHECK: runtime rejection not probed "
              "(no patient/user row to reference); CHECK text verified above")
    else:
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO appointments "
                "(patient_id, scheduled_by, appointment_date, status) "
                "VALUES (?, ?, '2026-01-01', 'Bogus')",
                (anchor["patient_id"], anchor["user_id"]),
            )
            conn.execute("ROLLBACK")
            problems.append("CHECK did not reject an invalid status")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "CHECK constraint failed" not in str(exc):
                problems.append(
                    f"invalid status was rejected, but by {exc} rather than the CHECK"
                )
            else:
                print("status CHECK: rejects values outside the vocabulary")

    live_indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='appointments'"
        )
    }
    for expected in ("idx_appointments_date", "idx_appointments_queue"):
        if expected not in live_indexes:
            problems.append(f"index {expected} missing after migration")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nAll pre-existing column values preserved byte-for-byte; "
          "indexes and foreign keys intact; queue statuses available.")


if __name__ == "__main__":
    main()

"""Migration: add the appointment_sms_messages table.

Run: python migrations/migrate_add_appointment_sms.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

MESSAGES_SQL = """
CREATE TABLE IF NOT EXISTS appointment_sms_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    appointment_id INTEGER,
    patient_id INTEGER,
    event TEXT NOT NULL CHECK (event IN ('booked', 'rescheduled', 'cancelled')),
    recipient_name TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    message TEXT NOT NULL,
    segments INTEGER NOT NULL DEFAULT 0,
    encoding TEXT NOT NULL DEFAULT 'GSM-7',
    status TEXT NOT NULL CHECK (status IN ('Sent', 'Failed')),
    delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('live', 'simulated')),
    gateway_response TEXT,
    sent_by INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (sent_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_appointment_sms_sent_at "
    "ON appointment_sms_messages(sent_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_appointment_sms_appointment "
    "ON appointment_sms_messages(appointment_id, sent_at)",
)

NEW_TABLES = ("appointment_sms_messages",)

# Every table whose contents must be exactly what they were. The two broadcast
# tables are in this list on purpose: the whole promise of this change is that
# community broadcasts are untouched by it, and that promise is worth checking
# row for row rather than asserting.
EXISTING_TABLES = (
    "users", "patients", "consultations", "inventory_items", "appointments",
    "immunizations", "general_vaccinations", "medicine_dispensing",
    "audit_logs", "settings", "sms_broadcasts", "sms_broadcast_recipients",
)

MESSAGE_COLUMNS = [
    "id", "reference", "appointment_id", "patient_id", "event", "recipient_name",
    "mobile_number", "message", "segments", "encoding", "status",
    "delivery_mode", "gateway_response", "sent_by", "sent_at", "created_at",
]


def table_names(conn):
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def snapshot(conn, table):
    """Every row of one table, keyed by id, or None if the table is absent."""
    if table not in table_names(conn):
        return None
    return {
        row["id"]: dict(row)
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")
    }


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = {table: snapshot(conn, table) for table in EXISTING_TABLES}
    for table in NEW_TABLES:
        present = table in table_names(conn)
        print(f"{table} before migration: {'present' if present else 'absent'}")
    for table, rows in before.items():
        print(f"  {table:<26} {len(rows) if rows is not None else '(missing)'} rows")

    conn.execute(MESSAGES_SQL)
    for statement in INDEXES:
        conn.execute(statement)
    conn.commit()

    print()
    for table in NEW_TABLES:
        present = table in table_names(conn)
        count = (
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if present else "-"
        )
        print(f"{table} after migration: {'present' if present else 'MISSING'} ({count} rows)")

    problems = []

    for table in NEW_TABLES:
        if table not in table_names(conn):
            problems.append(f"{table} was not created")

    # --- nothing that already existed may have moved ------------------------
    for table, old in before.items():
        new = snapshot(conn, table)
        if old is None:
            continue
        if new is None:
            problems.append(f"table {table} disappeared")
            continue
        if len(old) != len(new):
            problems.append(f"{table}: row count changed {len(old)} -> {len(new)}")
            continue
        for row_id, old_row in old.items():
            new_row = new.get(row_id)
            if new_row is None:
                problems.append(f"{table} id={row_id} disappeared")
                continue
            for column, value in old_row.items():
                if new_row[column] != value:
                    problems.append(
                        f"{table} id={row_id}.{column}: {value!r} -> {new_row[column]!r}"
                    )

    columns = [
        row[1] for row in conn.execute("PRAGMA table_info(appointment_sms_messages)")
    ]
    if columns != MESSAGE_COLUMNS:
        problems.append(
            f"appointment_sms_messages columns are {columns}, expected {MESSAGE_COLUMNS}"
        )

    live_indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'appointment_sms_messages'"
        )
    }
    for name in ("idx_appointment_sms_sent_at", "idx_appointment_sms_appointment"):
        if name not in live_indexes:
            problems.append(f"index {name} missing after migration")

    # --- the constraints have to actually refuse, not merely be written -----
    #
    # Probes need a real user to attribute a message to, so a database migrated
    # before anyone is seeded skips them rather than reporting a failure -- the
    # same allowance migrate_add_sms_broadcasts.py makes for its probes.
    anchor = conn.execute("SELECT id FROM users LIMIT 1").fetchone()

    if anchor is None:
        print("constraints: not probed (no user row to reference); DDL verified above")
    else:
        user_id = anchor["id"]

        def probe(event="booked", status="Sent", delivery_mode="simulated",
                  reference="__PROBE__"):
            conn.execute(
                """
                INSERT INTO appointment_sms_messages
                    (reference, event, recipient_name, mobile_number, message,
                     status, delivery_mode, sent_by)
                VALUES (?, ?, '__PROBE__', '09171234567', '__PROBE__', ?, ?, ?)
                """,
                (reference, event, status, delivery_mode, user_id),
            )

        def expect_refusal(label, description, **kwargs):
            try:
                conn.execute("BEGIN")
                probe(**kwargs)
                conn.execute("ROLLBACK")
                problems.append(f"{label} did not reject {description}")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                if "CHECK constraint failed" not in str(exc):
                    problems.append(f"{description} rejected by {exc}, not CHECK")
                else:
                    print(f"{label}: rejects {description}")

        # A message cannot be about something this feature does not send.
        expect_refusal(
            "CHECK (event)", "event 'no-show', which is not a thing to text about",
            event="no-show",
        )
        # A row cannot claim a delivery this system never learns of.
        expect_refusal(
            "CHECK (status)", "status 'Delivered', which nothing could verify",
            status="Delivered",
        )
        # A row cannot exist without saying whether it really left the building.
        expect_refusal(
            "CHECK (delivery_mode)", "a mode that is neither live nor simulated",
            delivery_mode="pretend",
        )

        # reference must be unique.
        try:
            conn.execute("BEGIN")
            probe()
            probe()
            conn.execute("ROLLBACK")
            problems.append("UNIQUE did not reject a duplicate reference")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "UNIQUE constraint failed" not in str(exc):
                problems.append(f"duplicate reference rejected by {exc}, not UNIQUE")
            else:
                print("UNIQUE (reference): rejects a repeated message reference")

        left_behind = conn.execute(
            "SELECT COUNT(*) FROM appointment_sms_messages WHERE message = '__PROBE__'"
        ).fetchone()[0]
        if left_behind:
            problems.append(f"{left_behind} probe rows survived their rollback")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nappointment_sms_messages present with its indexes and working "
          "constraints; every pre-existing table unchanged row for row, the two "
          "broadcast tables included.")


if __name__ == "__main__":
    main()

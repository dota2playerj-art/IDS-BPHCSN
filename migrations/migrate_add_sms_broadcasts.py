"""Migration: add the sms_broadcasts and sms_broadcast_recipients tables.

Run: python migrations/migrate_add_sms_broadcasts.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

BROADCASTS_SQL = """
CREATE TABLE IF NOT EXISTS sms_broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    message TEXT NOT NULL,
    category TEXT,
    audience TEXT NOT NULL,
    audience_label TEXT NOT NULL,
    recipient_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    segments INTEGER NOT NULL DEFAULT 0,
    encoding TEXT NOT NULL DEFAULT 'GSM-7',
    status TEXT NOT NULL DEFAULT 'Sent' CHECK (status IN ('Sent', 'Partial', 'Failed')),
    delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('live', 'simulated')),
    sent_by INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sent_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

RECIPIENTS_SQL = """
CREATE TABLE IF NOT EXISTS sms_broadcast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL,
    patient_id INTEGER,
    user_id INTEGER,
    recipient_name TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Sent', 'Failed')),
    gateway_response TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (broadcast_id) REFERENCES sms_broadcasts(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sms_broadcasts_sent_at "
    "ON sms_broadcasts(sent_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_sms_recipients_broadcast "
    "ON sms_broadcast_recipients(broadcast_id, status)",
)

NEW_TABLES = ("sms_broadcasts", "sms_broadcast_recipients")

# Every table whose contents must be exactly what they were.
EXISTING_TABLES = (
    "users", "patients", "consultations", "inventory_items", "appointments",
    "immunizations", "audit_logs", "schedule_logs", "settings",
)

BROADCAST_COLUMNS = [
    "id", "reference", "message", "category", "audience", "audience_label",
    "recipient_count", "sent_count", "failed_count", "segments", "encoding",
    "status", "delivery_mode", "sent_by", "sent_at", "created_at",
]

RECIPIENT_COLUMNS = [
    "id", "broadcast_id", "patient_id", "user_id", "recipient_name",
    "mobile_number", "status", "gateway_response", "created_at",
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
        print(f"  {table:<16} {len(rows) if rows is not None else '(missing)'} rows")

    conn.execute(BROADCASTS_SQL)
    conn.execute(RECIPIENTS_SQL)
    for statement in INDEXES:
        conn.execute(statement)
    conn.commit()

    print()
    for table in NEW_TABLES:
        present = table in table_names(conn)
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if present else "-"
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

    for table, expected in (
        ("sms_broadcasts", BROADCAST_COLUMNS),
        ("sms_broadcast_recipients", RECIPIENT_COLUMNS),
    ):
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if columns != expected:
            problems.append(f"{table} columns are {columns}, expected {expected}")

    live_indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name IN ('sms_broadcasts', 'sms_broadcast_recipients')"
        )
    }
    for name in ("idx_sms_broadcasts_sent_at", "idx_sms_recipients_broadcast"):
        if name not in live_indexes:
            problems.append(f"index {name} missing after migration")

    # --- the constraints have to actually refuse, not merely be written -----
    #
    # Probes need a real user to attribute a broadcast to, so a database migrated
    # before anyone is seeded skips them rather than reporting a failure -- the
    # same allowance migrate_add_immunizations.py makes for its probes.
    anchor = conn.execute("SELECT id FROM users LIMIT 1").fetchone()

    if anchor is None:
        print("constraints: not probed (no user row to reference); DDL verified above")
    else:
        user_id = anchor["id"]

        def probe_broadcast(delivery_mode, status="Sent", reference="__PROBE__"):
            conn.execute(
                """
                INSERT INTO sms_broadcasts
                    (reference, message, audience, audience_label, status,
                     delivery_mode, sent_by)
                VALUES (?, '__PROBE__', 'all_patients', 'Probe', ?, ?, ?)
                """,
                (reference, status, delivery_mode, user_id),
            )

        # delivery_mode must refuse anything but live/simulated. A row that could
        # not say whether its messages left is the failure this column prevents.
        try:
            conn.execute("BEGIN")
            probe_broadcast("pretend")
            conn.execute("ROLLBACK")
            problems.append("CHECK did not reject delivery_mode 'pretend'")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "CHECK constraint failed" not in str(exc):
                problems.append(f"bad delivery_mode rejected by {exc}, not CHECK")
            else:
                print("CHECK (delivery_mode): rejects a mode that is neither live nor simulated")

        # reference must be unique.
        try:
            conn.execute("BEGIN")
            probe_broadcast("simulated")
            probe_broadcast("simulated")
            conn.execute("ROLLBACK")
            problems.append("UNIQUE did not reject a duplicate reference")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "UNIQUE constraint failed" not in str(exc):
                problems.append(f"duplicate reference rejected by {exc}, not UNIQUE")
            else:
                print("UNIQUE (reference): rejects a repeated broadcast reference")

        # A recipient row cannot claim a delivery this system never learns of.
        try:
            conn.execute("BEGIN")
            probe_broadcast("simulated")
            broadcast_id = conn.execute(
                "SELECT id FROM sms_broadcasts WHERE reference = '__PROBE__'"
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT INTO sms_broadcast_recipients
                    (broadcast_id, recipient_name, mobile_number, status)
                VALUES (?, 'Probe', '09171234567', 'Delivered')
                """,
                (broadcast_id,),
            )
            conn.execute("ROLLBACK")
            problems.append("CHECK did not reject recipient status 'Delivered'")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "CHECK constraint failed" not in str(exc):
                problems.append(f"'Delivered' rejected by {exc}, not CHECK")
            else:
                print("CHECK (recipient status): rejects 'Delivered', which nothing could verify")

        left_behind = conn.execute(
            "SELECT COUNT(*) FROM sms_broadcasts WHERE message = '__PROBE__'"
        ).fetchone()[0]
        if left_behind:
            problems.append(f"{left_behind} probe rows survived their rollback")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nsms_broadcasts and sms_broadcast_recipients present with their indexes "
          "and working constraints; every pre-existing table unchanged row for row.")


if __name__ == "__main__":
    main()

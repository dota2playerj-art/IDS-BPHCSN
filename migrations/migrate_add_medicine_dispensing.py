"""Migration: add the medicine_dispensing table.

Run: python migrations/migrate_add_medicine_dispensing.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS medicine_dispensing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    inventory_item_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    unit TEXT,
    quantity_dispensed INTEGER NOT NULL CHECK (quantity_dispensed > 0),
    date_dispensed TEXT NOT NULL,
    dispensed_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (consultation_id, inventory_item_id),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE RESTRICT,
    FOREIGN KEY (dispensed_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

INDEXES = (
    # Patient Profile's Medicine History tab reads one patient's issues, newest
    # first.
    "CREATE INDEX IF NOT EXISTS idx_medicine_dispensing_patient "
    "ON medicine_dispensing(patient_id, date_dispensed)",
    # The consultation form reads back what was given during one visit, and the
    # Recent Consultations table on the Administrator dashboard reads it per row.
    "CREATE INDEX IF NOT EXISTS idx_medicine_dispensing_consultation "
    "ON medicine_dispensing(consultation_id)",
    # Reports & Analytics ranks the most-dispensed medicines inside a date range.
    "CREATE INDEX IF NOT EXISTS idx_medicine_dispensing_item "
    "ON medicine_dispensing(inventory_item_id, date_dispensed)",
)

# Every table whose contents must be exactly what they were. `inventory_items`
# is listed first and deliberately: this migration adds the table that will move
# stock figures, and proving it moved none of them itself is the point of the
# check, not a formality.
EXISTING_TABLES = (
    "inventory_items", "users", "patients", "consultations", "immunizations",
    "general_vaccinations", "appointments", "audit_logs", "sms_broadcasts",
    "sms_broadcast_recipients", "settings",
)

EXPECTED_COLUMNS = [
    "id", "patient_id", "consultation_id", "inventory_item_id", "medicine_name",
    "unit", "quantity_dispensed", "date_dispensed", "dispensed_by", "created_at",
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
        for row in conn.execute("SELECT * FROM {} ORDER BY id".format(table))
    }


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = {table: snapshot(conn, table) for table in EXISTING_TABLES}
    existed = "medicine_dispensing" in table_names(conn)
    print("medicine_dispensing table before migration: "
          "{}".format("present" if existed else "absent"))
    for table, rows in before.items():
        print("  {:<28} {} rows".format(
            table, len(rows) if rows is not None else "(missing)"))

    conn.execute(TABLE_SQL)
    for statement in INDEXES:
        conn.execute(statement)
    conn.commit()

    present = "medicine_dispensing" in table_names(conn)
    print("\nmedicine_dispensing table after migration: "
          "{}".format("present" if present else "MISSING"))
    print("dispensing rows: {}".format(
        conn.execute("SELECT COUNT(*) FROM medicine_dispensing").fetchone()[0]))

    problems = []

    if not present:
        problems.append("medicine_dispensing table was not created")

    # --- nothing that already existed may have moved ------------------------
    for table, old in before.items():
        new = snapshot(conn, table)
        if old is None:
            continue
        if new is None:
            problems.append("table {} disappeared".format(table))
            continue
        if len(old) != len(new):
            problems.append("{}: row count changed {} -> {}".format(
                table, len(old), len(new)))
            continue
        for row_id, old_row in old.items():
            new_row = new.get(row_id)
            if new_row is None:
                problems.append("{} id={} disappeared".format(table, row_id))
                continue
            for column, value in old_row.items():
                if new_row[column] != value:
                    problems.append("{} id={}.{}: {!r} -> {!r}".format(
                        table, row_id, column, value, new_row[column]))

    columns = [row[1] for row in conn.execute("PRAGMA table_info(medicine_dispensing)")]
    if columns != EXPECTED_COLUMNS:
        problems.append("columns are {}, expected {}".format(columns, EXPECTED_COLUMNS))

    nullable = {row[1]: not row[3] for row in
                conn.execute("PRAGMA table_info(medicine_dispensing)")}
    # unit is the one nullable column of the six that describe the event: an item
    # with no unit recorded on it still dispenses, and inventing "Piece" for it
    # would be a figure this system made up.
    if not nullable.get("unit", False):
        problems.append("unit is NOT NULL; an item with no unit on file must "
                        "still be dispensable")
    for column in ("patient_id", "inventory_item_id", "medicine_name",
                   "quantity_dispensed", "date_dispensed", "dispensed_by"):
        if nullable.get(column, True):
            problems.append("{} is nullable; it must not be".format(column))
    # consultation_id is nullable on purpose -- ON DELETE SET NULL needs it to be.
    if not nullable.get("consultation_id", False):
        problems.append("consultation_id is NOT NULL; ON DELETE SET NULL "
                        "requires it to accept NULL")

    live_indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='medicine_dispensing'"
        )
    }
    for name in ("idx_medicine_dispensing_patient",
                 "idx_medicine_dispensing_consultation",
                 "idx_medicine_dispensing_item"):
        if name not in live_indexes:
            problems.append("index {} missing after migration".format(name))

    # --- the constraints have to actually refuse, not merely be written -----
    #
    # Probes need a real patient, a real user and a real inventory item to point
    # at, so a database migrated before anything is registered simply skips them
    # rather than reporting a failure -- the same allowance
    # migrate_add_general_vaccinations.py makes for its constraint probes.
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1) AS patient_id, "
        "       (SELECT id FROM users LIMIT 1) AS user_id, "
        "       (SELECT id FROM inventory_items LIMIT 1) AS item_id"
    ).fetchone()

    if (anchor["patient_id"] is None or anchor["user_id"] is None
            or anchor["item_id"] is None):
        print("constraints: not probed (no patient/user/item row to reference); "
              "DDL verified above")
    else:
        insert = (
            "INSERT INTO medicine_dispensing "
            "(patient_id, consultation_id, inventory_item_id, medicine_name, "
            " unit, quantity_dispensed, date_dispensed, dispensed_by) "
            "VALUES (?, ?, ?, '__PROBE__', 'Tablet', ?, '2026-01-01', ?)"
        )
        patient_id = anchor["patient_id"]
        item_id = anchor["item_id"]
        user_id = anchor["user_id"]

        # A consultation to hang the UNIQUE probes off. The constraint only bites
        # when consultation_id is non-NULL, so probing it with NULL would prove
        # nothing at all -- which is the mistake worth avoiding here.
        consultation_id = conn.execute(
            "SELECT id FROM consultations LIMIT 1"
        ).fetchone()
        consultation_id = consultation_id[0] if consultation_id else None

        # CHECK must reject a zero quantity -- a record of nothing.
        try:
            conn.execute("BEGIN")
            conn.execute(insert, (patient_id, consultation_id, item_id, 0, user_id))
            conn.execute("ROLLBACK")
            problems.append("CHECK did not reject a zero quantity")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "CHECK constraint failed" not in str(exc):
                problems.append("zero quantity rejected by {} rather than "
                                "CHECK".format(exc))
            else:
                print("CHECK (quantity_dispensed > 0): rejects a zero quantity")

        # ...and a negative one, which would put units back on the shelf through
        # a path with no supplier, batch or expiry date behind them.
        try:
            conn.execute("BEGIN")
            conn.execute(insert, (patient_id, consultation_id, item_id, -5, user_id))
            conn.execute("ROLLBACK")
            problems.append("CHECK did not reject a negative quantity")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "CHECK constraint failed" not in str(exc):
                problems.append("negative quantity rejected by {} rather than "
                                "CHECK".format(exc))
            else:
                print("CHECK (quantity_dispensed > 0): rejects a negative quantity")

        if consultation_id is None:
            print("UNIQUE (consultation, item): not probed (no consultation row "
                  "to anchor to); DDL verified above")
        else:
            # UNIQUE must reject the same medicine twice at one visit.
            try:
                conn.execute("BEGIN")
                for _ in range(2):
                    conn.execute(
                        insert, (patient_id, consultation_id, item_id, 5, user_id))
                conn.execute("ROLLBACK")
                problems.append("UNIQUE did not reject the same medicine twice at "
                                "one consultation")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                if "UNIQUE constraint failed" not in str(exc):
                    problems.append(
                        "same-visit duplicate was rejected, but by {} rather than "
                        "UNIQUE".format(exc))
                else:
                    print("UNIQUE (consultation, item): rejects the same medicine "
                          "twice at one visit")

            # ...and must NOT reject the same medicine at a *different* visit.
            # A patient collecting the same maintenance drug every month is the
            # ordinary case, not a duplicate.
            other = conn.execute(
                "SELECT id FROM consultations WHERE id <> ? LIMIT 1",
                (consultation_id,),
            ).fetchone()
            if other is None:
                print("UNIQUE (consultation, item): repeat-visit case not probed "
                      "(only one consultation on file)")
            else:
                try:
                    conn.execute("BEGIN")
                    conn.execute(
                        insert, (patient_id, consultation_id, item_id, 5, user_id))
                    conn.execute(
                        insert, (patient_id, other[0], item_id, 5, user_id))
                    conn.execute("ROLLBACK")
                    print("UNIQUE (consultation, item): allows the same medicine "
                          "at a later visit")
                except sqlite3.IntegrityError as exc:
                    conn.execute("ROLLBACK")
                    problems.append(
                        "the same medicine at a different visit was refused ({}) "
                        "-- a repeat issue is a real event".format(exc))

        # NOT NULL must reject a dispensing with no date.
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO medicine_dispensing "
                "(patient_id, consultation_id, inventory_item_id, medicine_name, "
                " unit, quantity_dispensed, date_dispensed, dispensed_by) "
                "VALUES (?, ?, ?, '__PROBE__', 'Tablet', 5, NULL, ?)",
                (patient_id, consultation_id, item_id, user_id),
            )
            conn.execute("ROLLBACK")
            problems.append("NOT NULL did not reject a dispensing with no date")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "NOT NULL constraint failed" not in str(exc):
                problems.append("undated dispensing rejected by {} rather than "
                                "NOT NULL".format(exc))
            else:
                print("NOT NULL (date_dispensed): rejects an undated dispensing")

        # The foreign key to inventory_items must actually bind. PRAGMA
        # foreign_keys is off by default in SQLite and has to be asked for, which
        # is exactly why this is worth probing rather than assuming.
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN")
            missing_item = conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM inventory_items"
            ).fetchone()[0]
            conn.execute(
                insert, (patient_id, consultation_id, missing_item, 5, user_id))
            conn.execute("ROLLBACK")
            problems.append("the inventory_item_id foreign key did not refuse an "
                            "item that does not exist")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "FOREIGN KEY constraint failed" not in str(exc):
                problems.append("nonexistent item rejected by {} rather than the "
                                "foreign key".format(exc))
            else:
                print("FOREIGN KEY (inventory_item_id): refuses an item that does "
                      "not exist")
        conn.execute("PRAGMA foreign_keys = OFF")

        left_behind = conn.execute(
            "SELECT COUNT(*) FROM medicine_dispensing WHERE medicine_name = '__PROBE__'"
        ).fetchone()[0]
        if left_behind:
            problems.append("{} probe rows survived their rollback".format(left_behind))

    # Nothing above may have moved a stock figure. Checked separately from the
    # row-for-row comparison so the failure, if it ever happens, names the thing
    # this migration most has to be innocent of.
    after_stock = {
        row["id"]: row["stock_quantity"]
        for row in conn.execute("SELECT id, stock_quantity FROM inventory_items")
    }
    if before["inventory_items"] is not None:
        for item_id, row in before["inventory_items"].items():
            if after_stock.get(item_id) != row["stock_quantity"]:
                problems.append(
                    "inventory_items id={} stock moved {} -> {} during the "
                    "migration".format(item_id, row["stock_quantity"],
                                       after_stock.get(item_id)))

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nmedicine_dispensing table present with its indexes and working "
          "constraints; every pre-existing table unchanged row for row, and no "
          "stock figure moved.")


if __name__ == "__main__":
    main()

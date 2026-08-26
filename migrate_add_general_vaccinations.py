"""Migration: add the general_vaccinations table.

The gap this closes: an adult who receives a vaccine at the health center had
nowhere in the system for it to go. The `immunizations` table exists to answer
"is this child on the DOH EPI schedule?", so it is scoped -- correctly -- to the
under-five cohort that schedule describes, and every screen that reads it is
scoped the same way. A 19-year-old having a hepatitis B dose is not part of that
question, and so was not recorded anywhere at all.

This adds the second, plainer kind of record: a vaccine was given, to this
patient, on this day, by this person, during this visit. No age restriction, and
deliberately no schedule column of any kind -- no due date, no status, no grace
period. There is no single official adult immunisation schedule in the
Philippines to evaluate against, so a due/overdue reading here would be invented
precision. The EPI logic in models/immunizations.py is untouched by this
migration and by the feature it supports; the two live side by side, which is the
same split HL7 FHIR draws between Immunization and ImmunizationRecommendation.

Idempotent -- re-running is a no-op. Follows migrate_add_immunizations.py
exactly: CREATE TABLE IF NOT EXISTS, snapshot every pre-existing table before,
compare row for row after, and prove the constraints actually refuse bad data
rather than merely being spelled out in the DDL.


WHY THE CONSTRAINTS ARE WHAT THEY ARE
-------------------------------------
UNIQUE (patient_id, vaccine_name, date_administered) rather than the EPI table's
UNIQUE (patient_id, vaccine_code, dose_number).

The EPI constraint says "a child cannot receive the same dose twice, ever",
because the schedule is a closed list with a fixed dose count per vaccine. That
is exactly wrong here: influenza is one shot every year for life, a Td booster a
decade later is a new dose and not a duplicate, and a rabies course is several
doses on consecutive days. A constraint spanning dose numbers would refuse real
clinical events.

What is still never right is the same vaccine, to the same patient, on the same
day -- that is one event, however many times a form is submitted. So the date is
what makes a row unique, which keeps double-clicking Save harmless (INSERT OR
IGNORE absorbs it) without refusing next year's flu shot.

dose_number is NULLABLE, unlike the EPI table's NOT NULL. Most of these vaccines
have no fixed dose count, and requiring a number would force a health worker to
invent one.

vaccine_name is TEXT holding the name itself, not a code. The EPI table stores a
code because EPI_SCHEDULE looks records up by it; nothing looks these up, the
entry form's list is an explicitly non-exhaustive convenience ending in a
free-text row, and a code for a vaccine nobody anticipated would have to be
invented at the point of typing.

The three foreign keys match the immunizations table exactly, for the reasons
that table's migration gives:

    patient_id       ON DELETE CASCADE  -- matches consultations
    consultation_id  ON DELETE SET NULL -- the vaccination happened whether or
                                           not its paperwork survives
    administered_by  ON DELETE RESTRICT -- an account cannot be deleted out from
                                           under a clinical record naming it

Run:  python migrate_add_general_vaccinations.py
"""
import sqlite3
import sys

import config

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS general_vaccinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_name TEXT NOT NULL,
    dose_number INTEGER,
    date_administered TEXT NOT NULL,
    administered_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (patient_id, vaccine_name, date_administered),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

INDEXES = (
    # The Patient Profile reads one patient's history, newest first.
    "CREATE INDEX IF NOT EXISTS idx_general_vaccinations_patient "
    "ON general_vaccinations(patient_id, date_administered)",
    # The consultation form reads back what was given during one visit.
    "CREATE INDEX IF NOT EXISTS idx_general_vaccinations_consultation "
    "ON general_vaccinations(consultation_id)",
)

# Every table whose contents must be exactly what they were. `immunizations` is
# listed first and deliberately: this migration exists alongside the EPI
# implementation rather than modifying it, and proving that table came through
# row for row unchanged is the point of the check, not a formality.
EXISTING_TABLES = (
    "immunizations", "users", "patients", "consultations", "inventory_items",
    "appointments", "audit_logs", "sms_broadcasts", "sms_broadcast_recipients",
    "settings",
)

EXPECTED_COLUMNS = [
    "id", "patient_id", "consultation_id", "vaccine_name", "dose_number",
    "date_administered", "administered_by", "created_at",
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
    existed = "general_vaccinations" in table_names(conn)
    print("general_vaccinations table before migration: "
          "{}".format("present" if existed else "absent"))
    for table, rows in before.items():
        print("  {:<26} {} rows".format(
            table, len(rows) if rows is not None else "(missing)"))

    conn.execute(TABLE_SQL)
    for statement in INDEXES:
        conn.execute(statement)
    conn.commit()

    present = "general_vaccinations" in table_names(conn)
    print("\ngeneral_vaccinations table after migration: "
          "{}".format("present" if present else "MISSING"))
    print("general vaccination rows: {}".format(
        conn.execute("SELECT COUNT(*) FROM general_vaccinations").fetchone()[0]))

    problems = []

    if not present:
        problems.append("general_vaccinations table was not created")

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

    columns = [row[1] for row in conn.execute("PRAGMA table_info(general_vaccinations)")]
    if columns != EXPECTED_COLUMNS:
        problems.append("columns are {}, expected {}".format(columns, EXPECTED_COLUMNS))

    # dose_number must be nullable -- the whole point of the column.
    nullable = {row[1]: not row[3] for row in
                conn.execute("PRAGMA table_info(general_vaccinations)")}
    if not nullable.get("dose_number", False):
        problems.append("dose_number is NOT NULL; it has to accept a vaccine with "
                        "no fixed dose count")
    for column in ("patient_id", "vaccine_name", "date_administered", "administered_by"):
        if nullable.get(column, True):
            problems.append("{} is nullable; it must not be".format(column))

    live_indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='general_vaccinations'"
        )
    }
    for name in ("idx_general_vaccinations_patient",
                 "idx_general_vaccinations_consultation"):
        if name not in live_indexes:
            problems.append("index {} missing after migration".format(name))

    # --- the constraints have to actually refuse, not merely be written -----
    #
    # Probes need a real patient and a real user to point at, so a database
    # migrated before anyone is registered simply skips them rather than
    # reporting a failure -- the same allowance migrate_add_immunizations.py
    # makes for its constraint probes.
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1) AS patient_id, "
        "       (SELECT id FROM users LIMIT 1) AS user_id"
    ).fetchone()

    if anchor["patient_id"] is None or anchor["user_id"] is None:
        print("constraints: not probed (no patient/user row to reference); "
              "DDL verified above")
    else:
        probe = (anchor["patient_id"], anchor["user_id"])

        # UNIQUE must reject the same vaccine to the same patient on the same day.
        try:
            conn.execute("BEGIN")
            for _ in range(2):
                conn.execute(
                    "INSERT INTO general_vaccinations "
                    "(patient_id, vaccine_name, dose_number, date_administered, "
                    " administered_by) VALUES (?, '__PROBE__', 1, '2026-01-01', ?)",
                    probe,
                )
            conn.execute("ROLLBACK")
            problems.append("UNIQUE did not reject the same vaccine twice on one day")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "UNIQUE constraint failed" not in str(exc):
                problems.append(
                    "same-day duplicate was rejected, but by {} rather than "
                    "UNIQUE".format(exc))
            else:
                print("UNIQUE (patient, vaccine, date): rejects the same vaccine "
                      "twice on one day")

        # ...and must NOT reject the same vaccine on a different day. This is the
        # constraint's whole reason for differing from the EPI table's: next
        # year's influenza shot is a real event, not a duplicate.
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO general_vaccinations "
                "(patient_id, vaccine_name, dose_number, date_administered, "
                " administered_by) VALUES (?, '__PROBE__', 1, '2026-01-01', ?)",
                probe,
            )
            conn.execute(
                "INSERT INTO general_vaccinations "
                "(patient_id, vaccine_name, dose_number, date_administered, "
                " administered_by) VALUES (?, '__PROBE__', 2, '2027-01-01', ?)",
                probe,
            )
            conn.execute("ROLLBACK")
            print("UNIQUE (patient, vaccine, date): allows the same vaccine in a "
                  "later year")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            problems.append(
                "the same vaccine on a later date was refused ({}) -- a repeat "
                "vaccination is a real event".format(exc))

        # dose_number must accept NULL: most of these have no dose count.
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO general_vaccinations "
                "(patient_id, vaccine_name, dose_number, date_administered, "
                " administered_by) VALUES (?, '__PROBE__', NULL, '2026-02-02', ?)",
                probe,
            )
            conn.execute("ROLLBACK")
            print("dose_number: accepts a vaccination with no dose number")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            problems.append("a vaccination with no dose number was refused: "
                            "{}".format(exc))

        # NOT NULL must reject a vaccination with no date.
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO general_vaccinations "
                "(patient_id, vaccine_name, dose_number, date_administered, "
                " administered_by) VALUES (?, '__PROBE__', 1, NULL, ?)",
                probe,
            )
            conn.execute("ROLLBACK")
            problems.append("NOT NULL did not reject a vaccination with no date")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "NOT NULL constraint failed" not in str(exc):
                problems.append("undated vaccination rejected by {} rather than "
                                "NOT NULL".format(exc))
            else:
                print("NOT NULL (date_administered): rejects an undated vaccination")

        left_behind = conn.execute(
            "SELECT COUNT(*) FROM general_vaccinations WHERE vaccine_name = '__PROBE__'"
        ).fetchone()[0]
        if left_behind:
            problems.append("{} probe rows survived their rollback".format(left_behind))

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\ngeneral_vaccinations table present with its indexes and working "
          "constraints; every pre-existing table unchanged row for row, "
          "immunizations included.")


if __name__ == "__main__":
    main()

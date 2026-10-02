"""Migration: let an immunisation record say whether this health center gave it.

So the schedule went on calling the child a defaulter, the follow-up list went on
chasing them, and the coverage figures went on counting a protected child as
unprotected.

Run: python migrations/migrate_add_immunization_source.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

# The two values `source` may hold. Named here so the verification below can tell
# a value this schema does not permit from a legitimate one, and so this file and
# models/immunizations.py cannot drift apart about the vocabulary.
SOURCE_ADMINISTERED = "administered"
SOURCE_REPORTED = "reported"
VALID_SOURCES = (SOURCE_ADMINISTERED, SOURCE_REPORTED)

# The table as schema.sql now declares it, verbatim apart from the name. `source`
# sits next to dose_number rather than at the end because it qualifies what the
# row claims about the dose, and the two CHECKs are the whole reason for the
# rebuild. Nothing else changes: same columns, same UNIQUE, same three foreign
# keys with the same delete rules.
NEW_TABLE_SQL = """
CREATE TABLE immunizations_migrated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_code TEXT NOT NULL,
    dose_number INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'administered'
        CHECK (source IN ('administered', 'reported')),
    date_administered TEXT,
    administered_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source = 'reported' OR date_administered IS NOT NULL),
    UNIQUE (patient_id, vaccine_code, dose_number),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

# Copied by name, never by position and never by SELECT *. `source` is
# deliberately absent from this list: every row that exists before this migration
# is a dose this health center recorded as its own work, so all of them take the
# 'administered' default. That is not a guess -- until this migration there was
# no other kind of row the form could write.
COPY_COLUMNS = (
    "id", "patient_id", "consultation_id", "vaccine_code", "dose_number",
    "date_administered", "administered_by", "notes", "created_at",
)

# Recreated after the swap, because DROP TABLE takes a table's indexes with it.
# Identical to the two schema.sql declares.
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_immunizations_patient "
    "ON immunizations(patient_id, date_administered)",
    "CREATE INDEX IF NOT EXISTS idx_immunizations_consultation "
    "ON immunizations(consultation_id)",
)


def table_info(conn):
    return list(conn.execute("PRAGMA table_info(immunizations)"))


def already_migrated(conn):
    """True when the live table already carries source and a nullable date.

    Both halves are asked, not just the column name. A database that somehow had
    `source` added by hand while date_administered was still NOT NULL would be
    half migrated, and reporting it as done would leave the undated reported dose
    impossible to write with no sign of why.
    """
    columns = {row[1]: row for row in table_info(conn)}
    if "source" not in columns:
        return False
    date_column = columns.get("date_administered")
    # PRAGMA table_info's fourth value is `notnull`.
    return bool(date_column) and date_column[3] == 0


def rebuild(conn):
    """Replace immunizations with the table above, carrying every row across.

    The sequence SQLite documents for altering a constraint. Foreign keys are off
    around the swap so the DROP cannot cascade into patients or consultations,
    and a foreign_key_check runs before they go back on.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(NEW_TABLE_SQL)
        columns = ", ".join(COPY_COLUMNS)
        conn.execute(
            "INSERT INTO immunizations_migrated ({0}) "
            "SELECT {0} FROM immunizations".format(columns)
        )
        conn.execute("DROP TABLE immunizations")
        conn.execute("ALTER TABLE immunizations_migrated RENAME TO immunizations")
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


def prove_constraints(conn):
    """Show the two new CHECKs refuse bad data rather than merely reading well.

    What migrate_add_immunizations.py did for the UNIQUE constraint when this
    table was created: a constraint spelled out in DDL and never exercised is a
    comment. Every probe below is rolled back, so nothing here reaches the
    database.
    """
    proofs, failures = [], []

    anchor = conn.execute(
        "SELECT patient_id, administered_by FROM immunizations LIMIT 1"
    ).fetchone()
    if anchor is None:
        anchor = conn.execute(
            "SELECT (SELECT id FROM patients LIMIT 1) AS patient_id, "
            "       (SELECT id FROM users LIMIT 1) AS administered_by"
        ).fetchone()
    if anchor is None or anchor["patient_id"] is None or anchor["administered_by"] is None:
        proofs.append("constraint probes skipped: no patient or user to anchor them to")
        return proofs, failures

    # (what is being tried, source, date) -- each one must be refused.
    probes = (
        ("an administered dose with no date", SOURCE_ADMINISTERED, None),
        ("a source the vocabulary does not contain", "guessed", "2026-01-01"),
    )
    for description, source, day in probes:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                INSERT INTO immunizations
                    (patient_id, vaccine_code, dose_number, source,
                     date_administered, administered_by)
                VALUES (?, 'PROBE', 99, ?, ?, ?)
                """,
                (anchor["patient_id"], source, day, anchor["administered_by"]),
            )
        except sqlite3.IntegrityError as exc:
            if "CHECK" in str(exc):
                proofs.append("refused {} ({})".format(description, exc))
            else:
                failures.append(
                    "{} was refused, but not by the expected constraint: {}".format(
                        description, exc)
                )
        else:
            failures.append(
                "{} was ACCEPTED -- the CHECK is not holding".format(description)
            )
        finally:
            conn.execute("ROLLBACK")

    # And the one that must still be accepted, or the migration has closed the
    # very door it was written to open.
    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO immunizations
                (patient_id, vaccine_code, dose_number, source,
                 date_administered, administered_by)
            VALUES (?, 'PROBE', 99, ?, NULL, ?)
            """,
            (anchor["patient_id"], SOURCE_REPORTED, anchor["administered_by"]),
        )
    except sqlite3.IntegrityError as exc:
        failures.append("an undated reported dose was refused: {}".format(exc))
    else:
        proofs.append("accepted a reported dose with no date, which is the point")
    finally:
        conn.execute("ROLLBACK")

    return proofs, failures


def main():
    # isolation_level=None: this script issues its own BEGIN/COMMIT around the
    # rebuild, and PRAGMA foreign_keys is ignored inside a transaction, so the
    # implicit one Python would otherwise open has to be out of the way.
    conn = sqlite3.connect(config.DATABASE, isolation_level=None)
    conn.row_factory = sqlite3.Row

    select_all = "SELECT {} FROM immunizations ORDER BY id".format(", ".join(COPY_COLUMNS))

    before_count = conn.execute("SELECT COUNT(*) FROM immunizations").fetchone()[0]
    before_rows = {row["id"]: dict(row) for row in conn.execute(select_all)}
    print("immunizations before migration: {}".format(before_count))

    problems = []
    if already_migrated(conn):
        print("source column and nullable date_administered: already present "
              "-- rebuild skipped")
    else:
        print("rebuilding immunizations: adding source, relaxing date_administered")
        violations = rebuild(conn)
        if violations:
            problems.append(
                "foreign_key_check reported {} violations".format(len(violations))
            )

    after_count = conn.execute("SELECT COUNT(*) FROM immunizations").fetchone()[0]
    after_rows = {row["id"]: dict(row) for row in conn.execute(select_all)}
    print("immunizations after migration:  {}".format(after_count))

    if before_count != after_count:
        problems.append(
            "row count changed: {} -> {}".format(before_count, after_count)
        )

    for row_id, old in before_rows.items():
        new = after_rows.get(row_id)
        if new is None:
            problems.append("immunization #{} disappeared".format(row_id))
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(
                    "immunization #{}.{}: {!r} -> {!r}".format(
                        row_id, column, value, new[column])
                )

    # Two different questions, kept apart the way
    # migrate_add_consultation_restriction.py keeps its two apart.
    #
    # On EVERY run, a value outside the vocabulary is damage: the CHECK refuses
    # one on write, but a CHECK is only consulted on write, and a value written
    # by a tool that went around it would sit there unnoticed.
    #
    # Only on the run that DOES the rebuild is "every row is administered" a real
    # invariant. After that the feature is live, a reported dose on file is the
    # feature working, and a re-run must not fail on finding one.
    source_counts = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT source, COUNT(*) FROM immunizations GROUP BY source"
        )
    }
    for source, count in sorted(source_counts.items(), key=lambda kv: str(kv[0])):
        if source not in VALID_SOURCES:
            problems.append(
                "{} rows have source {!r}, which the schema does not permit "
                "(allowed: {})".format(count, source, ", ".join(VALID_SOURCES))
            )

    # The invariant that outlives the rebuild: whatever a row's source, a dose
    # this health center administered says when it was given. The CHECK read back
    # from the data rather than from the DDL.
    undated_administered = conn.execute(
        "SELECT COUNT(*) FROM immunizations "
        " WHERE source = ? AND date_administered IS NULL",
        (SOURCE_ADMINISTERED,),
    ).fetchone()[0]
    if undated_administered:
        problems.append(
            "{} rows claim this health center administered a dose but carry no "
            "date".format(undated_administered)
        )

    proofs, failures = prove_constraints(conn)
    problems.extend(failures)

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    for proof in proofs:
        print("  constraint proof:", proof)

    print(
        "\nAll pre-existing column values preserved byte-for-byte; every source "
        "is one the schema permits ({}={}, {}={}), and no dose this health "
        "center claims to have administered is undated.".format(
            SOURCE_ADMINISTERED, source_counts.get(SOURCE_ADMINISTERED, 0),
            SOURCE_REPORTED, source_counts.get(SOURCE_REPORTED, 0),
        )
    )


if __name__ == "__main__":
    main()

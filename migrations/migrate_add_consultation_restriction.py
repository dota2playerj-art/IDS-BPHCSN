"""Migration: give a consultation somewhere to record that it is confidential.

So nothing here guesses. `is_restricted` is a flag the licensed clinician sets,
on the entry they judge to be sensitive, for whatever reason they judge it. The
schema holds the decision; it does not make it.

Run: python migrations/migrate_add_consultation_restriction.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

# (column_name, column_definition) in the order they are added.
#
# is_restricted takes NOT NULL DEFAULT 0, so every consultation already on file
# comes out of this migration explicitly unsealed rather than NULL. "Nobody has
# decided about this record" and "somebody decided it is not sensitive" are the
# same thing here -- the flag is what a clinician sets, and the absence of one is
# the ordinary state of a clinical record.
#
# restricted_by carries a REFERENCES clause and no default, which SQLite requires
# for a column added by ALTER TABLE when foreign keys are on: it must default to
# NULL. ON DELETE is deliberately absent, which leaves it at the SQLite default of
# NO ACTION -- consultations.recorded_by is ON DELETE RESTRICT for the same reason
# and nothing in this application deletes an account.
NEW_COLUMNS = [
    ("is_restricted", "INTEGER NOT NULL DEFAULT 0 CHECK (is_restricted IN (0, 1))"),
    ("restricted_by", "INTEGER REFERENCES users(id)"),
    ("restricted_at", "TEXT"),
]

# The only two values the CHECK above permits. Named here so the verification
# below can tell "a value this schema does not allow" from a legitimate seal.
VALID_FLAGS = (0, 1)


def existing_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(consultations)")}


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before_count = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    before_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM consultations ORDER BY id")
    }
    print(f"consultations before migration: {before_count}")

    present = existing_columns(conn)
    added, skipped = [], []
    for name, definition in NEW_COLUMNS:
        if name in present:
            skipped.append(name)
            continue
        conn.execute(f"ALTER TABLE consultations ADD COLUMN {name} {definition}")
        added.append(name)
    conn.commit()

    print(f"columns added:   {added if added else '(none)'}")
    print(f"already present: {skipped if skipped else '(none)'}")

    after_count = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    after_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM consultations ORDER BY id")
    }

    print(f"consultations after migration:  {after_count}")

    problems = []
    if before_count != after_count:
        problems.append(f"row count changed: {before_count} -> {after_count}")

    for row_id, old in before_rows.items():
        new = after_rows.get(row_id)
        if new is None:
            problems.append(f"consultation #{row_id} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(
                    f"consultation #{row_id}.{column}: {value!r} -> {new[column]!r}"
                )

    # Two different questions, kept apart exactly as
    # migrate_add_inventory_columns.py keeps its two apart, and for the same
    # reason.
    #
    # On the run that ADDS the column, SQLite backfills every existing row from
    # the DEFAULT, so all of them must come out 0. That is a real invariant about
    # this migration's own work and it is asserted -- but only on the run that
    # does the adding.
    #
    # On a re-run the column is already there and the Administrator has been able
    # to seal records in between. A sealed consultation is the feature working,
    # not damage, so a re-run must not fail on finding one.
    #
    # What is worth catching on EVERY run is a value the schema does not permit.
    # The CHECK refuses one on write, but a CHECK is only consulted on write: a
    # value written by a tool that went around it would sit there unnoticed.
    flag_counts = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT is_restricted, COUNT(*) FROM consultations GROUP BY is_restricted"
        )
    }

    for flag, count in sorted(flag_counts.items(), key=lambda kv: str(kv[0])):
        if flag not in VALID_FLAGS:
            problems.append(
                f"{count} rows have is_restricted {flag!r}, which the schema does "
                f"not permit (allowed: {', '.join(str(v) for v in VALID_FLAGS)})"
            )

    if "is_restricted" in added:
        not_defaulted = sum(
            count for flag, count in flag_counts.items() if flag != 0
        )
        if not_defaulted:
            problems.append(
                f"{not_defaulted} rows did not take the 0 default on the run "
                "that added the column"
            )

    # The three columns have to agree with each other. A row claiming to be
    # sealed by nobody, or naming a sealer while carrying no seal, is a record
    # whose confidentiality state cannot be explained on screen -- and the
    # Patient Profile prints that explanation next to the placeholder it shows
    # Staff, so an inconsistent row would put an unanswerable sentence in front
    # of a health worker.
    inconsistent = conn.execute(
        """
        SELECT COUNT(*) FROM consultations
         WHERE (is_restricted = 1 AND (restricted_by IS NULL OR restricted_at IS NULL))
            OR (is_restricted = 0 AND (restricted_by IS NOT NULL OR restricted_at IS NOT NULL))
        """
    ).fetchone()[0]
    if inconsistent:
        problems.append(
            f"{inconsistent} rows have is_restricted disagreeing with "
            "restricted_by / restricted_at"
        )

    # Every sealer must be a real account. The REFERENCES clause enforces this on
    # write only when foreign keys are switched on for the connection doing the
    # writing, so it is asserted here rather than assumed.
    orphaned = conn.execute(
        """
        SELECT COUNT(*) FROM consultations c
         WHERE c.restricted_by IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = c.restricted_by)
        """
    ).fetchone()[0]
    if orphaned:
        problems.append(f"{orphaned} rows name a restricted_by account that does not exist")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    sealed = flag_counts.get(1, 0)
    print(
        "\nAll pre-existing column values preserved byte-for-byte; every "
        f"is_restricted is one the schema permits (0={flag_counts.get(0, 0)}, "
        f"1={sealed}), and every row's three restriction columns agree."
    )


if __name__ == "__main__":
    main()

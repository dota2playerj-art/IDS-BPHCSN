"""Seal all free text of restricted visits, and remove free clinical text from old audit entries.

The database defaults to app.db (config.DATABASE). Run python setup_env.py
first: step 4 needs SEALED_DATA_KEY in .env.

Run: python migrations/migrate_seal_free_text_fields.py (project root). Safe to run twice.
"""
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config  # loads .env into the environment
from utils import sealed_crypto

PROJECT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "seal-free-text-fields"

# The consultation columns this task adds to the sealed set, and the queue visit's.
CONSULTATION_FIELDS = ("chief_complaint", "remarks")
VISIT_TABLE, VISIT_FIELD = "appointments", "notes"

LABELS = ("Chief complaint", "Additional notes", "Check-in reason", "Reason for visit")
REMOVED = "(clinical text removed)"
# A rendered value in an edit entry: quoted text, or one of two fixed words.
_VALUE = r'(?:not recorded|\[withheld — Restricted\]|".*?")'
PATTERNS = [
    re.compile(rf"({re.escape(label)}): {_VALUE} → {_VALUE}(?=; |$)", re.S)
    for label in LABELS
]
# What must not be left in any entry afterwards.
LEFTOVER = re.compile(rf'(?:{"|".join(re.escape(l) for l in LABELS)}): [^;]*"')

ACTION = "Sealed all free text of restricted visits"
MODULE = "Medical Confidentiality"
REASON = ("Free clinical text removed from earlier audit entries, and the free "
          "text of restricted visits encrypted, to protect patient privacy "
          "(RA 11166 Section 44, RA 10173).")


def redact(details):
    """The entry text with free clinical text removed. Unchanged if none."""
    if not details:
        return details
    for pattern in PATTERNS:
        # Only a pair that quotes text. "[withheld — Restricted]" holds none.
        details = pattern.sub(
            lambda m: f"{m.group(1)}: {REMOVED}" if '"' in m.group(0) else m.group(0),
            details)
    return details


def _backup(db_path, backup_dir):
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{Path(db_path).name}.PRETASK_BACKUP_{TASK}_{stamp}"
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def _counts(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def _needs_sealing(value):
    return value not in (None, "") and not sealed_crypto.is_encrypted(value)


def _plan(conn):
    entries = [(row["id"], row["details"], redact(row["details"]))
               for row in conn.execute("SELECT id, details FROM audit_logs ORDER BY id")]
    entries = [(i, old, new) for i, old, new in entries if new != old]
    sealed = list(conn.execute(
        f"SELECT id, appointment_id, {', '.join(CONSULTATION_FIELDS)} "
        "FROM consultations WHERE is_restricted = 1 ORDER BY id"))
    consultations, visits = [], []
    for row in sealed:
        if any(_needs_sealing(row[f]) for f in CONSULTATION_FIELDS):
            consultations.append(row)
        if row["appointment_id"]:
            visit = conn.execute(
                f"SELECT id, {VISIT_FIELD} FROM {VISIT_TABLE} WHERE id = ?",
                (row["appointment_id"],)).fetchone()
            if visit is not None and _needs_sealing(visit[VISIT_FIELD]):
                visits.append(visit)
    recorded = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action = ?", (ACTION,)).fetchone()[0]
    return entries, consultations, visits, recorded


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    problem = sealed_crypto.key_problem(os.environ.get("SEALED_DATA_KEY", ""))
    if problem:
        raise SystemExit("Stopped. " + problem)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA secure_delete = ON")
    result = {"database": db_path, "backup": None, "entries_redacted": 0,
              "consultations_encrypted": 0, "visits_encrypted": 0,
              "record_written": False, "problems": []}
    try:
        entries, consultations, visits, recorded = _plan(conn)
        if not entries and not consultations and not visits and recorded:
            return result  # nothing to change: no copy, no write

        result["backup"] = str(_backup(db_path, backup_dir))
        before_counts = _counts(conn)
        before_audit = {r["id"]: tuple(r) for r in conn.execute(
            "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")

        conn.execute("BEGIN")
        for entry_id, _old, new in entries:
            conn.execute("UPDATE audit_logs SET details = ? WHERE id = ?", (new, entry_id))
        plain = {}
        for row in consultations:
            plain[row["id"]] = {f: row[f] for f in CONSULTATION_FIELDS}
            conn.execute(
                f"UPDATE consultations SET "
                f"{', '.join(f'{f} = ?' for f in CONSULTATION_FIELDS)} WHERE id = ?",
                [row[f] if sealed_crypto.is_encrypted(row[f])
                 else sealed_crypto.encrypt(row[f], row["id"], f)
                 for f in CONSULTATION_FIELDS]
                + [row["id"]])
        plain_visits = {}
        for visit in visits:
            plain_visits[visit["id"]] = visit[VISIT_FIELD]
            conn.execute(
                f"UPDATE {VISIT_TABLE} SET {VISIT_FIELD} = ? WHERE id = ?",
                (sealed_crypto.encrypt(visit[VISIT_FIELD], visit["id"], VISIT_FIELD,
                                       VISIT_TABLE), visit["id"]))
        details = (
            f"Done by the migration script migrate_seal_free_text_fields.py, "
            f"not by this account. {len(entries)} earlier "
            f"entr{'y' if len(entries) == 1 else 'ies'} changed; "
            f"{len(consultations)} restricted consultation"
            f"{'' if len(consultations) == 1 else 's'} and {len(visits)} check-in "
            f"reason{'' if len(visits) == 1 else 's'} encrypted. {REASON}")
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
            (actor["id"], ACTION, MODULE, details))

        # Checks, before anything is committed.
        problems = result["problems"]
        after_counts = _counts(conn)
        expected = dict(before_counts, audit_logs=before_counts["audit_logs"] + 1)
        if after_counts != expected:
            problems.append("a table's row count changed")
        after_audit = {r["id"]: tuple(r) for r in conn.execute(
            "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
        if any(after_audit.get(i) != row for i, row in before_audit.items()):
            problems.append("an audit entry's who, when or action changed")
        if any(LEFTOVER.search(r[0] or "") for r in conn.execute(
                "SELECT details FROM audit_logs")):
            problems.append("quoted free text is still in an audit entry")
        for cid, fields in plain.items():
            row = conn.execute(
                f"SELECT {', '.join(CONSULTATION_FIELDS)} FROM consultations WHERE id = ?",
                (cid,)).fetchone()
            for f in CONSULTATION_FIELDS:
                if not _needs_sealing(fields[f]):
                    continue
                stored = row[f]
                # Checked with the same module the app uses. The migration is the
                # one place outside open_sealed_value() allowed to decrypt.
                if (not sealed_crypto.is_encrypted(stored)
                        or sealed_crypto.decrypt(stored, cid, f) != fields[f]):
                    problems.append(f"consultation {cid} {f} did not encrypt correctly")
        for vid, text in plain_visits.items():
            stored = conn.execute(
                f"SELECT {VISIT_FIELD} FROM {VISIT_TABLE} WHERE id = ?",
                (vid,)).fetchone()[VISIT_FIELD]
            if (not sealed_crypto.is_encrypted(stored)
                    or sealed_crypto.decrypt(stored, vid, VISIT_FIELD, VISIT_TABLE) != text):
                problems.append(f"queue visit {vid} reason did not encrypt correctly")
        if problems:
            conn.execute("ROLLBACK")
            result["backup_note"] = "Nothing was changed."
            return result
        conn.execute("COMMIT")
        result.update(entries_redacted=len(entries),
                      consultations_encrypted=len(consultations),
                      visits_encrypted=len(visits), record_written=True)
        conn.execute("VACUUM")
        return result
    finally:
        conn.close()


def main(argv):
    db_path = argv[0] if argv else config.DATABASE
    print(f"database: {db_path}")
    result = run(db_path)
    if result["problems"]:
        print("STOPPED. Nothing was changed:")
        for problem in result["problems"]:
            print(f"  - {problem}")
        return 1
    if not result["backup"]:
        print("Nothing to do. It has already run, and no free clinical text is left.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"audit entries with free clinical text removed: {result['entries_redacted']}")
    print(f"restricted consultations encrypted: {result['consultations_encrypted']}")
    print(f"check-in reasons encrypted: {result['visits_encrypted']}")
    print("one audit entry written recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

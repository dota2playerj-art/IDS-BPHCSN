"""Remove diagnosis and treatment text from old audit entries, and encrypt sealed records.

usage:
    python migrate_redact_clinical_audit_text.py [database]

The database defaults to app.db (config.DATABASE). Run python setup_env.py
first: step 4 needs SEALED_DATA_KEY in .env.

WHY (Task 5, H4; RA 11166 Section 44, RA 10173)
-----------------------------------------------
Audit Logs are read and exported by the Administrator, who is not a physician.
Older consultation-edit entries quote the diagnosis and treatment plan, for
example 'Diagnosis: "A" → "B"'. Sealed consultations still hold those two
fields as plain text, so the backup file carries them.

WHAT IT DOES, IN ORDER
----------------------
1. Looks for work. When there is nothing to change and the record of an earlier
   run exists, it makes no copy and writes nothing.
2. Copies the database into IDS-BPHCSN-backups next to the project, with a
   timestamped name, before it changes anything.
3. In every audit entry, replaces the quoted text after "Diagnosis:" and
   "Treatment plan / medicines given:" with "(clinical text removed)". Who,
   when, the action and the record reference stay as they are.
4. Encrypts the diagnosis and treatment plan of every sealed consultation still
   holding plain text (utils/sealed_crypto.py).
5. Writes ONE audit entry saying the redaction ran, how many entries it changed
   and why. audit_logs.user_id must name an account, and no "system" account
   exists, so it is filed under the first active Administrator account. The
   entry says the migration did it, not that person.
6. Checks before committing: only those fields moved, every encrypted value
   decrypts back to its old text, and no quoted clinical text is left.
7. Runs VACUUM, so the old plain text does not stay in the file's free space.

Safe to run twice. The second run finds nothing to change and writes nothing.
"""
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import config  # loads .env into the environment
from utils import sealed_crypto

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "redact-clinical-audit-text"

SEALED_FIELDS = ("diagnosis", "treatment_plan")
LABELS = ("Diagnosis", "Treatment plan / medicines given")
REMOVED = "(clinical text removed)"
# A rendered value in an edit entry: quoted text, or one of two fixed words.
_VALUE = r'(?:not recorded|\[withheld — Restricted\]|".*?")'
PATTERNS = [
    re.compile(rf"({re.escape(label)}): {_VALUE} → {_VALUE}(?=; |$)", re.S)
    for label in LABELS
]
# What must not be left in any entry afterwards.
LEFTOVER = re.compile(r'(?:Diagnosis|Treatment plan / medicines given): [^;]*"')

ACTION = "Removed clinical text from earlier audit entries"
MODULE = "Medical Confidentiality"
REASON = ("Clinical text removed from earlier entries to protect patient "
          "privacy (RA 11166, RA 10173).")


def redact(details):
    """The entry text with diagnosis and treatment text removed. Unchanged if none."""
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


def _plan(conn):
    entries = [(row["id"], row["details"], redact(row["details"]))
               for row in conn.execute("SELECT id, details FROM audit_logs ORDER BY id")]
    entries = [(i, old, new) for i, old, new in entries if new != old]
    sealed = [row for row in conn.execute(
        f"SELECT id, {', '.join(SEALED_FIELDS)} FROM consultations "
        "WHERE is_restricted = 1 ORDER BY id")
        if any(row[f] not in (None, "") and not sealed_crypto.is_encrypted(row[f])
               for f in SEALED_FIELDS)]
    recorded = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action = ?", (ACTION,)).fetchone()[0]
    return entries, sealed, recorded


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
              "records_encrypted": 0, "record_written": False, "problems": []}
    try:
        entries, sealed, recorded = _plan(conn)
        if not entries and not sealed and recorded:
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
        for row in sealed:
            plain[row["id"]] = {f: row[f] for f in SEALED_FIELDS}
            conn.execute(
                f"UPDATE consultations SET {', '.join(f'{f} = ?' for f in SEALED_FIELDS)} "
                "WHERE id = ?",
                [row[f] if sealed_crypto.is_encrypted(row[f])
                 else sealed_crypto.encrypt(row[f], row["id"], f)
                 for f in SEALED_FIELDS]
                + [row["id"]])
        details = (
            f"Done by the migration script migrate_redact_clinical_audit_text.py, "
            f"not by this account. {len(entries)} earlier "
            f"entr{'y' if len(entries) == 1 else 'ies'} changed; "
            f"{len(sealed)} sealed consultation{'' if len(sealed) == 1 else 's'} "
            f"encrypted. {REASON}")
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
            problems.append("quoted clinical text is still in an audit entry")
        for cid, fields in plain.items():
            row = conn.execute(
                f"SELECT {', '.join(SEALED_FIELDS)} FROM consultations WHERE id = ?",
                (cid,)).fetchone()
            for f in SEALED_FIELDS:
                if fields[f] in (None, "") or sealed_crypto.is_encrypted(fields[f]):
                    continue
                stored = row[f]
                # Checked with the same module the app uses. The migration is the
                # one place outside open_sealed_value() allowed to decrypt.
                if (not sealed_crypto.is_encrypted(stored)
                        or sealed_crypto.decrypt(stored, cid, f) != fields[f]):
                    problems.append(f"consultation {cid} {f} did not encrypt correctly")
        if problems:
            conn.execute("ROLLBACK")
            result["backup_note"] = "Nothing was changed."
            return result
        conn.execute("COMMIT")
        result.update(entries_redacted=len(entries), records_encrypted=len(sealed),
                      record_written=True)
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
        print("Nothing to do. It has already run, and no clinical text is left.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"audit entries with clinical text removed: {result['entries_redacted']}")
    print(f"sealed consultations encrypted: {result['records_encrypted']}")
    print("one audit entry written recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

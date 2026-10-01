"""Mask phone numbers in earlier audit entries.

usage:
    python migrate_mask_audit_phone_numbers.py [database]

The database defaults to app.db (config.DATABASE).

WHY (Task 5e; RA 10173, the minimum-necessary standard)
-------------------------------------------------------
Since Task 5d a phone number shows only its last four digits on every SMS
screen. Audit entries are now written that way too (models/audit.py log_action()).
Older entries could still quote a whole number in their text, for example an
appointment SMS entry. This rewrites them, so no stored audit text holds one.

WHAT IT DOES, IN ORDER
----------------------
1. Looks for work. When there is nothing to change and the record of an earlier
   run exists, it makes no copy and writes nothing.
2. Copies the database into IDS-BPHCSN-backups next to the project, with a
   timestamped name, before it changes anything.
3. Masks every phone-like number in audit text to its last four digits. Who, when,
   the action, the module and the rest of the text stay.
4. Writes ONE audit entry recording the run, under the first active Administrator,
   as migrate_admin_minimum_necessary.py does.
5. Checks before committing: only those entries moved, who, when and action are
   unchanged, no table's row count changed except audit_logs by one, and no number
   is left. Any problem rolls everything back.

Safe to run twice. The second run finds nothing to change and writes nothing.
It prints counts only.
"""
import sqlite3
import sys
from pathlib import Path

import config  # loads .env into the environment
from migrate_admin_minimum_necessary import BACKUP_DIR, _counts
from migrate_admin_minimum_necessary import _backup as _backup_with_task
import migrate_admin_minimum_necessary as _first
from utils.phone import _PH_MOBILE_IN_TEXT, mask_numbers_in_text

ACTION = "Masked phone numbers in earlier audit entries"
MODULE = "Medical Confidentiality"
REASON = ("A phone number shows only its last four digits everywhere it is shown "
          "(RA 10173, the minimum-necessary standard).")


def _backup(db_path, backup_dir):
    _first.TASK = "mask-audit-phone-numbers"
    return _backup_with_task(db_path, backup_dir)


def _plan(conn):
    entries = []
    for row in conn.execute("SELECT id, details FROM audit_logs ORDER BY id"):
        if row["details"] and _PH_MOBILE_IN_TEXT.search(row["details"]):
            entries.append((row["id"], mask_numbers_in_text(row["details"])))
    recorded = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action = ?", (ACTION,)).fetchone()[0]
    return entries, recorded


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA secure_delete = ON")
    result = {"database": db_path, "backup": None, "entries_masked": 0,
              "record_written": False, "problems": []}
    try:
        entries, recorded = _plan(conn)
        if not entries and recorded:
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
        for entry_id, new in entries:
            conn.execute("UPDATE audit_logs SET details = ? WHERE id = ?", (new, entry_id))
        details = (
            "Done by the migration script migrate_mask_audit_phone_numbers.py, not by "
            f"this account. {len(entries)} earlier "
            f"entr{'y' if len(entries) == 1 else 'ies'} changed to show phone numbers "
            f"as their last four digits. {REASON}")
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
            (actor["id"], ACTION, MODULE, details))

        problems = result["problems"]
        if _counts(conn) != dict(before_counts, audit_logs=before_counts["audit_logs"] + 1):
            problems.append("a table's row count changed")
        after_audit = {r["id"]: tuple(r) for r in conn.execute(
            "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
        if any(after_audit.get(i) != row for i, row in before_audit.items()):
            problems.append("an audit entry's who, when or action changed")
        if _plan(conn)[0]:
            problems.append("an entry still holds a whole phone number")
        if problems:
            conn.execute("ROLLBACK")
            return result
        conn.execute("COMMIT")
        result.update(entries_masked=len(entries), record_written=True)
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
        print("Nothing to do. It has already run, and no whole number is left.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"audit entries masked: {result['entries_masked']}")
    print("one audit entry written recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

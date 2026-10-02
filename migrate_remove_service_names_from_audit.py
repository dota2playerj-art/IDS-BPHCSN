"""Migration: take visit service names out of earlier audit entries (Task 6c, L32).

usage:
    python migrate_remove_service_names_from_audit.py [database]

The database defaults to app.db (config.DATABASE).

WHY
---
A service names a clinical fact (a prenatal check-up, an immunization). The Administrator
reads the Audit Logs, so no entry may name a visit's service. Task 6b wrote
"Changed the service of visit APT-00081 from Consultation to Immunization." The entry is
now "Corrected the service of visit APT-00081." This rewords the earlier ones.

WHAT IT DOES, IN ORDER
----------------------
1. Looks for entries of the action "Changed the service of a visit" whose text still has
   "from ... to ...". When there are none, it makes no copy and writes nothing.
2. Copies the database into IDS-BPHCSN-backups next to the project, with a timestamped
   name, before it changes anything.
3. Rewrites the `details` of those entries to "Corrected the service of visit <ref>.",
   keeping a trailing "The visit is now Completed." Who, when, the action and the module
   stay as they are.
4. Writes ONE audit entry recording the run, with the count. audit_logs.user_id must name
   an account, and no "system" account exists, so it is filed under the first active
   Administrator. The entry says the migration did it, not that person.
5. Checks before it commits: only `details` of those entries moved, no entry still names
   a service, and the audit table gained exactly one row. Any problem rolls it back.

Safe to run twice: the second run finds nothing to reword. It prints counts only.
"""
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "remove-service-names-from-audit"

SERVICE_ACTION = "Changed the service of a visit"
ACTION = "Reworded service names in earlier audit entries"
MODULE = "Medical Confidentiality"
_OLD = re.compile(r"^Changed the service of visit (APT-\d{5}) from .+ to .+?\.( The visit is now Completed\.)?$")
_DONE = " The visit is now Completed."


def reworded(details):
    """The new text for an old entry, or None when it needs no change."""
    match = _OLD.match(details or "")
    if not match:
        return None
    return f"Corrected the service of visit {match.group(1)}." + (_DONE if match.group(2) else "")


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


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    result = {"database": db_path, "backup": None, "reworded": 0, "problems": []}
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        changes = []
        for row in conn.execute("SELECT id, details FROM audit_logs WHERE action = ? ORDER BY id",
                                (SERVICE_ACTION,)):
            new = reworded(row["details"])
            if new is not None:
                changes.append((row["id"], new))
        if not changes:
            return result
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")
        result["backup"] = str(_backup(db_path, backup_dir))
        before = {r["id"]: tuple(r) for r in conn.execute(
            "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
        count_before = len(before)
        conn.execute("BEGIN")
        try:
            for entry_id, new in changes:
                conn.execute("UPDATE audit_logs SET details = ? WHERE id = ?", (new, entry_id))
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_remove_service_names_from_audit.py, "
                 f"not by this account. {len(changes)} earlier "
                 f"entr{'y' if len(changes) == 1 else 'ies'} reworded so that no audit entry "
                 "names a visit's service."))
            problems = result["problems"]
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != count_before + 1:
                problems.append("the audit table did not gain exactly one row")
            after = {r["id"]: tuple(r) for r in conn.execute(
                "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
            if any(after.get(i) != v for i, v in before.items()):
                problems.append("something other than the text of the entries changed")
            if any(_OLD.match(r["details"] or "") for r in conn.execute(
                    "SELECT details FROM audit_logs WHERE action = ?", (SERVICE_ACTION,))):
                problems.append("an entry still names a service")
            conn.execute("ROLLBACK" if problems else "COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result["reworded"] = len(changes) if not result["problems"] else 0
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
        print("Nothing to do. No entry names a service.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"entries reworded: {result['reworded']}")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

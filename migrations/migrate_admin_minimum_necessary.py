"""Remove patient-linked clinical details from earlier audit entries.

The database defaults to app.db (config.DATABASE).

Run: python migrations/migrate_admin_minimum_necessary.py (project root). Safe to run twice.
"""
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "admin-minimum-necessary"

DISPENSED = "Dispensed medicine"
DOSE_ACTIONS = ("Recorded EPI immunisation doses", "Recorded doses given elsewhere",
                "Recorded other vaccinations")
CONSULTATION_UPDATED = "Updated consultation record"
CORRECTIONS = ("Corrected EPI immunisation record", "Corrected other vaccination record")
APPOINTMENT_SMS = "Sent appointment SMS to patient"

# Consultation field labels, in form order (models/consultations.py FIELD_LABELS).
CONSULTATION_LABELS = (
    "Chief complaint", "Temperature", "Blood pressure", "Pulse rate",
    "Respiratory rate", "Weight", "Height", "Head circumference", "Diagnosis",
    "Treatment plan / medicines given", "Additional notes", "Follow-up date",
)
# The dose and dispensing phrases an edit entry carried, and the name each is
# listed under now (routes/consultation_views.py _describe_dose_changes()).
EDIT_PHRASES = (
    ("Immunisations added", "immunisations added"),
    ("Immunisations removed", "immunisations removed"),
    ("Doses recorded as previously given elsewhere", "doses reported as given elsewhere"),
    ("Other vaccinations added", "other vaccinations added"),
    ("Medicine dispensed", "items dispensed"),
)
CORRECTION_LABELS = ("Vaccine / dose", "Vaccine", "Dose number", "Date given")

ACTION = "Removed patient clinical details from earlier audit entries"
MODULE = "Medical Confidentiality"
REASON = ("Clinical data is for the care team only, and Audit Logs are read by the "
          "Administrator (RA 11166, RA 10173, the minimum-necessary standard).")

_DISPENSED_OLD = re.compile(r"^For (?P<who>.+?)(?:, consultation #(?P<cid>\d+))?: (?P<items>.*)$", re.S)
_DOSES_OLD = re.compile(r"^(?P<count>\d+ doses?) for (?P<who>.+?) at consultation #(?P<cid>\d+): .*$", re.S)


def _count(n, noun):
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _dispensed(details):
    match = _DISPENSED_OLD.match(details or "")
    if not match:
        return details
    items = match.group("items")
    restricted = re.match(r"^(\d+) items?\. Names not shown", items)
    if restricted:
        n = int(restricted.group(1))
    else:
        n = len(re.findall(r"(?:^|, )\d+ [^,]*? of ", items)) or None
    where = f" at consultation #{match.group('cid')}" if match.group("cid") else ""
    counted = f" {_count(n, 'item')}" if n else " items"
    return f"Dispensed{counted} for {match.group('who')}{where}."


def _doses(details):
    match = _DOSES_OLD.match(details or "")
    if not match:
        return details
    return (f"Recorded {match.group('count')} for {match.group('who')} at "
            f"consultation #{match.group('cid')}.")


def _named(tail, labels):
    """The labels a summary mentions, in the given order."""
    found = []
    listed = []
    for part in re.findall(r"Changed: ([^;]*)", tail):
        listed += [name.strip() for name in part.split(",")]
    for label in labels:
        if re.search(rf"(?:^|; ){re.escape(label)}: ", tail) or label in listed:
            found.append(label)
    return found


def _consultation_edit(details):
    head, sep, tail = (details or "").partition(" changed — ")
    if not sep:
        return details
    names = _named(tail, CONSULTATION_LABELS)
    for phrase, name in EDIT_PHRASES:
        if re.search(rf"(?:^|; ){re.escape(phrase)}: ", tail) or name in tail:
            names.append(name)
    new_tail = ("Changed: " + ", ".join(names)) if names else "(clinical text removed)"
    return head + sep + new_tail


def _correction(details):
    head, sep, tail = (details or "").partition(" corrected — ")
    if not sep:
        return details
    names = _named(tail, CORRECTION_LABELS)
    new_tail = ("Changed: " + ", ".join(names)) if names else "(clinical text removed)"
    return head + sep + new_tail


def _appointment_sms(details):
    text = re.sub(r" on [^,]*, about appointment", ", about appointment", details or "")
    return re.sub(r'; message: ".*"\s*$', "; message removed", text, flags=re.S)


REWRITERS = {DISPENSED: _dispensed, CONSULTATION_UPDATED: _consultation_edit,
             APPOINTMENT_SMS: _appointment_sms}
REWRITERS.update({action: _doses for action in DOSE_ACTIONS})
REWRITERS.update({action: _correction for action in CORRECTIONS})


def rewrite(action, details):
    """The entry text as Task 5c writes it. Unchanged if it already is."""
    rewriter = REWRITERS.get(action)
    return rewriter(details) if rewriter else details


def leftover(action, details):
    """Whether a rewritten entry still carries a clinical value or a contact."""
    text = details or ""
    if action in (CONSULTATION_UPDATED,) + CORRECTIONS:
        return "→" in text or '"' in text
    if action == DISPENSED:
        return " of " in text or ": " in text
    if action in DOSE_ACTIONS:
        return ": " in text
    if action == APPOINTMENT_SMS:
        return 'message: "' in text or bool(re.search(r"\b0?9\d{9}\b|\+63", text))
    return False


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
    placeholders = ", ".join("?" for _ in REWRITERS)
    rows = conn.execute(
        f"SELECT id, action, details FROM audit_logs WHERE action IN ({placeholders}) "
        "ORDER BY id", list(REWRITERS)).fetchall()
    entries = []
    for row in rows:
        new = rewrite(row["action"], row["details"])
        if new != row["details"]:
            entries.append((row["id"], row["action"], new))
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
    result = {"database": db_path, "backup": None, "entries_rewritten": 0,
              "by_action": {}, "record_written": False, "problems": []}
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

        by_action = {}
        conn.execute("BEGIN")
        for entry_id, action, new in entries:
            conn.execute("UPDATE audit_logs SET details = ? WHERE id = ?", (new, entry_id))
            by_action[action] = by_action.get(action, 0) + 1
        details = (
            "Done by the migration script migrate_admin_minimum_necessary.py, not by "
            f"this account. {len(entries)} earlier "
            f"entr{'y' if len(entries) == 1 else 'ies'} rewritten to name no medicine, "
            f"vaccine, clinical value, contact number or message. {REASON}")
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
            (actor["id"], ACTION, MODULE, details))

        # Checks, before anything is committed.
        problems = result["problems"]
        expected = dict(before_counts, audit_logs=before_counts["audit_logs"] + 1)
        if _counts(conn) != expected:
            problems.append("a table's row count changed")
        after_audit = {r["id"]: tuple(r) for r in conn.execute(
            "SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")}
        if any(after_audit.get(i) != row for i, row in before_audit.items()):
            problems.append("an audit entry's who, when or action changed")
        placeholders = ", ".join("?" for _ in REWRITERS)
        for row in conn.execute(
                f"SELECT action, details FROM audit_logs WHERE action IN ({placeholders})",
                list(REWRITERS)):
            if leftover(row["action"], row["details"]):
                problems.append(f"an entry of '{row['action']}' still carries clinical detail")
                break
        if problems:
            conn.execute("ROLLBACK")
            result["backup_note"] = "Nothing was changed."
            return result
        conn.execute("COMMIT")
        result.update(entries_rewritten=len(entries), by_action=by_action,
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
        print("Nothing to do. It has already run, and no clinical detail is left.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"audit entries rewritten: {result['entries_rewritten']}")
    for action, count in sorted(result["by_action"].items()):
        print(f"  {action}: {count}")
    print("one audit entry written recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Writes to audit_logs -- the record of who changed what, and when.

The table has existed since the first schema pass and held nothing; this is its
first writer. It is deliberately append-only: nothing here updates or deletes a
row, because an audit trail that can be edited answers no question worth asking.

WHAT AN ENTRY HAS TO SAY TO BE WORTH KEEPING
--------------------------------------------
"Consultation updated" is not an audit entry, it is a timestamp with a label. An
entry earns its place only if someone reading it months later -- during a review,
or when two people disagree about what was recorded -- can tell what the record
said before and what it says now without opening anything else. So `details`
carries the field-by-field before and after, spelled out:

    Consultation #12 for Elena Gonzales (PAT-005), recorded 07 Aug 2026.
    Temperature: 37.2 °C → 38.4 °C; Diagnosis: "Viral upper respiratory
    infection" → "Dengue fever, suspected"; Follow-up date: not recorded →
    Aug 15, 2026

The four columns map onto the Audit Logs screen's existing table, so entries
written here are already in the shape that screen reads:

    action       the short activity phrase in its Activity column
    module       the pill beside it, one of MODULE_*
    details      the expansion, as above
    ip_address   where the request came from
"""
from database.connection import get_db
from utils.dates import day_start_utc, today

# The module pills the Audit Logs screen already renders. Named constants rather
# than literals at each call site so a typo cannot split one module into two.
MODULE_CONSULTATIONS = "Consultation Records"
MODULE_PATIENTS = "Patient Records"
MODULE_INVENTORY = "Medicine Inventory"
MODULE_APPOINTMENTS = "Appointment Scheduling"
MODULE_SMS = "SMS Notifications"

# Activity phrases, in the same voice as the ones on that screen ("Updated
# patient record", "Updated stock quantity").
ACTION_CONSULTATION_UPDATED = "Updated consultation record"
# A broadcast is not editable, so unlike the consultation entry above there is no
# before-and-after to describe. What earns its place in `details` instead is the
# message itself, who it reached, and whether it was actually transmitted -- an
# entry that omitted the last of those would read as a send that happened.
ACTION_SMS_BROADCAST_SENT = "Sent community SMS broadcast"


def log_action(user_id, action, module=None, details=None, ip_address=None):
    """Append one entry. Returns its id, or None if it could not be attributed.

    A missing user_id means no entry rather than a fabricated one: user_id is NOT
    NULL and FK-constrained to a real account, and an audit row that cannot say
    who acted is worse than none -- it would read as though the change had no
    author. The caller's own write is not rolled back for it; losing a log line
    must never cost the clinical record it describes.
    """
    if not user_id:
        return None

    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO audit_logs (user_id, action, module, details, ip_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, action, module, details, ip_address),
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    return entry_id


def get_audit_logs(module=None, limit=100):
    """Recent entries, newest first, with the acting user's name resolved."""
    clause = "WHERE a.module = ?" if module else ""
    parameters = ([module] if module else []) + [limit]

    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT a.id, a.action, a.module, a.details, a.ip_address, a.created_at,
               u.full_name AS user_name, u.role AS user_role
        FROM audit_logs a
        JOIN users u ON u.id = a.user_id
        {clause}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_audit_logs(module=None):
    """How many entries exist, for the module filter in force. One query, so the
    "showing N of M" line on the screen cannot disagree with the rows above it."""
    clause = "WHERE module = ?" if module else ""
    parameters = [module] if module else []

    conn = get_db()
    total = conn.execute(
        f"SELECT COUNT(*) FROM audit_logs {clause}", parameters
    ).fetchone()[0]
    conn.close()
    return total


def get_audit_stats():
    """The figures the Audit Logs screen's stat cards report.

    Counted here rather than from the page's own row list: that list is capped by
    `limit`, so totals derived from it would silently start understating once the
    trail outgrew one page.

    WHAT IS DELIBERATELY NOT HERE
    -----------------------------
    The screen was designed with "Login Events" and "Security Events" cards.
    Neither is returned, because neither is written: log_action() is called from
    the consultation edit path and the SMS broadcast path only, and routes/auth.py
    logs nothing at all -- no login, no logout, no failed attempt. A count of
    logins would therefore be a count of zero dressed up as a measurement, which
    is the one thing this project's reporting rule forbids. The template names the
    absence instead. See UNTRACKED in routes/audit_views.py.
    """
    start_of_today = day_start_utc(today())

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    today_count = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE created_at >= ?", (start_of_today,)
    ).fetchone()[0]
    by_module = conn.execute(
        """
        SELECT module, COUNT(*) AS entries
          FROM audit_logs
         WHERE module IS NOT NULL
      GROUP BY module
      ORDER BY entries DESC, module
        """
    ).fetchall()
    # "Record Updates" on the screen means a change to a clinical or stock
    # record, as opposed to a message sent out -- so it is every module except
    # SMS rather than a second list that could drift from MODULE_* above.
    record_updates = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE module IS NOT NULL AND module <> ?",
        (MODULE_SMS,),
    ).fetchone()[0]
    actors = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM audit_logs"
    ).fetchone()[0]
    conn.close()

    return {
        "total": total,
        "today": today_count,
        "record_updates": record_updates,
        "distinct_actors": actors,
        "by_module": [dict(row) for row in by_module],
    }


def describe_changes(before, after, labels, formatters=None):
    """Turn two versions of a record into the readable half of an audit entry.

    Returns (summary, field_names): the "Label: old → new; ..." text, and the
    plain list of fields that moved. An empty field list means nothing changed,
    which is the caller's signal not to write an entry at all -- a save that
    altered nothing is not an event.

    Only keys present in `labels` are compared, and they are reported in that
    dict's order rather than the dict-of-values order, so two edits to the same
    record always list their fields the same way round.

    `formatters` maps a field to a callable rendering its value for a person: a
    temperature gains its unit, a date is spelled out. Anything without one is
    shown as stored, quoted if it is text, so a trailing space or a changed case
    is visible rather than looking like no change at all.
    """
    formatters = formatters or {}
    parts, changed = [], []

    for field, label in labels.items():
        old_value = before.get(field)
        new_value = after.get(field)
        if _same(old_value, new_value):
            continue
        changed.append(field)
        render = formatters.get(field, _default_render)
        parts.append(f"{label}: {render(old_value)} → {render(new_value)}")

    return "; ".join(parts), changed


def _same(old_value, new_value):
    """Whether two stored values are the same as far as an audit trail cares.

    None and "" are the same absence -- a field cleared to empty text and one
    never filled in both mean "not recorded", and reporting a move between them
    as a change would fill the log with edits nobody made. Numbers are compared
    numerically so 37 and 37.0 do not read as an edit.
    """
    if old_value is None or old_value == "":
        old_value = None
    if new_value is None or new_value == "":
        new_value = None
    if old_value is None or new_value is None:
        return old_value is new_value

    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
        return float(old_value) == float(new_value)
    return str(old_value) == str(new_value)


def _default_render(value):
    if value is None or value == "":
        return "not recorded"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'

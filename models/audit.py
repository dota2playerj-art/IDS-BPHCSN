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
# The two immunisation tables, under one pill. Both halves of the Patient
# Profile's Immunization Record tab write here: the DOH EPI doses and the
# vaccinations given outside that schedule. One module rather than two because
# the question this pill answers is "which screen was touched", and those two
# lists are one screen -- the trail keeps them apart where it matters, in the
# activity phrase, which names which kind of record moved.
MODULE_IMMUNIZATIONS = "Immunization Records"
MODULE_SMS = "SMS Notifications"
# Sign-ins and refused sign-ins. Its own module rather than folded into one of
# the record modules above, because it answers a different question: those say
# what the record used to say and what it says now, this one says who was let in
# and who was turned away. Keeping it separate is also what lets the Audit Logs
# module filter show the authentication trail on its own.
MODULE_AUTH = "Authentication"

# Activity phrases, in the same voice as the ones on that screen ("Updated
# patient record", "Updated stock quantity").
ACTION_CONSULTATION_UPDATED = "Updated consultation record"
# The two correction phrases, written from routes/vaccination_correction_views.py
# when a recorded vaccination's own field values are put right.
#
# "Corrected", not "Updated", and the difference is the whole point of the path
# that writes these. Every other record in this system is edited through the form
# that created it; a vaccination is not, because both entry forms are deliberately
# add-only -- see routes/consultation_views.py _apply_immunization_edit(). A
# correction is therefore a rarer and more deliberate act than an edit, reached
# from a different screen behind its own confirmation, and the trail says so in
# the one word an administrator scanning it will actually read.
#
# THEY ARE TWO PHRASES RATHER THAN ONE FOR THE REASON ACTION_LOGIN_BLOCKED IS
# SEPARATE FROM ACTION_LOGIN_FAILED. Both sentences are about a vaccination
# record, and collapsing them would lose the distinction that decides what a
# reader does next. An EPI dose is graded against the national schedule: moving
# its date moves whether a child reads as Due Now or Overdue on every screen that
# counts them. A vaccination outside that schedule is graded against nothing, so
# correcting one changes a history and no status anywhere. An administrator
# asking "did a correction change who is showing as a defaulter?" needs those two
# to look different in a list, not to be filtered apart by reading each entry.
ACTION_IMMUNIZATION_CORRECTED = "Corrected EPI immunisation record"
ACTION_GENERAL_VACCINATION_CORRECTED = "Corrected other vaccination record"
# A broadcast is not editable, so unlike the consultation entry above there is no
# before-and-after to describe. What earns its place in `details` instead is the
# message itself, who it reached, and whether it was actually transmitted -- an
# entry that omitted the last of those would read as a send that happened.
ACTION_SMS_BROADCAST_SENT = "Sent community SMS broadcast"
# The two authentication outcomes, written from routes/auth.py's login route.
# Both phrases are stable strings because the counts below select on them: a
# reworded action would silently stop being counted, so they are constants for
# the same reason the module names are.
ACTION_LOGIN_SUCCESS = "Signed in"
ACTION_LOGIN_FAILED = "Refused sign-in attempt"
# A third outcome, and its own phrase rather than a variant of the one above.
# "The password did not match" and "the account has been deactivated" are refusals
# with nothing else in common: the first is a typo or a guess, the second is a
# revoked credential still being presented -- often, and this is the whole point,
# with the CORRECT password. Collapsing them into one phrase would bury the only
# entry on this screen that tells an administrator a credential they thought they
# had withdrawn is still in someone's hands and still being used.
ACTION_LOGIN_BLOCKED = "Blocked sign-in to deactivated account"
# A fourth phrase, and the first one that is not about the login form at all.
# The three above are written when somebody presents credentials. This one is
# written when a session that was already open is ended underneath its holder,
# because the account it belongs to has been deactivated since it started --
# utils/security.py checks the flag on every guarded request, so a revocation
# takes effect at the next click rather than at the next sign-in.
#
# IT IS ITS OWN PHRASE FOR THE SAME REASON ACTION_LOGIN_BLOCKED IS.
# Folding it into that one would be the more tempting shortcut, because both
# sentences are about a deactivated account -- and it would make the trail lie in
# a way nobody would catch by reading it. "Blocked sign-in" says a credential was
# presented at the form and refused. Here nothing was presented: somebody was
# already inside, and the door was closed behind them. An administrator chasing
# "who is still trying to use the account I switched off" would read the second
# as the first and conclude the credential is still in circulation.
ACTION_SESSION_REVOKED = "Ended session on deactivated account"

# Every action that means somebody was turned away at the login form. Grouped so
# the Security Events figure counts refusals rather than one particular kind of
# refusal -- adding a fourth outcome later must not silently shrink that number.
#
# ACTION_SESSION_REVOKED IS DELIBERATELY NOT IN THIS GROUP, AND THAT IS A CLAIM
# ABOUT TWO SCREENS RATHER THAN A PREFERENCE.
# The comment above says "at the login form", and both screens reading this
# figure say the same in their own words: Audit Logs' Security Events card is
# titled "Sign-ins refused against an account that exists", and Settings labels
# the number "Refused sign-in attempts". A revoked session is not a sign-in
# attempt. Adding it here would leave two visible labels describing a total that
# no longer matches them -- which is the precise failure utils/unavailable.py's
# docstring calls the hardest kind, a figure that is mostly right.
#
# The entry is not hidden by that. It is written under MODULE_AUTH like the other
# three, so it appears in the trail and under the screen's Authentication filter;
# it is only kept out of a total whose name would stop being true. If a future
# session wants these counted, the honest change is a card of their own, not a
# quiet addition to this tuple.
REFUSAL_ACTIONS = (ACTION_LOGIN_FAILED, ACTION_LOGIN_BLOCKED)

# Modules that are not a change to a stored record, and so are excluded from the
# "Record Updates" figure on the Audit Logs screen. A broadcast is a message that
# went out; a sign-in is an access event. Neither edits a clinical or stock row,
# and counting them as record updates would inflate the one figure on that screen
# that is supposed to answer "how much of the data has been altered".
NON_RECORD_MODULES = (MODULE_SMS, MODULE_AUTH)


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
    """Recent entries, newest first, with the acting user's name resolved.

    `limit=None` returns every matching entry rather than a page of them. The
    screen always passes a page size, because a table nobody can scroll past is
    not more useful for being longer. The export passes None: a downloaded audit
    trail that silently stopped at the hundredth entry would be the worst place in
    this system for a quiet omission, since the whole point of the file is that it
    is the complete record of who changed what.
    """
    clause = "WHERE a.module = ?" if module else ""
    parameters = [module] if module else []
    cap = ""
    if limit is not None:
        cap = "LIMIT ?"
        parameters = parameters + [limit]

    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT a.id, a.action, a.module, a.details, a.ip_address, a.created_at,
               u.full_name AS user_name, u.role AS user_role
        FROM audit_logs a
        JOIN users u ON u.id = a.user_id
        {clause}
        ORDER BY a.created_at DESC, a.id DESC
        {cap}
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

    THE TWO LOGIN FIGURES USED TO BE ABSENT, AND NOW ARE NOT
    --------------------------------------------------------
    This docstring used to say the screen's "Login Events" and "Security Events"
    cards returned nothing, because nothing was written: routes/auth.py started a
    session and logged neither the sign-in, nor the sign-out, nor the refusal. A
    count of logins would have been a count of zero dressed up as a measurement,
    which is the one thing this project's reporting rule forbids, so the template
    named the absence instead.

    That gap is closed. The login route now writes one entry per successful
    sign-in and one per sign-in refused against an account that exists, so
    `logins` and `refused_logins` below are counts of real rows and both cards
    report them.

    A refusal comes in two kinds and they are counted separately as well as
    together. `failed_logins` is a credential that did not match on an account
    that is allowed to sign in; `blocked_logins` is an account that has been
    deactivated, refused whether or not the password was right. The Security
    Events card adds them, because the question it answers is "is somebody being
    turned away"; the trail keeps them distinct, because the question an
    administrator asks next is "why", and the two answers lead to opposite
    investigations.

    Two things are still genuinely absent, and are counted nowhere because
    nothing writes them:

    * An attempt against a username that does not exist. user_id is NOT NULL and
      foreign-keyed to a real account, so there is no row such an attempt could be
      attributed to -- see log_action() above. What `failed_logins` counts is
      every refusal aimed at an account that exists, which is the only kind that
      could ever have succeeded.
    * Signing out. routes/auth.py clears the session and writes nothing, so these
      are sign-in counts and not session counts.

    Both are stated on the screen beside the figures rather than left to be
    inferred. See UNTRACKED in routes/audit_views.py.
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
    # record, as opposed to a message sent out or an access event -- so it is
    # every module except the ones NON_RECORD_MODULES names, rather than a second
    # list that could drift from MODULE_* above. This was "except SMS" until
    # authentication started writing; leaving it that way would have quietly
    # counted every sign-in as an edit to somebody's record.
    exclusions = ", ".join("?" for _ in NON_RECORD_MODULES)
    record_updates = conn.execute(
        f"""
        SELECT COUNT(*) FROM audit_logs
         WHERE module IS NOT NULL AND module NOT IN ({exclusions})
        """,
        NON_RECORD_MODULES,
    ).fetchone()[0]
    actors = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM audit_logs"
    ).fetchone()[0]

    # The two authentication figures, each selected on its own action so a
    # successful sign-in can never be counted as a refused one or the reverse.
    def _auth_count(action, since=None):
        clause = " AND created_at >= ?" if since else ""
        parameters = [MODULE_AUTH, action] + ([since] if since else [])
        return conn.execute(
            f"SELECT COUNT(*) FROM audit_logs WHERE module = ? AND action = ?{clause}",
            parameters,
        ).fetchone()[0]

    logins = _auth_count(ACTION_LOGIN_SUCCESS)
    logins_today = _auth_count(ACTION_LOGIN_SUCCESS, start_of_today)
    failed_logins = _auth_count(ACTION_LOGIN_FAILED)
    failed_logins_today = _auth_count(ACTION_LOGIN_FAILED, start_of_today)
    blocked_logins = _auth_count(ACTION_LOGIN_BLOCKED)
    blocked_logins_today = _auth_count(ACTION_LOGIN_BLOCKED, start_of_today)
    refused_logins = sum(_auth_count(a) for a in REFUSAL_ACTIONS)
    refused_logins_today = sum(_auth_count(a, start_of_today) for a in REFUSAL_ACTIONS)
    # How many distinct accounts have ever signed in -- not how many exist. An
    # account that has never signed in is absent from audit_logs entirely, which
    # is exactly what makes this figure worth reporting beside the total.
    login_accounts = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM audit_logs WHERE module = ? AND action = ?",
        (MODULE_AUTH, ACTION_LOGIN_SUCCESS),
    ).fetchone()[0]
    conn.close()

    return {
        "total": total,
        "today": today_count,
        "record_updates": record_updates,
        "distinct_actors": actors,
        "by_module": [dict(row) for row in by_module],
        "logins": logins,
        "logins_today": logins_today,
        "failed_logins": failed_logins,
        "failed_logins_today": failed_logins_today,
        "blocked_logins": blocked_logins,
        "blocked_logins_today": blocked_logins_today,
        # What the Security Events card reports: every refusal, whatever its
        # reason. Summed over REFUSAL_ACTIONS rather than adding the two named
        # figures above, so a third refusal outcome added later is counted here
        # the moment it joins that tuple -- the alternative is a total that
        # quietly stops being one and a card that under-reports without failing.
        "refused_logins": refused_logins,
        "refused_logins_today": refused_logins_today,
        "login_accounts": login_accounts,
    }


def get_last_logins():
    """{user_id: the stored timestamp of that account's most recent sign-in}.

    One grouped query rather than one per account, so User Management's roster
    costs the same whether it lists three accounts or thirty.

    Only ACTION_LOGIN_SUCCESS is considered. A refused attempt is not a login,
    and letting one set a "last login" would be the worst possible reading of the
    column -- an account that has never once been signed into would show a time
    beside it because somebody guessed at its password. That holds for the
    deactivated case too, and matters more there: a blocked attempt can carry the
    correct password, so counting it would put a fresh "last login" against
    precisely the account whose access was supposed to have ended.

    An account missing from the result has never signed in. That absence is the
    answer, and the caller reports it as such rather than substituting a date.
    MAX() over the stored text is a correct maximum because created_at is written
    by CURRENT_TIMESTAMP in a fixed-width, zero-padded UTC format, so it sorts
    lexicographically in the same order it sorts chronologically.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT user_id, MAX(created_at) AS last_login
          FROM audit_logs
         WHERE module = ? AND action = ?
      GROUP BY user_id
        """,
        (MODULE_AUTH, ACTION_LOGIN_SUCCESS),
    ).fetchall()
    conn.close()
    return {row["user_id"]: row["last_login"] for row in rows}


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

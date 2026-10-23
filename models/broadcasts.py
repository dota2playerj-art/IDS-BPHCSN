"""Community SMS broadcasts: who a message reaches, and what was actually sent.

Screen 09's community-facing half. A broadcast is one message composed once and
delivered to every contact in a chosen audience, which makes it a different thing
from the per-patient reminders the rest of the system deals in: it belongs to no
patient record, and its history is a record of what the barangay said to the
community rather than of anyone's care.
"""
import re

from database.connection import db_connection
from models.consultations import PEDIATRIC_AGE_YEARS
from models.patients import SENIOR_AGE, calculate_age
from utils.roles import is_care_team
from utils.dates import (
    day_start_utc,
    display_timestamp,
    month_bounds,
    range_bounds_utc,
    resolve_range,
    today,
)
from utils.phone import (
    is_valid_ph_mobile, mask_phone, normalize_phone_number, to_local_ph_mobile,
)
from utils.sms import (
    LIVE,
    SIMULATED,
    deliver_announcement_sms,
    gateway_configured,
    message_metrics,
)

# The message categories the screen offers. One tuple, rendered into the compose
# dialog's dropdown and the history filter alike, and checked on submit -- the
# same arrangement every other constrained field in this project uses.
BROADCAST_CATEGORIES = (
    "Barangay Health Advisory",
    "Vaccination Reminder",
    "Prenatal Reminder",
    "Senior Citizen Consultation",
    "Medicine Availability",
    "General Reminder",
)

# Audiences that cannot be built from anything the schema holds. Kept as data
# rather than as a comment so the screen can say why they are absent instead of
# silently offering four options where the specification lists six.
AUDIENCE_NOT_AVAILABLE = (
    {
        "label": "Entire Barangay / All Residents",
        "reason": (
            "The system holds registered patients only, not every resident. "
            "Reaching every resident needs a barangay contact list this project does not have."
        ),
    },
    {
        "label": "Pregnant Women",
        "reason": (
            "Pregnancy is not recorded, so the Prenatal Patients figure reads 0. This audience "
            "needs a prenatal flag first."
        ),
    },
)

# Every audience, and the real query behind it. `source` is shown on the compose
# dialog so whoever is sending can see exactly whose numbers they are about to
# use -- a broadcast is irreversible, and "Senior Citizens" is not self-evidently
# "patients aged 60 and over with a mobile number on file".
AUDIENCES = {
    "all_patients": {
        "label": "All Registered Patients",
        "source": "Active patient records with a valid mobile number on file.",
    },
    "seniors": {
        "label": "Senior Citizens",
        "source": (
            f"Active patients aged {SENIOR_AGE} and over (Republic Act 9994) with "
            "a valid mobile number."
        ),
    },
    "child_guardians": {
        "label": "Parents / Guardians of Children Under " + str(PEDIATRIC_AGE_YEARS),
        "source": (
            f"The contact number recorded on the record of each active patient "
            f"under {PEDIATRIC_AGE_YEARS} — that number belongs to the child's "
            "parent or guardian, not the child."
        ),
    },
    "personnel": {
        "label": "Health Center Personnel",
        "source": "Active user accounts with a mobile number in their profile.",
    },
}

AUDIENCE_ORDER = ("all_patients", "seniors", "child_guardians", "personnel")

# Broadcast-level outcome. Derived from the recipient rows, never set by hand.
STATUS_SENT = "Sent"
STATUS_PARTIAL = "Partial"
STATUS_FAILED = "Failed"

STATUS_BADGE_CLASS = {
    STATUS_SENT: "badge-sent",
    STATUS_PARTIAL: "badge-queued",
    STATUS_FAILED: "badge-failed",
}

# How much of the message the history table shows before it is cut short.
PREVIEW_CHARACTERS = 70


# ---------------------------------------------------------------------------
# RECIPIENTS
# ---------------------------------------------------------------------------

def _patient_contacts(min_age=None, max_age=None):
    """Active patients with a usable mobile, optionally narrowed by age.

    Deceased and Inactive records are excluded in the SQL, not filtered later.
    Texting a health advisory to a number on a deceased patient's record is the
    single worst thing this feature could do, so that exclusion is part of the
    query every audience runs rather than something each one remembers.

    `max_age` is exclusive: max_age=5 is "under five", matching how
    PEDIATRIC_AGE_YEARS is read everywhere else in the project.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT id, first_name, middle_name, last_name, birth_date, contact_number
        FROM patients
        WHERE status = 'Active'
          AND contact_number IS NOT NULL
          AND TRIM(contact_number) != ''
        ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
        """
        ).fetchall()

    contacts = []
    for row in rows:
        if not is_valid_ph_mobile(row["contact_number"]):
            continue
        if min_age is not None or max_age is not None:
            age = calculate_age(row["birth_date"])
            if age is None:
                continue
            if min_age is not None and age < min_age:
                continue
            if max_age is not None and age >= max_age:
                continue

        name = " ".join(
            part for part in (row["first_name"], row["middle_name"], row["last_name"])
            if part
        )
        contacts.append({
            "patient_id": row["id"],
            "user_id": None,
            "name": name,
            "mobile": to_local_ph_mobile(row["contact_number"]),
        })
    return contacts


def _personnel_contacts():
    """Active user accounts carrying a usable mobile number.

    users.phone is empty on every seeded account today, so this audience
    currently resolves to nobody and the compose dialog says so. That is the
    honest reading of the column rather than a reason to invent numbers for it.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT id, full_name, role, phone
        FROM users
        WHERE is_active = 1 AND phone IS NOT NULL AND TRIM(phone) != ''
        ORDER BY full_name COLLATE NOCASE
        """
        ).fetchall()

    return [
        {
            "patient_id": None,
            "user_id": row["id"],
            "name": row["full_name"],
            "mobile": to_local_ph_mobile(row["phone"]),
        }
        for row in rows
        if is_valid_ph_mobile(row["phone"])
    ]


def _deduplicate(contacts):
    """One message per number, however many records carry it.

    Two children of the same parent hold the same guardian number, so the
    "Parents / Guardians" audience would otherwise text that parent twice for one
    advisory -- and bill twice for it. Matched on the normalised 639XXXXXXXXX
    form, so 0917... and +63917... are recognised as the one number they are.

    Returns (recipients, merged_count); the count is reported to the operator
    rather than quietly absorbed, because it explains why an audience of 8
    records sends 6 messages.
    """
    seen = {}
    unique = []
    merged = 0
    for contact in contacts:
        key = normalize_phone_number(contact["mobile"])
        if key in seen:
            merged += 1
            continue
        seen[key] = True
        unique.append(contact)
    return unique, merged


def resolve_recipients(audience):
    """Everyone an audience reaches right now, one entry per distinct number.

    Resolved at send time rather than stored: a broadcast goes to whoever is on
    the roster the moment it is sent, and the count recorded against it is the
    count that was actually messaged.
    """
    if audience == "all_patients":
        contacts = _patient_contacts()
    elif audience == "seniors":
        contacts = _patient_contacts(min_age=SENIOR_AGE)
    elif audience == "child_guardians":
        contacts = _patient_contacts(max_age=PEDIATRIC_AGE_YEARS)
    elif audience == "personnel":
        contacts = _personnel_contacts()
    else:
        return [], 0

    return _deduplicate(contacts)


def audience_options():
    """Every audience with its live recipient count, in AUDIENCE_ORDER.

    The counts are read from the same resolve_recipients() the send uses, so the
    number on the radio button is the number of messages that will go out.
    """
    options = []
    for key in AUDIENCE_ORDER:
        recipients, merged = resolve_recipients(key)
        options.append({
            "key": key,
            "label": AUDIENCES[key]["label"],
            "source": AUDIENCES[key]["source"],
            "count": len(recipients),
            "merged": merged,
        })
    return options


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_broadcast_form(values, recipients=None):
    """Server-side checks on a compose submit. Returns {field: message}.

    Runs independently of the browser: the character counter in the dialog is a
    convenience, and a POST can arrive without it ever having run.
    """
    errors = {}

    message = (values.get("message") or "").strip()
    if not message:
        errors["message"] = "Enter the message to broadcast."
    else:
        metrics = message_metrics(message)
        if metrics["over_maximum"]:
            errors["message"] = (
                f"The message is {metrics['length']} characters; the gateway "
                f"accepts at most {metrics['max_characters']}."
            )

    audience = (values.get("audience") or "").strip()
    if not audience:
        errors["audience"] = "Choose who this broadcast goes to."
    elif audience not in AUDIENCES:
        errors["audience"] = "Choose an audience from the list."
    elif recipients is not None and not recipients:
        # Not a field-format problem: the audience is real, it is simply empty
        # today. Said plainly so the operator knows the send did not silently
        # go nowhere.
        errors["audience"] = (
            f"{AUDIENCES[audience]['label']} currently has no contact with a "
            "valid mobile number on file, so there is nobody to send to."
        )

    category = (values.get("category") or "").strip()
    if category and category not in BROADCAST_CATEGORIES:
        errors["category"] = "Choose a category from the list."

    return errors


# ---------------------------------------------------------------------------
# SENDING AND HISTORY
# ---------------------------------------------------------------------------

def generate_next_reference(conn=None):
    """Next free SMS-YYYY-NNNN reference for the current clinic year.

    Reads the highest number already issued this year rather than counting rows,
    so a deleted broadcast cannot cause a UNIQUE collision -- the same reasoning
    as generate_next_patient_id().
    """
    if conn is None:
        with db_connection() as own:
            return generate_next_reference(own)
    year = today().year
    rows = conn.execute(
        "SELECT reference FROM sms_broadcasts WHERE reference LIKE ?",
        (f"SMS-{year}-%",),
    ).fetchall()

    highest = 0
    for row in rows:
        suffix = str(row["reference"]).rsplit("-", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"SMS-{year}-{highest + 1:04d}"


class BroadcastNotSent(Exception):
    """A send that was refused before any message left (audit B20).

    `reason` is ALREADY_SENT (this compose form's reference is already on a broadcast:
    a second press, a resubmitted page, or two requests at once) or REFERENCE_TAKEN
    (another broadcast took the next reference while this one was being written).
    `existing` is the broadcast that holds the reference, for ALREADY_SENT.
    """

    def __init__(self, reason, existing=None):
        super().__init__(reason)
        self.reason = reason
        self.existing = existing


ALREADY_SENT = "already-sent"
REFERENCE_TAKEN = "reference-taken"
# The compose form carries the reference its broadcast will be stored under. It is the
# form's one-time token: the server claims it before anything is sent, so one form sends
# once (audit B20).
SEND_REFERENCE_FIELD = "send_reference"
SEND_REFERENCE_PATTERN = re.compile(r"SMS-[0-9]{4}-[0-9]{4,6}")


def _claim_reference(conn, reference, row):
    """Insert the broadcast row under `reference` inside one write transaction.

    BEGIN IMMEDIATE takes SQLite's write lock first, so two requests cannot both find
    the reference free. Returns the new row id, or raises BroadcastNotSent. A `reference`
    of None claims the next free one (callers with no compose form).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        if reference is not None:
            held = conn.execute("SELECT id FROM sms_broadcasts WHERE reference = ?",
                                (reference,)).fetchone()
            if held:
                raise BroadcastNotSent(ALREADY_SENT, held["id"])
            if reference != generate_next_reference(conn):
                raise BroadcastNotSent(REFERENCE_TAKEN)
        else:
            reference = generate_next_reference(conn)
        cursor = conn.execute(
            """
        INSERT INTO sms_broadcasts
            (reference, message, category, audience, audience_label,
             recipient_count, sent_count, failed_count, segments, encoding,
             status, delivery_mode, sent_by)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
        """,
            (reference, *row),
        )
        conn.commit()
        return cursor.lastrowid
    except BaseException:
        conn.rollback()
        raise


def send_broadcast(message, audience, category, sent_by, reference=None):
    """Deliver one broadcast to its audience and record what happened.

    Every recipient is attempted individually, because that is what the gateway's
    API takes -- one number per request -- and each attempt's own outcome is
    stored. The broadcast's sent/failed counts are then sums of real per-recipient
    results rather than an assumption that all or none succeeded.

    delivery_mode is whatever utils.sms.deliver_announcement_sms() actually did:
    'live' when SEMAPHORE_API_KEY is configured, 'simulated' when it is not. It
    is recorded per broadcast, not per system, so a history spanning the day the
    key was added stays truthful about which messages really went out.

    Returns the stored broadcast as a dict.

    Known limitation, deliberately not hidden: a live send of N recipients is N
    sequential HTTP calls inside the request. That is fine at barangay scale and
    for the simulated path, but a roster in the thousands would want a queue.
    """
    recipients, merged = resolve_recipients(audience)
    metrics = message_metrics(message)

    # Claimed BEFORE anything is sent (audit B20): a second press of Send, a resubmitted
    # page or two requests at once find the reference taken and send nothing. The row is
    # written as Failed with no counts and completed below, so a send that stops halfway
    # still leaves a record of having started.
    with db_connection() as conn:
        broadcast_id = _claim_reference(conn, reference, (
            message, category or None, audience, AUDIENCES[audience]["label"],
            len(recipients), metrics["segments"], metrics["encoding"], STATUS_FAILED,
            LIVE if gateway_configured() else SIMULATED, sent_by))

    results = []
    for recipient in recipients:
        outcome = deliver_announcement_sms(message, recipient["mobile"])
        results.append((recipient, outcome))

    sent_count = sum(1 for _, outcome in results if outcome["status"] == "sent")
    failed_count = len(results) - sent_count
    # Read back from the attempts rather than assumed, so the recorded mode is
    # what actually happened. With no recipients there is nothing to read, so ask
    # the gateway directly -- validate_broadcast_form() refuses that case, which
    # makes this a floor rather than a path the screen can reach.
    modes = {outcome["mode"] for _, outcome in results}
    if modes:
        delivery_mode = LIVE if LIVE in modes else SIMULATED
    else:
        delivery_mode = LIVE if gateway_configured() else SIMULATED

    if failed_count == 0:
        status = STATUS_SENT
    elif sent_count == 0:
        status = STATUS_FAILED
    else:
        status = STATUS_PARTIAL

    with db_connection() as conn:
        conn.execute(
            "UPDATE sms_broadcasts SET sent_count = ?, failed_count = ?, status = ?, "
            "delivery_mode = ? WHERE id = ?",
            (sent_count, failed_count, status, delivery_mode, broadcast_id),
        )

        for recipient, outcome in results:
            conn.execute(
                """
            INSERT INTO sms_broadcast_recipients
                (broadcast_id, patient_id, user_id, recipient_name, mobile_number,
                 status, gateway_response)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    broadcast_id, recipient["patient_id"], recipient["user_id"],
                    recipient["name"], recipient["mobile"],
                    "Sent" if outcome["status"] == "sent" else "Failed",
                    outcome.get("response") or outcome.get("error"),
                ),
            )

        conn.commit()

    broadcast = get_broadcast_by_id(broadcast_id)
    broadcast["merged_duplicates"] = merged
    return broadcast


def _to_broadcast(row):
    """Copy a stored row into a dict and add what the screen renders."""
    broadcast = dict(row)
    message = broadcast.get("message") or ""
    broadcast["preview"] = (
        message if len(message) <= PREVIEW_CHARACTERS
        else message[:PREVIEW_CHARACTERS].rstrip() + "…"
    )
    broadcast["status_badge_class"] = STATUS_BADGE_CLASS.get(
        broadcast.get("status"), "badge-queued"
    )
    broadcast["is_simulated"] = broadcast.get("delivery_mode") == SIMULATED
    # sent_at is stored as UTC by CURRENT_TIMESTAMP; the screen shows clinic time.
    broadcast["sent_at_display"] = display_timestamp(broadcast.get("sent_at"))
    return broadcast


_HISTORY_SELECT = """
    SELECT b.*, u.full_name AS sent_by_name, u.role AS sent_by_role
    FROM sms_broadcasts b
    JOIN users u ON u.id = b.sent_by
"""


def get_broadcast_history(limit=50):
    """Past broadcasts, newest first, with the sender's name resolved."""
    with db_connection() as conn:
        rows = conn.execute(
            _HISTORY_SELECT + " ORDER BY b.sent_at DESC, b.id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_to_broadcast(row) for row in rows]


def get_broadcast_by_id(broadcast_id):
    with db_connection() as conn:
        row = conn.execute(
            _HISTORY_SELECT + " WHERE b.id = ?", (broadcast_id,)
        ).fetchone()
    return _to_broadcast(row) if row else None


def get_broadcast_recipients(broadcast_id, viewer_role, limit=None):
    """Who one broadcast went to, and whether each message was accepted.

    Names are for the care team only (the Doctor and Health Center Staff). The
    Administrator and the Barangay Official get an empty list for every audience,
    and read get_broadcast_recipient_counts() instead (final fixes, M37).
    The number is MASKED for every role (Task 5d, D3): the last four digits only.
    The full number stays in the table and in send_broadcast(), which is what
    dials it. The gateway's own reply is not returned.
    """
    if not is_care_team(viewer_role):
        return []
    columns = ("id, broadcast_id, patient_id, user_id, recipient_name, "
               "mobile_number, status, created_at")
    with db_connection() as conn:
        rows = conn.execute(
            f"""
        SELECT {columns} FROM sms_broadcast_recipients
        WHERE broadcast_id = ?
        ORDER BY recipient_name COLLATE NOCASE, id
        """
            + (" LIMIT ?" if limit else ""),
            (broadcast_id, limit) if limit else (broadcast_id,),
        ).fetchall()
    recipients = []
    for row in rows:
        recipient = dict(row)
        recipient["mobile_number"] = mask_phone(recipient["mobile_number"])
        recipients.append(recipient)
    return recipients


def get_broadcast_recipient_counts(broadcast_id):
    """How many recipients one broadcast had: total, sent and failed. No names."""
    with db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(status = 'Sent'), 0) AS sent, "
            "COALESCE(SUM(status = 'Failed'), 0) AS failed "
            "FROM sms_broadcast_recipients WHERE broadcast_id = ?", (broadcast_id,)
        ).fetchone()
    return {"total": row["total"], "sent": row["sent"], "failed": row["failed"]}


def get_broadcast_stats(history=None, start=None, end=None, months=6):
    """The four figures above the history table.

    Every one of them is counted from stored rows or from the live roster. There
    is no delivery rate here, for the reason the module header gives: nothing in
    this system is ever told that a message arrived.

    `start`/`end` add a `window` block counting the same things over a requested
    range. `reachable_contacts` is deliberately not ranged and stays out of it:
    it counts who could be texted *now*, from the current roster, which is a fact
    about today rather than something that happened during a period. A report
    claiming "10 contacts reachable in March" would be asserting the March
    roster, which this system does not keep a history of.
    """
    if history is None:
        history = get_broadcast_history(limit=1000)

    month_start, next_month_start = month_bounds()
    start_text, end_text = day_start_utc(month_start), day_start_utc(next_month_start)

    this_month = sum(
        1 for broadcast in history
        if start_text <= str(broadcast["sent_at"]) < end_text
    )
    reachable, _ = resolve_recipients("all_patients")

    window = resolve_range(start=start, end=end, months=months)
    lo, hi = range_bounds_utc(window)
    scoped = [b for b in history if lo <= str(b["sent_at"]) < hi]

    return {
        "total_broadcasts": len(history),
        "this_month": this_month,
        "messages_sent": sum(broadcast["sent_count"] for broadcast in history),
        "messages_failed": sum(broadcast["failed_count"] for broadcast in history),
        "simulated_broadcasts": sum(
            1 for broadcast in history if broadcast["delivery_mode"] == SIMULATED
        ),
        "live_broadcasts": sum(
            1 for broadcast in history if broadcast["delivery_mode"] == LIVE
        ),
        "reachable_contacts": len(reachable),
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "broadcasts": len(scoped),
            "messages_sent": sum(b["sent_count"] for b in scoped),
            "messages_failed": sum(b["failed_count"] for b in scoped),
            "simulated": sum(1 for b in scoped if b["delivery_mode"] == SIMULATED),
        },
    }

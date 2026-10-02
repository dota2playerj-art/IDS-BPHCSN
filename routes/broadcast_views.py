"""Shared context and submit handling for Screen 09's SMS broadcasts.

Screen 09 is rendered by three blueprints -- Administrator, Barangay Official and
Health Center Staff -- from one template with one set of data. The queries live
here so the three role variants cannot drift apart; each route stays thin and
keeps its own role_required guard.
"""
from flask import session

from models.appointment_sms import (
    get_appointment_sms_history,
    get_appointment_sms_stats,
)
from models.audit import ACTION_SMS_BROADCAST_SENT, MODULE_SMS, log_action
from models.broadcasts import (
    AUDIENCE_NOT_AVAILABLE,
    AUDIENCES,
    BROADCAST_CATEGORIES,
    audience_options,
    get_broadcast_history,
    get_broadcast_recipient_counts,
    get_broadcast_recipients,
    get_broadcast_stats,
    resolve_recipients,
    send_broadcast,
    validate_broadcast_form,
)
from utils.roles import is_care_team, normalize_role
from utils.security import get_current_user
from utils.sms import (
    GSM_BASIC_CHARACTERS,
    GSM_EXTENDED_CHARACTERS,
    MAX_MESSAGE_CHARACTERS,
    SIMULATED,
    SINGLE_SEGMENT_GSM,
    SINGLE_SEGMENT_UNICODE,
    CONCATENATED_SEGMENT_GSM,
    CONCATENATED_SEGMENT_UNICODE,
    gateway_configured,
    sms_mode,
    message_metrics,
)

# The fields the compose dialog posts back, and the keys the template reads to
# repopulate itself. One tuple so a field cannot be collected without being
# redisplayed after a failed submit.
COMPOSE_FIELDS = ("message", "audience", "category")

# How many recipients the detail panel names before it stops listing them.
DETAIL_RECIPIENT_LIMIT = 8

# Who may see the individual appointment confirmations panel, and how many rows
# it shows.
#
# THE BARANGAY OFFICIAL IS DELIBERATELY NOT ON THIS LIST, AND IT IS NOT THE
# BROADCAST RULE BEING RESTATED.
# That rule is about *sending*: Administrator and Barangay Official send
# community broadcasts, Health Center Staff does not. This is the opposite way
# round and about *reading*. Every row in the individual history names one
# patient, the service they are booked for and the date they are expected --
# which is a clinical record in miniature, and 09_UI_Architecture §2 keeps the
# Barangay Official out of Patient Records entirely. Putting that same material
# on a screen they do reach would route around the restriction rather than
# honour it. They keep the whole broadcast half of this screen, which names
# nobody.
# The Doctor reads it exactly as Health Center Staff do: same screen, same rows.
# The care team only (Task 5c). Each row names one patient, their mobile number
# and what was texted about their visit; the Administrator does not see those.
APPOINTMENT_SMS_ROLES = {"doctor", "health staff"}
APPOINTMENT_SMS_LIMIT = 25


def _gateway_context():
    """Whether this process could actually transmit, and what to say about it.

    Read fresh on every render rather than cached at import: the whole activation
    story in utils/sms.py is that setting SEMAPHORE_API_KEY and restarting is the
    only step, and a value frozen at import would make a restart necessary twice.
    """
    live = gateway_configured()
    return {
        "gateway_live": live,
        "gateway_label": sms_mode(),
        "gateway_note": (
            "" if live else
            "Set SEMAPHORE_API_KEY on the server and restart the system to send for real."
        ),
    }


def _appointment_sms_context():
    """The individual-confirmation panel's rows, or the absence of the panel.

    The role is read the same way utils.context.inject_role_context() reads it --
    the signed-in account first, the session's own label as the fallback -- so
    one screen cannot decide a viewer is staff while the sidebar beside it
    decides they are not.
    """
    user = get_current_user()
    if user:
        role = normalize_role(user["role"])
    else:
        role = normalize_role(session.get("role"))

    if role not in APPOINTMENT_SMS_ROLES:
        return {
            "can_see_appointment_sms": False,
            "appointment_sms": [],
            "appointment_sms_stats": None,
        }

    history = get_appointment_sms_history(limit=APPOINTMENT_SMS_LIMIT)
    return {
        "can_see_appointment_sms": True,
        "appointment_sms": history,
        "appointment_sms_stats": get_appointment_sms_stats(history),
    }


def sms_notifications_context(compose=None, errors=None):
    """Everything Screen 09 renders.

    `compose` set means a submit came back without saving: the dialog is reopened
    holding those values with `errors` beside the fields they belong to, so the
    operator's message is never thrown away.
    """
    history = get_broadcast_history()
    latest = history[0] if history else None
    user = get_current_user()
    role = normalize_role(user["role"] if user else session.get("role"))

    return {
        "broadcasts": history,
        "stats": get_broadcast_stats(history),
        "latest": latest,
        # Names are for the care team. The Administrator and the Official read the
        # counts instead, built here so no template decides it (final fixes, M37).
        "latest_recipients": (
            get_broadcast_recipients(latest["id"], role, limit=DETAIL_RECIPIENT_LIMIT)
            if latest else []
        ),
        "latest_recipient_counts": (
            get_broadcast_recipient_counts(latest["id"]) if latest else None
        ),
        "recipient_names_visible": is_care_team(role),
        "audience_options": audience_options(),
        "audiences_unavailable": AUDIENCE_NOT_AVAILABLE,
        "categories": BROADCAST_CATEGORIES,
        "compose": compose or {},
        "errors": errors or {},
        "compose_open": bool(errors),
        # Handed to the template so the live counter in the dialog and the
        # server-side check in validate_broadcast_form() are the same numbers --
        # the alphabets included, so the counter's GSM-7/UCS-2 verdict is reached
        # from the same character sets utils.sms.message_metrics() uses rather
        # than from a second copy that could drift from it.
        "sms_limits": {
            "gsm_single": SINGLE_SEGMENT_GSM,
            "gsm_concatenated": CONCATENATED_SEGMENT_GSM,
            "unicode_single": SINGLE_SEGMENT_UNICODE,
            "unicode_concatenated": CONCATENATED_SEGMENT_UNICODE,
            "maximum": MAX_MESSAGE_CHARACTERS,
            "gsm_basic": "".join(sorted(GSM_BASIC_CHARACTERS)),
            "gsm_extended": "".join(sorted(GSM_EXTENDED_CHARACTERS)),
        },
        **_gateway_context(),
        # The individual half of this screen: one message to one patient about
        # one of their own appointments, sent from the Patient Queue or the
        # Patient Profile rather than from here. It is shown here because this is
        # where somebody asking "what has this system texted, and to whom?" comes
        # to look, and an answer that covered only broadcasts would be a partial
        # one presented as complete.
        **_appointment_sms_context(),
    }


def _extract_compose(form_data):
    return {field: (form_data.get(field) or "").strip() for field in COMPOSE_FIELDS}


def _sent_message(broadcast):
    """The line flashed after a send, naming what actually happened.

    Deliberately concrete. "Broadcast sent" would read the same whether it
    reached 21 people or nobody, and -- while there is no API key -- whether or
    not anything left the building at all. Every figure here is read back off the
    stored row, so the confirmation cannot claim more than was recorded.
    """
    recipients = broadcast["recipient_count"]
    sent = broadcast["sent_count"]
    failed = broadcast["failed_count"]

    parts = [
        f"{broadcast['reference']} sent to {sent} of {recipients} "
        f"{'recipient' if recipients == 1 else 'recipients'} "
        f"in {broadcast['audience_label']}"
    ]
    if failed:
        parts.append(f"{failed} failed")
    if broadcast["segments"] > 1:
        parts.append(
            f"{broadcast['segments']} segments per recipient "
            f"({broadcast['encoding']})"
        )
    if broadcast.get("merged_duplicates"):
        merged = broadcast["merged_duplicates"]
        parts.append(
            f"{merged} duplicate {'number was' if merged == 1 else 'numbers were'} "
            "merged, so nobody was texted twice"
        )

    message = " — ".join(parts) + "."

    # The simulated-send flag. Appended to the same confirmation rather than
    # raised as an error, because nothing went wrong: the broadcast is genuinely
    # recorded, it simply has not been transmitted yet.
    if broadcast["delivery_mode"] == SIMULATED:
        message += (
            " Simulated send: no key is set, so the message was recorded but not sent."
        )
    return message


def process_send_broadcast(form_data, user_id, ip_address=None):
    """Validate a compose submit, send it, and record it.

    Returns (broadcast, context, message). The broadcast and the context are
    mutually exclusive: a broadcast means the caller should redirect to Screen 09
    and flash `message`; a context means the caller should re-render the page with
    the compose dialog reopened on what was entered.
    """
    values = _extract_compose(form_data)

    # Resolved before validation so an audience that is real but currently empty
    # is reported as such rather than sending nothing and calling it a success.
    recipients = (
        resolve_recipients(values["audience"])[0]
        if values["audience"] in AUDIENCES else []
    )

    errors = validate_broadcast_form(values, recipients)
    if errors:
        return None, sms_notifications_context(compose=values, errors=errors), None

    broadcast = send_broadcast(
        values["message"], values["audience"], values["category"], user_id
    )

    metrics = message_metrics(values["message"])
    log_action(
        user_id,
        ACTION_SMS_BROADCAST_SENT,
        module=MODULE_SMS,
        details=(
            f"{broadcast['reference']} to {broadcast['audience_label']} "
            f"({broadcast['recipient_count']} recipients, "
            f"{broadcast['sent_count']} sent, {broadcast['failed_count']} failed); "
            f"{metrics['length']} characters, {metrics['segments']} "
            f"segment{'' if metrics['segments'] == 1 else 's'}; "
            f"{broadcast['delivery_mode']}; "
            f'category {broadcast["category"] or "none"}'
        ),
        ip_address=ip_address,
    )

    return broadcast, None, _sent_message(broadcast)

"""Semaphore SMS gateway client.

Three things live here, in order: the real HTTP call, what a message costs to
send, and the one decision that says whether an outbound message goes to the
gateway or is recorded as a simulated send.


TURNING THIS FEATURE LIVE
-------------------------
The SMS broadcast feature is complete and writes real history. The only thing it
does not do today is put bytes on the wire, because the project has no Semaphore
account yet. To make it fully live:

    1. Create a Semaphore account at https://semaphore.co and obtain the API key
       from its dashboard.
    2. Set that key in the environment the app runs in, then restart it:

           Windows PowerShell   $env:SEMAPHORE_API_KEY = "your-key-here"
           Linux / macOS        export SEMAPHORE_API_KEY="your-key-here"

That is the whole activation step. Nothing in this file, in models/broadcasts.py,
in routes/broadcast_views.py or in the templates changes: deliver_announcement_sms()
below reads the environment on every call, so the first broadcast sent after the
key is present goes through send_announcement_sms() to Semaphore's live endpoint
and is recorded with delivery_mode 'live'. Broadcasts already in the history keep
their 'simulated' mark, which is correct -- those messages genuinely were not
transmitted.

A sender name (Semaphore calls it a sender ID) is optional and is deliberately
not sent: an account without an approved sender name has its messages delivered
under Semaphore's default, which is the correct behaviour for a new account.
"""
import os
from urllib import parse, request as urllib_request

from utils.phone import is_valid_ph_mobile, normalize_phone_number


def send_announcement_sms(announcement_text, recipient_number, api_key=None):
    """Send an SMS notification for a barangay announcement to a resident contact number."""
    api_key = api_key or os.environ.get("SEMAPHORE_API_KEY")
    normalized_number = normalize_phone_number(recipient_number)

    if not api_key or not announcement_text or not normalized_number:
        return {
            "success": False,
            "error": "Missing API key, announcement text, or recipient number",
        }

    payload = {
        "apikey": api_key,
        "number": normalized_number,
        "message": announcement_text,
    }
    encoded_payload = parse.urlencode(payload).encode("utf-8")
    request_obj = urllib_request.Request(
        "https://api.semaphore.co/api/v4/messages",
        data=encoded_payload,
        method="POST",
    )
    request_obj.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib_request.urlopen(request_obj, timeout=15) as response:
            response_body = response.read().decode("utf-8")
            return {"success": True, "status": "sent", "response": response_body}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# WHAT A MESSAGE COSTS TO SEND
#
# An SMS is not measured in characters, it is measured in segments, and the
# segment size depends on which alphabet the text needs:
#
#   GSM-7   the 7-bit alphabet of GSM 03.38. 160 characters in a single message;
#           153 per part once a message is long enough to be split, because the
#           concatenation header takes the other 7.
#   UCS-2   any character outside that alphabet forces the WHOLE message into
#           16-bit encoding: 70 characters single, 67 per part when split.
#
# That cliff is the reason this is computed rather than approximated. One emoji,
# one curly quote pasted from Word, or one "…" drops a 160-character advisory to
# 70 and turns one message per recipient into three. Filipino text is safe: ñ, Ñ
# and à are all in the GSM basic set.
#
# Semaphore bills one message credit per segment, so `segments` here is also the
# per-recipient cost of a broadcast. MAX_MESSAGE_CHARACTERS is Semaphore's
# documented ceiling for a single message; it is worth re-checking against the
# account's own dashboard once one exists, but as a guard it only ever refuses a
# message far longer than anything this screen is for.
# ---------------------------------------------------------------------------

SINGLE_SEGMENT_GSM = 160
CONCATENATED_SEGMENT_GSM = 153
SINGLE_SEGMENT_UNICODE = 70
CONCATENATED_SEGMENT_UNICODE = 67
MAX_MESSAGE_CHARACTERS = 1600

# GSM 03.38 basic character set. Anything here is one septet.
GSM_BASIC_CHARACTERS = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΘΞ"
    "ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# The extension table. Still GSM-7, but each of these costs two septets because
# it is transmitted as an escape followed by the character.
GSM_EXTENDED_CHARACTERS = frozenset("^{}\\[~]|€\f")


def message_metrics(text):
    """How the gateway will see one message: encoding, segments, room left.

    Returns the numbers the compose form's counter and the send-time validation
    both read, so what the operator is shown and what the server enforces are the
    same calculation rather than two that agree by coincidence.

    An empty message is 0 segments, not 1 -- nothing is sent, so nothing is
    charged, and the counter should not claim a cost before anything is typed.
    """
    text = text or ""

    needs_unicode = any(
        character not in GSM_BASIC_CHARACTERS
        and character not in GSM_EXTENDED_CHARACTERS
        for character in text
    )

    if needs_unicode:
        encoding = "UCS-2"
        # Every character is one 16-bit unit; the extension table does not apply.
        length = len(text)
        single, concatenated = SINGLE_SEGMENT_UNICODE, CONCATENATED_SEGMENT_UNICODE
    else:
        encoding = "GSM-7"
        length = sum(
            2 if character in GSM_EXTENDED_CHARACTERS else 1 for character in text
        )
        single, concatenated = SINGLE_SEGMENT_GSM, CONCATENATED_SEGMENT_GSM

    if length == 0:
        segments = 0
    elif length <= single:
        segments = 1
    else:
        # Ceiling division: a message that spills past `single` is sent as parts
        # of `concatenated` each, header included.
        segments = -(-length // concatenated)

    capacity = single if segments <= 1 else concatenated * segments

    return {
        "characters": len(text),
        # What the gateway counts, which is longer than len(text) when the
        # message contains escaped characters such as { } [ ] ~ or €.
        "length": length,
        "encoding": encoding,
        "segments": segments,
        "segment_size": single if segments <= 1 else concatenated,
        "remaining": capacity - length,
        "max_characters": MAX_MESSAGE_CHARACTERS,
        "over_maximum": length > MAX_MESSAGE_CHARACTERS,
        "multi_segment": segments > 1,
        # True when a non-GSM character has forced the whole message into 16-bit
        # encoding. Worth surfacing: it is almost always one pasted character,
        # and removing it more than doubles the room available.
        "unicode_forced": needs_unicode,
    }


# ---------------------------------------------------------------------------
# LIVE OR SIMULATED
#
# One decision, in one place. See the module header for the activation step.
# ---------------------------------------------------------------------------

LIVE = "live"
SIMULATED = "simulated"

SIMULATED_NOTE = (
    "Simulated send: no key is set for the messaging service, so nothing was "
    "transmitted."
)


def gateway_configured(api_key=None):
    """Whether a Semaphore API key is available to this process."""
    return bool(api_key or os.environ.get("SEMAPHORE_API_KEY"))


def deliver_announcement_sms(announcement_text, recipient_number, api_key=None):
    """Send one message live, or record a simulated send when there is no key.

    The single point where the feature is either live or not. With a key present
    this is send_announcement_sms() and nothing else -- same call, same endpoint,
    same response -- so no code changes when credentials arrive.

    Returns a dict every caller can store as-is:

        success   whether the message was accepted (or would have been)
        status    'sent' or 'failed', matching the recipient status column
        mode      'live' or 'simulated'
        response  the gateway's reply, or the note saying nothing was sent
        error     present only on a failure

    A missing or unusable number fails in both modes. Simulating a send to a
    number the gateway would reject would record a success that could not happen,
    which is exactly the kind of figure this feature must not manufacture. Note
    that "unusable" is is_valid_ph_mobile() and not merely "has digits in it":
    normalize_phone_number() hands back whatever digits it was given when they
    are not a Philippine mobile, so a five-digit typo would otherwise pass this
    guard and be recorded as sent.
    """
    mode = LIVE if gateway_configured(api_key) else SIMULATED

    if not announcement_text or not is_valid_ph_mobile(recipient_number):
        return {
            "success": False,
            "status": "failed",
            "mode": mode,
            "error": "Missing message text or usable recipient number",
        }

    if mode == LIVE:
        result = send_announcement_sms(announcement_text, recipient_number, api_key)
        result["mode"] = LIVE
        result["status"] = "sent" if result.get("success") else "failed"
        return result

    return {
        "success": True,
        "status": "sent",
        "mode": SIMULATED,
        "response": SIMULATED_NOTE,
    }

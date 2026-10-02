"""Philippine mobile number formatting for the SMS gateway."""
import re


def normalize_phone_number(number):
    cleaned = re.sub(r"\D", "", number or "")
    if not cleaned:
        return ""
    if cleaned.startswith("0"):
        return "63" + cleaned[1:]
    if cleaned.startswith("63"):
        return cleaned
    if len(cleaned) == 10 and cleaned.startswith("9"):
        return "63" + cleaned
    return cleaned


def is_valid_ph_mobile(number):
    """True for anything normalize_phone_number() can turn into 639XXXXXXXXX.

    Deliberately the same funnel the SMS gateway uses, so a number accepted at
    registration is one send_announcement_sms() can actually dial. Philippine
    mobile numbers are 10 digits beginning with 9 once the country code is off.
    """
    normalized = normalize_phone_number(number)
    return len(normalized) == 12 and normalized.startswith("639")


def to_local_ph_mobile(number):
    """639171234567 -> 09171234567, the format the existing rows are stored in.

    Returns "" if the input is not a valid mobile number.
    """
    if not is_valid_ph_mobile(number):
        return ""
    return "0" + normalize_phone_number(number)[2:]


# THE MASK (Task 5d, D3). On every SMS screen, export and JSON response a phone
# number shows its last four digits only. The full number stays where the system
# sends messages: the recipient tables, and models/broadcasts.py send_broadcast(),
# which hands it to the gateway. Everything that is shown goes through here, so a
# number is masked the same way on every page and file.
MASK_PREFIX = "•••• •••"

# A Philippine mobile number as written in free text: 09 and nine more digits, +63 / 63
# and 9 and nine more digits, with spaces, dashes, dots or brackets anywhere between
# the digits ("0917-123-4567", "+63 917 123 4567", "(0917) 123 4567"), and not part
# of a longer run of digits. The optional "open" group is a bracket just before the
# number; it is dropped when the number closes a bracket that it did not open.
_SEP = r"[\s.\-()\[\]]*"
_PH_MOBILE_IN_TEXT = re.compile(
    r"(?P<open>[(\[]?)(?P<num>(?<!\d)(?:\+" + _SEP + r")?(?:63|0)" + _SEP + r"9(?:" + _SEP
    + r"\d){9}(?!\d))"
)


def mask_phone(number):
    """An eleven-digit number -> '•••• •••' and its last four digits.

    An empty value stays empty. A value of four digits or fewer shows none of
    them, so a short string is never revealed whole. A value already masked is
    returned as it is.
    """
    text = str(number or "").strip()
    if not text or MASK_PREFIX in text:
        return text
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if len(digits) <= 4:
        return MASK_PREFIX
    return f"{MASK_PREFIX} {digits[-4:]}"


def _mask_match(match):
    number, opener = match.group("num"), match.group("open")
    masked = mask_phone(number)
    closers = number.count(")") + number.count("]")
    openers = number.count("(") + number.count("[")
    # "(0917) 123 4567": the number closes the bracket in front of it, so the bracket goes too.
    return masked if closers > openers else opener + masked


def mask_numbers_in_text(text):
    """Mask every mobile number written inside a longer text, such as an audit entry."""
    if not text:
        return text
    return _PH_MOBILE_IN_TEXT.sub(_mask_match, text)

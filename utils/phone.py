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

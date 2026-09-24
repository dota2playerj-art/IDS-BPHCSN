"""Role vocabulary.

schema.sql stores exactly four role strings ('Admin', 'Doctor', 'Health Center
Staff', 'Barangay Official'), but sessions, decorators and templates each spell
them a little differently. Everything funnels through normalize_role() so
comparisons happen on one canonical form.

'Doctor' is the fourth, added when the RHU's own field data separated two jobs
that this system had held under one account: administering the system (the
Administrator -- a barangay Kagawad on the Health Committee, not a physician)
and exercising clinical authority (the RHU doctor). See models/consultations.py
can_diagnose() for what the Doctor role alone may do.
"""


def normalize_role(role):
    if role is None:
        return ""
    normalized = str(role).strip().lower()
    if normalized in {"admin", "administrator", "system administrator"}:
        return "admin"
    if normalized in {"doctor", "physician", "rhu physician"}:
        return "doctor"
    if normalized in {"health staff", "health center staff", "staff"}:
        return "health staff"
    if normalized in {"barangay official", "official"}:
        return "barangay official"
    return normalized

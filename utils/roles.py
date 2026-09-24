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


# THE ONE ROLE THAT HOLDS CLINICAL AUTHORITY.
# Diagnosing, deciding a treatment, deciding that a diagnosis is privileged and
# sealing it, reading one that is sealed, and declaring a patient dead are all
# licensed clinical acts, and at the RHU they are the doctor's. They used to be
# the Administrator's, on the assumption that the Administrator was the doctor;
# the Administrator is a barangay Kagawad, and that assumption is gone.
#
# Every one of those permissions delegates here -- models/consultations.py
# can_diagnose() and can_view_restricted(), models/patients.py
# can_declare_death() -- so they are one rule rather than several copies of it
# that could come to name different roles. It lives in this module rather than
# in either model because models/consultations.py imports models/patients.py,
# and a rule both need cannot sit in the one the other cannot import.
CLINICAL_AUTHORITY_ROLE = "doctor"


def holds_clinical_authority(role):
    """Whether this role is the licensed clinician. Only the Doctor is."""
    return normalize_role(role) == CLINICAL_AUTHORITY_ROLE

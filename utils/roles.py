"""Role vocabulary.

schema.sql stores exactly three role strings ('Admin', 'Health Center Staff',
'Barangay Official'), but sessions, decorators and templates each spell them a
little differently. Everything funnels through normalize_role() so comparisons
happen on one canonical form.
"""


def normalize_role(role):
    if role is None:
        return ""
    normalized = str(role).strip().lower()
    if normalized in {"admin", "administrator", "system administrator"}:
        return "admin"
    if normalized in {"health staff", "health center staff", "staff"}:
        return "health staff"
    if normalized in {"barangay official", "official"}:
        return "barangay official"
    return normalized

"""The audit entry for a sealed consultation that could not be opened (H4).

Only the Doctor reaches this: every other role is shown the placeholder and
never asks for the text. When the key on this computer cannot decrypt a sealed
field, the Doctor sees one plain line and this writes one entry. The entry holds
no clinical text.
"""
from flask import request, session

from models.audit import ACTION_SEALED_UNOPENABLE, MODULE_CONFIDENTIALITY, log_action


def log_unopenable(patient, consultation_ids, screen):
    """One entry naming every consultation on this page that could not be opened."""
    ids = sorted({cid for cid in consultation_ids if cid})
    if not ids:
        return None
    visits = ", ".join(f"#{cid}" for cid in ids)
    return log_action(
        user_id=session.get("user_id"),
        action=ACTION_SEALED_UNOPENABLE,
        module=MODULE_CONFIDENTIALITY,
        details=(f"{screen} for {patient['full_name']} ({patient['patient_id']}): "
                 f"consultation {visits} could not be opened with the key on this "
                 "computer. Nothing was changed."),
        ip_address=request.remote_addr,
    )

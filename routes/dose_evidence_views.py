"""Recording a dose given elsewhere, with its evidence (Task 9, D3 to D6).

Outside a consultation: from a scheduled dose's row on the Immunization Record tab.
Health Center Staff and the Doctor only; the routes are in routes/staff.py, and the
Administrator and the Barangay Official have no route to any of this.

The rules are enforced here and in models/immunizations.py, not by the form:
the dose is one the schedule lists, the proof is one of the two choices, a card needs
a date, a parent's report may have none, and no date is in the future or before birth.
"""
from models.immunizations import (
    DATE_FIELD,
    DOSE_FIELD,
    EVIDENCE_CARD,
    MAX_PLACE_LENGTH,
    PLACE_FIELD,
    PROOF_CHOICES,
    PROOF_FIELD,
    clean_place,
    dose_label,
    get_immunization_by_id,
    parse_dose_keys,
    record_elsewhere_dose,
    remove_elsewhere_dose,
    update_elsewhere_dose,
    validate_evidence,
    validate_reported_date,
)
from models.immunizations import get_immunization_status
from models.patients import get_patient_by_id
from routes.audit_entries import (
    elsewhere_dose_changed,
    elsewhere_dose_recorded,
    elsewhere_dose_removed,
)
from utils.dates import today

RECORD_FIELD = "record_id"


def elsewhere_options():
    """What the dialog prints: the two proofs, the field names, today as the date ceiling."""
    return {
        "choices": PROOF_CHOICES,
        "proof_field": PROOF_FIELD,
        "date_field": DATE_FIELD,
        "place_field": PLACE_FIELD,
        "dose_field": DOSE_FIELD,
        "record_field": RECORD_FIELD,
        "max_place_length": MAX_PLACE_LENGTH,
        "today": today(),
        "card": EVIDENCE_CARD,
    }


def _read_evidence_fields(form_data, patient):
    """Proof, date and place from the dialog. Returns (values, errors)."""
    errors = {}
    evidence, error = validate_evidence(form_data.get(PROOF_FIELD))
    if error:
        errors[PROOF_FIELD] = error
    date_text, date_error = validate_reported_date(
        form_data.get(DATE_FIELD), patient, required=evidence == EVIDENCE_CARD)
    if date_error:
        errors[DATE_FIELD] = date_error
    if errors:
        return None, errors
    return {"evidence": evidence, "date": date_text,
            "place": clean_place(form_data.get(PLACE_FIELD))}, {}


def _reopen(mode, form_data, errors, label, record_id=None, dose_key=""):
    """The dialog's state after a submit that did not save: what was typed, and why."""
    return {
        "open": True,
        "mode": mode,
        "errors": errors,
        "label": label,
        "record_id": record_id,
        "dose_key": dose_key,
        "form": {
            PROOF_FIELD: str(form_data.get(PROOF_FIELD) or "").strip(),
            DATE_FIELD: str(form_data.get(DATE_FIELD) or "").strip(),
            PLACE_FIELD: str(form_data.get(PLACE_FIELD) or "").strip(),
        },
        "banner": "Nothing has been saved. Correct the highlighted "
                  f"field{'' if len(errors) == 1 else 's'} below.",
    }


def _early_note(patient, code, dose_number):
    """A sentence to add when the card date shows the dose was given too early (Task 13, D4):
    it is on file, but it does not count, and the Doctor decides about a repeat."""
    status = get_immunization_status(get_patient_by_id(patient["id"]))
    item = next((i for i in status["schedule"]
                 if i["code"] == code and i["dose_number"] == dose_number), None)
    if item and item["too_early"]:
        return " It was given too early, so it does not count. Ask the Doctor about a repeat."
    return ""


def process_record_elsewhere(patient_id, form_data, user_id, ip_address=None):
    """Record one dose given elsewhere. Returns (patient_id, reopen, message)."""
    patient = get_patient_by_id(patient_id)
    if patient is None:
        return None, None, "That patient record could not be found."
    keys = parse_dose_keys([form_data.get(DOSE_FIELD)])
    if len(keys) != 1:
        return patient_id, None, "Choose a dose from the schedule."
    code, dose_number = keys[0]
    label = dose_label(code, dose_number)
    values, errors = _read_evidence_fields(form_data, patient)
    if errors:
        return patient_id, _reopen("record", form_data, errors, label,
                                   dose_key=f"{code}:{dose_number}"), None
    outcome = record_elsewhere_dose(
        patient["id"], code, dose_number, values["evidence"], values["date"],
        values["place"], user_id,
        audit=elsewhere_dose_recorded(patient["id"], user_id, ip_address))
    name = patient["full_name"]
    if outcome == "recorded":
        if values["evidence"] == EVIDENCE_CARD:
            return patient_id, None, (
                f"{label} is recorded as given elsewhere for {name}. The card was seen."
                + _early_note(patient, code, dose_number))
        return patient_id, None, (
            f"{label} is recorded for {name} as: the parent says it was given, no card. "
            "It does not count as given until the card is shown.")
    if outcome == "upgraded":
        return patient_id, None, (
            f"{label} for {name} is now recorded as given elsewhere. The card was seen."
            + _early_note(patient, code, dose_number))
    if outcome == "unchanged":
        return patient_id, None, (
            f"{label} already has a parent's report for {name}. To add the card, choose "
            "the card as proof.")
    if outcome == "already-given":
        return patient_id, None, (
            f"{label} is already recorded as given for {name}. Nothing was changed.")
    return patient_id, None, "That dose could not be recorded. Check the proof and the date."


def process_change_elsewhere(form_data, user_id, ip_address=None):
    """Change a card or parent's-report record. Returns (patient_id, reopen, message)."""
    raw = str(form_data.get(RECORD_FIELD) or "").strip()
    record = get_immunization_by_id(int(raw)) if raw.isdigit() else None
    if record is None:
        return None, None, "That dose record could not be found."
    patient = get_patient_by_id(record["patient_id"])
    if patient is None:
        return None, None, "That patient record could not be found."
    label = dose_label(record["vaccine_code"], record["dose_number"])
    if record["evidence"] == "given_here":
        return patient["id"], None, (
            f"{label} was given at this health center. It is corrected with the "
            "record's Correct button.")
    values, errors = _read_evidence_fields(form_data, patient)
    if errors:
        return patient["id"], _reopen("change", form_data, errors, label,
                                      record_id=record["id"]), None
    outcome = update_elsewhere_dose(
        record["id"], values["evidence"], values["date"], values["place"],
        audit=elsewhere_dose_changed(patient["id"], user_id, ip_address))
    name = patient["full_name"]
    note = _early_note(patient, record["vaccine_code"], record["dose_number"])
    if outcome == "upgraded":
        return patient["id"], None, (
            f"{label} for {name} is now recorded as given elsewhere. The card was seen." + note)
    if outcome == "updated":
        return patient["id"], None, (
            f"{label} for {name} is changed. The change is in the audit log." + note)
    if outcome == "unchanged":
        return patient["id"], None, f"No change. {label} for {name} is as it was."
    if outcome == "duplicate":
        return patient["id"], None, (
            f"{label} for {name} already has a dose that counts. Nothing was changed.")
    return patient["id"], None, "That dose record could not be changed."


def process_remove_elsewhere(form_data, user_id, ip_address=None):
    """Remove a card or parent's-report record. Returns (patient_id, message)."""
    raw = str(form_data.get(RECORD_FIELD) or "").strip()
    record = get_immunization_by_id(int(raw)) if raw.isdigit() else None
    if record is None:
        return None, "That dose record could not be found."
    patient = get_patient_by_id(record["patient_id"])
    if patient is None:
        return None, "That patient record could not be found."
    label = dose_label(record["vaccine_code"], record["dose_number"])
    outcome = remove_elsewhere_dose(
        record["id"], audit=elsewhere_dose_removed(patient["id"], user_id, ip_address))
    if outcome == "removed":
        return patient["id"], (
            f"The record of {label} given elsewhere is removed for {patient['full_name']}.")
    return patient["id"], (
        f"{label} was given at this health center. A dose given here is never removed.")

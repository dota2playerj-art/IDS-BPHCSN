"""The audit entries for health-record writes (Task 4, H3).

Each function here returns an `audit` callback for one model write function.
The model calls it on its own connection just before it commits, so the entry
commits with the change or rolls back with it:

    create_patient(values, audit=patient_registered(user_id, ip_address))

One short line per entry. The acting account is the entry's user, so it is
not repeated in the text. Patients are named as "Name (PAT-001)", as the older
entries do. A change of value uses the shape the Audit Logs panel draws as a
before/after pair: "<record> — Label: before → after; note". These entries NEVER contain diagnosis or treatment text, any field
of a consultation, a password or a contact number. A patient edit lists the
fields that changed, not their values.
"""
from models.audit import (
    ACTION_CONSULTATION_COMPLETED,
    ACTION_LEFT_BEFORE_SEEN,
    ACTION_LEFT_UNDONE,
    ACTION_REFERRAL_UNDONE,
    ACTION_REFERRED,
    ACTION_SENT_TO_DOCTOR,
    ACTION_VISIT_SENT,
    ACTION_SERVICE_CHANGED,
    ACTION_CONSULTATION_RECORDED,
    ACTION_CONSULTATION_STARTED,
    ACTION_EPI_DOSES_RECORDED,
    ACTION_INVENTORY_ADDED,
    ACTION_INVENTORY_ARCHIVED,
    ACTION_INVENTORY_EDITED,
    ACTION_INVENTORY_RESTORED,
    ACTION_MEDICINE_DISPENSED,
    ACTION_OTHER_VACCINATIONS_RECORDED,
    ACTION_PATIENT_CHECKED_IN,
    ACTION_PATIENT_DEATH_REVERSED,
    ACTION_PATIENT_DECLARED_DECEASED,
    ACTION_PATIENT_REGISTERED,
    ACTION_PATIENT_STATUS_CHANGED,
    ACTION_PATIENT_UPDATED,
    ACTION_REPORTED_DOSES_RECORDED,
    ACTION_ELSEWHERE_DOSE_CHANGED,
    ACTION_ELSEWHERE_DOSE_RECORDED,
    ACTION_ELSEWHERE_DOSE_REMOVED,
    ACTION_PARENT_REPORT_RECORDED,
    ACTION_PARENT_REPORT_UPGRADED,
    ACTION_STOCK_RECEIVED,
    ACTION_STOCK_REMOVED,
    MODULE_APPOINTMENTS,
    MODULE_CONSULTATIONS,
    MODULE_IMMUNIZATIONS,
    MODULE_INVENTORY,
    MODULE_PATIENTS,
    log_action,
)
from utils.dates import display_date, today

DECEASED = "Deceased"

# Plain names for the patient fields, for "Changed: ..." on an edit.
PATIENT_FIELD_LABELS = {
    "first_name": "First name",
    "middle_name": "Middle name",
    "last_name": "Last name",
    "birth_date": "Birth date",
    "sex": "Sex",
    "civil_status": "Civil status",
    "blood_type": "Blood type",
    "address": "Address",
    "municipality": "Municipality",
    "province": "Province",
    "zip_code": "ZIP code",
    "contact_number": "Contact number",
    "emergency_contact_name": "Emergency contact name",
    "emergency_contact_relationship": "Emergency contact relationship",
    "emergency_contact_number": "Emergency contact number",
    "emergency_contact_address": "Emergency contact address",
    "medical_conditions": "Medical conditions",
    "allergies": "Allergies",
}


def _patient(conn, patient_id):
    """'Maria Santos (PAT-001)', read on the writer's own connection."""
    row = conn.execute(
        "SELECT first_name, middle_name, last_name, patient_id FROM patients WHERE id = ?",
        (patient_id,),
    ).fetchone()
    if row is None:
        return f"patient #{patient_id}"
    name = " ".join(p for p in (row["first_name"], row["middle_name"], row["last_name"]) if p)
    return f"{name} ({row['patient_id']})"


def _visit(conn, appointment_id):
    """(patient label, 'APT-00081', is_walkin) for one queue entry."""
    row = conn.execute(
        "SELECT patient_id, is_walkin FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    patient = _patient(conn, row["patient_id"]) if row else "an unknown patient"
    return patient, f"APT-{appointment_id:05d}", bool(row and row["is_walkin"])


def _item(conn, item_id):
    """'Paracetamol 500 mg (MED-0038)'."""
    row = conn.execute(
        "SELECT name, item_code FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    return f"{row['name']} ({row['item_code']})" if row else f"item #{item_id}"


def _entry(user_id, ip_address, action, module):
    """A writer for one kind of entry, on the caller's connection."""
    def write(conn, details):
        log_action(user_id, action, module, details, ip_address, conn=conn)
    return write


def _count(n, noun):
    return f"{n} {noun}{'' if n == 1 else 's'}"


# --- Patient Records ---------------------------------------------------------

def patient_registered(user_id, ip_address=None):
    write = _entry(user_id, ip_address, ACTION_PATIENT_REGISTERED, MODULE_PATIENTS)
    return lambda conn, patient_id: write(conn, f"{_patient(conn, patient_id)} registered.")


def patient_updated(patient_id, user_id, ip_address=None):
    write = _entry(user_id, ip_address, ACTION_PATIENT_UPDATED, MODULE_PATIENTS)

    def audit(conn, changed):
        names = ", ".join(PATIENT_FIELD_LABELS.get(f, f) for f in changed)
        write(conn, f"{_patient(conn, patient_id)} — Changed: {names}")
    return audit


def patient_status_changed(new_status, user_id, ip_address=None):
    """One entry per patient changed. A death and its reversal have their own phrase."""
    def audit(conn, moved):
        day = display_date(today())
        for patient_id, old_status in moved:
            who = _patient(conn, patient_id)
            details = f"{who} — Status: {old_status} → {new_status}"
            if new_status == DECEASED:
                action = ACTION_PATIENT_DECLARED_DECEASED
                details += f"; Declared deceased on {day}"
            elif old_status == DECEASED:
                action = ACTION_PATIENT_DEATH_REVERSED
                details += f"; Death declaration reversed on {day}"
            else:
                action = ACTION_PATIENT_STATUS_CHANGED
            log_action(user_id, action, MODULE_PATIENTS, details, ip_address, conn=conn)
    return audit


# --- Consultations and the doses recorded with them ----------------------------

def consultation_recorded(patient_id, visit_date, user_id, ip_address=None):
    """Names the consultation, the patient and the visit date. Nothing clinical."""
    write = _entry(user_id, ip_address, ACTION_CONSULTATION_RECORDED, MODULE_CONSULTATIONS)
    return lambda conn, consultation_id: write(
        conn, f"Consultation #{consultation_id} for {_patient(conn, patient_id)}, "
              f"visit {display_date(visit_date)}.")


def _doses(action, patient_id, consultation_id, user_id, ip_address):
    """How many doses, for whom, at which consultation. Never which vaccine (Task 5c).

    Audit Logs are read by the Administrator, who is not part of the patient's
    care. Which vaccines a named patient received is an immunization record, and
    it stays on the patient's profile for the care team.
    """
    write = _entry(user_id, ip_address, action, MODULE_IMMUNIZATIONS)

    def audit(conn, stored):
        write(conn, f"Recorded {_count(len(stored), 'dose')} for "
                    f"{_patient(conn, patient_id)} at consultation #{consultation_id}.")
    return audit


def epi_doses_recorded(patient_id, consultation_id, user_id, ip_address=None):
    return _doses(ACTION_EPI_DOSES_RECORDED, patient_id, consultation_id, user_id, ip_address)


def reported_doses_recorded(patient_id, consultation_id, user_id, ip_address=None):
    return _doses(ACTION_REPORTED_DOSES_RECORDED, patient_id, consultation_id, user_id, ip_address)


def elsewhere_dose_recorded(patient_id, user_id, ip_address=None):
    """One dose given elsewhere, recorded outside a consultation. Never which vaccine.

    `audit(conn, outcome)`: a new card record, a new parent report, or a parent report
    upgraded to a card record, each with its own action and wording (Task 9, D6).
    """
    card = _entry(user_id, ip_address, ACTION_ELSEWHERE_DOSE_RECORDED, MODULE_IMMUNIZATIONS)
    parent = _entry(user_id, ip_address, ACTION_PARENT_REPORT_RECORDED, MODULE_IMMUNIZATIONS)
    upgraded = _entry(user_id, ip_address, ACTION_PARENT_REPORT_UPGRADED, MODULE_IMMUNIZATIONS)

    def audit(conn, outcome, evidence="card"):
        who = _patient(conn, patient_id)
        if outcome == "upgraded":
            upgraded(conn, f"Upgraded a parent report to a card record for {who}.")
        elif evidence == "parent_report":
            parent(conn, f"Recorded a parent report of 1 dose for {who}.")
        else:
            card(conn, f"Recorded 1 dose given elsewhere for {who}.")
    return audit


def elsewhere_dose_changed(patient_id, user_id, ip_address=None):
    """A card or parent's-report record changed. `audit(conn, outcome)`."""
    changed = _entry(user_id, ip_address, ACTION_ELSEWHERE_DOSE_CHANGED, MODULE_IMMUNIZATIONS)
    upgraded = _entry(user_id, ip_address, ACTION_PARENT_REPORT_UPGRADED, MODULE_IMMUNIZATIONS)

    def audit(conn, outcome):
        who = _patient(conn, patient_id)
        if outcome == "upgraded":
            upgraded(conn, f"Upgraded a parent report to a card record for {who}.")
        else:
            changed(conn, f"Changed 1 dose record given elsewhere for {who}.")
    return audit


def elsewhere_dose_removed(patient_id, user_id, ip_address=None):
    write = _entry(user_id, ip_address, ACTION_ELSEWHERE_DOSE_REMOVED, MODULE_IMMUNIZATIONS)
    return lambda conn: write(
        conn, f"Removed 1 dose record given elsewhere for {_patient(conn, patient_id)}.")


def other_vaccinations_recorded(patient_id, consultation_id, user_id, ip_address=None):
    return _doses(ACTION_OTHER_VACCINATIONS_RECORDED, patient_id, consultation_id, user_id, ip_address)


# --- Medicine Inventory ----------------------------------------------------------

def medicine_dispensed(patient_id, consultation_id, user_id, ip_address=None):
    """Who received how many items, at which consultation. Never which medicine.

    A medicine can reveal a condition, and Audit Logs are read by the
    Administrator, who is not part of the patient's care (Task 5c). What was
    handed over stays on the patient's profile for the care team, and the stock
    level of each item is on Medicine Inventory.
    """
    write = _entry(user_id, ip_address, ACTION_MEDICINE_DISPENSED, MODULE_INVENTORY)

    def audit(conn, stored):
        where = f" at consultation #{consultation_id}" if consultation_id else ""
        write(conn, f"Dispensed {_count(len(stored), 'item')} for "
                    f"{_patient(conn, patient_id)}{where}.")
    return audit


def inventory_added(user_id, ip_address=None):
    """A new item. It holds no stock yet: stock arrives as a batch (Receive stock)."""
    write = _entry(user_id, ip_address, ACTION_INVENTORY_ADDED, MODULE_INVENTORY)

    def audit(conn, item_id):
        write(conn, f"{_item(conn, item_id)}.")
    return audit


def inventory_edited(item_id, user_id, ip_address=None):
    """Edit details changes the item's fields, never a quantity. Fields are named, not quoted."""
    def audit(conn, changes):
        status = next((c for c in changes if c["field"] == "status"), None)
        others = [c["label"] for c in changes if c is not status]
        parts = []
        if status:
            parts.append(f"Status: {status['old']} → {status['new']}")
        if others:
            parts.append(("Also changed: " if parts else "Changed: ") + ", ".join(others))
        log_action(user_id, ACTION_INVENTORY_EDITED, MODULE_INVENTORY,
                   f"{_item(conn, item_id)} — " + "; ".join(parts), ip_address, conn=conn)
    return audit


def _batch_label(conn, batch_id):
    """'Paracetamol 500 mg tablet (MED-0001), lot L-123' for a batch."""
    row = conn.execute(
        "SELECT inventory_item_id, lot_number FROM inventory_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    return f"{_item(conn, row['inventory_item_id'])}, lot {row['lot_number']}"


def stock_received(user_id, ip_address=None):
    """Who, the item, the lot and the amount received."""
    write = _entry(user_id, ip_address, ACTION_STOCK_RECEIVED, MODULE_INVENTORY)

    def audit(conn, batch_id):
        quantity = conn.execute(
            "SELECT quantity_received FROM inventory_batches WHERE id = ?", (batch_id,)
        ).fetchone()["quantity_received"]
        write(conn, f"{_batch_label(conn, batch_id)}: received {quantity:,}.")
    return audit


def stock_removed(user_id, ip_address=None):
    """Who, the item, the lot, the amount and the reason. The note is not copied here."""
    write = _entry(user_id, ip_address, ACTION_STOCK_REMOVED, MODULE_INVENTORY)

    def audit(conn, removal):
        write(conn, f"{_batch_label(conn, removal['batch_id'])}: removed "
                    f"{removal['quantity']:,} ({removal['reason']}).")
    return audit


def inventory_status_changed(item_id, old_status, new_status, user_id, ip_address=None):
    action = ACTION_INVENTORY_RESTORED if new_status == "Active" else ACTION_INVENTORY_ARCHIVED
    write = _entry(user_id, ip_address, action, MODULE_INVENTORY)
    return lambda conn: write(
        conn, f"{_item(conn, item_id)} — Status: {old_status} → {new_status}")


# --- Appointment Scheduling (the Patient Queue) -----------------------------------

def patient_checked_in(user_id, ip_address=None):
    """The visit reason is not included: it is what the patient came in with."""
    write = _entry(user_id, ip_address, ACTION_PATIENT_CHECKED_IN, MODULE_APPOINTMENTS)

    def audit(conn, appointment_id, outcome):
        patient, ref, walkin = _visit(conn, appointment_id)
        kind = "walk-in" if walkin else "booked visit"
        write(conn, f"{patient}, visit {ref}, {kind}.")
    return audit


def _queue_move(action, appointment_id, user_id, ip_address):
    write = _entry(user_id, ip_address, action, MODULE_APPOINTMENTS)

    def audit(conn):
        patient, ref, _ = _visit(conn, appointment_id)
        write(conn, f"{patient}, visit {ref}.")
    return audit


def consultation_started(appointment_id, user_id, ip_address=None):
    return _queue_move(ACTION_CONSULTATION_STARTED, appointment_id, user_id, ip_address)


def consultation_completed(appointment_id, user_id, ip_address=None):
    return _queue_move(ACTION_CONSULTATION_COMPLETED, appointment_id, user_id, ip_address)


def left_before_seen(appointment_id, user_id, ip_address=None):
    """The patient and the visit, as Name (PAT-005), visit APT-00081. Never why."""
    return _queue_move(ACTION_LEFT_BEFORE_SEEN, appointment_id, user_id, ip_address)


def left_undone(appointment_id, user_id, ip_address=None):
    return _queue_move(ACTION_LEFT_UNDONE, appointment_id, user_id, ip_address)


def visit_referred(appointment_id, user_id, ip_address=None):
    """'Referred <Name> (PAT-005), visit APT-00081, to the RHU.' The destination is from the
    list; the facility's typed name and the reason are never written."""
    write = _entry(user_id, ip_address, ACTION_REFERRED, MODULE_APPOINTMENTS)

    def audit(conn, destination):
        from models.referrals import DESTINATION_PHRASE
        patient, ref, _ = _visit(conn, appointment_id)
        write(conn, f"Referred {patient}, visit {ref}, to "
                    f"{DESTINATION_PHRASE.get(destination, 'another hospital or facility')}.")
    return audit


def referral_undone(appointment_id, user_id, ip_address=None):
    return _queue_move(ACTION_REFERRAL_UNDONE, appointment_id, user_id, ip_address)


def consultation_finished(appointment_id, user_id, ip_address=None):
    """Intake saved. Completed when nothing is left for the Doctor, else waiting for him.

    `audit(conn, new_status)`: the action says which. It names the patient and the
    visit, never what was recorded.
    """
    done = _queue_move(ACTION_CONSULTATION_COMPLETED, appointment_id, user_id, ip_address)
    waiting = _queue_move(ACTION_SENT_TO_DOCTOR, appointment_id, user_id, ip_address)

    def audit(conn, new_status):
        (done if new_status == "Completed" else waiting)(conn)
    return audit


def visit_service_changed(appointment_id, user_id, ip_address=None):
    """One short entry: the visit only. It names no patient and no service (Task 6c)."""
    write = _entry(user_id, ip_address, ACTION_SERVICE_CHANGED, MODULE_APPOINTMENTS)

    def audit(conn, old, new, moved):
        _, ref, _ = _visit(conn, appointment_id)
        text = f"Corrected the service of visit {ref}."
        if moved:
            text += " The visit is now In Consultation."
        write(conn, text)
    return audit


def visit_sent_to_doctor(appointment_id, user_id, ip_address=None):
    """One short entry: the visit only. It names no patient and no service."""
    write = _entry(user_id, ip_address, ACTION_VISIT_SENT, MODULE_APPOINTMENTS)

    def audit(conn):
        _, ref, _ = _visit(conn, appointment_id)
        write(conn, f"Sent visit {ref} to the Doctor.")
    return audit

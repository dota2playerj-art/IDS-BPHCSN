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
    ACTION_STOCK_ADJUSTED,
    MODULE_APPOINTMENTS,
    MODULE_CONSULTATIONS,
    MODULE_IMMUNIZATIONS,
    MODULE_INVENTORY,
    MODULE_PATIENTS,
    log_action,
)
from models.general_vaccinations import vaccination_label
from models.immunizations import dose_label
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


def _doses(action, labels_of, patient_id, consultation_id, user_id, ip_address):
    """How many doses, for whom, at which consultation. Never which vaccine (Task 5c).

    Audit Logs are read by the Administrator, who is not part of the patient's
    care. Which vaccines a named patient received is an immunization record, and
    it stays on the patient's profile for the care team. `labels_of` is kept so
    the three callers still say which kind of dose they record.
    """
    write = _entry(user_id, ip_address, action, MODULE_IMMUNIZATIONS)

    def audit(conn, stored):
        write(conn, f"Recorded {_count(len(stored), 'dose')} for "
                    f"{_patient(conn, patient_id)} at consultation #{consultation_id}.")
    return audit


def epi_doses_recorded(patient_id, consultation_id, user_id, ip_address=None):
    return _doses(ACTION_EPI_DOSES_RECORDED, lambda d: dose_label(d[0], d[1]),
                  patient_id, consultation_id, user_id, ip_address)


def reported_doses_recorded(patient_id, consultation_id, user_id, ip_address=None):
    def label(d):
        when = display_date(d[2]) if d[2] else "date not known"
        return f"{dose_label(d[0], d[1])} ({when})"
    return _doses(ACTION_REPORTED_DOSES_RECORDED, label,
                  patient_id, consultation_id, user_id, ip_address)


def other_vaccinations_recorded(patient_id, consultation_id, user_id, ip_address=None):
    return _doses(ACTION_OTHER_VACCINATIONS_RECORDED,
                  lambda e: vaccination_label(e["vaccine_name"], e["dose_number"]),
                  patient_id, consultation_id, user_id, ip_address)


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
    write = _entry(user_id, ip_address, ACTION_INVENTORY_ADDED, MODULE_INVENTORY)

    def audit(conn, item_id):
        stock = conn.execute(
            "SELECT stock_quantity FROM inventory_items WHERE id = ?", (item_id,)
        ).fetchone()["stock_quantity"]
        write(conn, f"{_item(conn, item_id)}, stock {stock}.")
    return audit


def inventory_edited(item_id, user_id, ip_address=None):
    """Stock and status are shown before and after. Other fields by name."""
    def audit(conn, changes):
        stock = next((c for c in changes if c["field"] == "stock_quantity"), None)
        status = next((c for c in changes if c["field"] == "status"), None)
        others = [c["label"] for c in changes if c not in (stock, status)]
        parts = []
        if stock:
            parts.append(f"Stock: {stock['old']} → {stock['new']}")
        if status:
            parts.append(f"Status: {status['old']} → {status['new']}")
        if others:
            parts.append(("Also changed: " if parts else "Changed: ") + ", ".join(others))
        action = ACTION_STOCK_ADJUSTED if stock else ACTION_INVENTORY_EDITED
        log_action(user_id, action, MODULE_INVENTORY,
                   f"{_item(conn, item_id)} — " + "; ".join(parts), ip_address,
                   conn=conn)
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

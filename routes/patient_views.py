"""Shared context builders for the patient screens.

Screens 03 and 04 are rendered by two blueprints each -- once for the
Administrator and once for Health Center Staff -- from the same templates with
the same data. The queries live here so the two role variants cannot drift
apart; the routes stay thin and each keeps its own role_required guard and its
own redirect target.
"""
from models.appointments import get_appointments_for_patient, get_next_appointment_for_patient
from models.consultations import get_consultations_for_patient
from models.general_vaccinations import get_general_vaccinations_for_patient
from models.immunizations import dose_label, get_immunization_status
from models.patients import (
    ALLERGY_OPTIONS,
    BLOOD_TYPES,
    CIVIL_STATUSES,
    CONDITION_OPTIONS,
    EMERGENCY_RELATIONSHIPS,
    MUNICIPALITIES,
    PATIENT_STATUSES,
    PROVINCES,
    SEXES,
    collect_list_field,
    create_patient,
    find_possible_duplicates,
    generate_next_patient_id,
    get_all_patients,
    get_patient_by_id,
    get_patient_statuses,
    get_patient_stats,
    set_patient_status,
    update_patient,
    validate_patient_form,
)
from utils.context import HEADER_SEARCH_MAX

# Bulk status changes are restricted to a selection that is already all on the
# same status. The alternative -- offering the union of every selected patient's
# valid transitions -- means one click can apply to only part of the selection
# and silently skip the rest, which on a medical record is the worst kind of
# partial write: it looks like it worked. Requiring one status makes the button
# mean exactly what it says for every row it touches. The dialog enforces this on
# the page and process_archive_patients() re-checks it on the server.
MIXED_STATUS_MESSAGE = (
    "Those records are not all on the same status. Select patients that currently "
    "share one status, then set them together."
)

# The Check In dialog's "New Patient (first visit)" path opens this same Register
# Patient screen with these two fields set, and the form carries them back on
# every submit.
#
# WHY THE INTENT TRAVELS WITH THE FORM
# ------------------------------------
# A first-time walk-in has to end up registered *and* in today's queue from one
# save, and the team's decision was to capture the full personal record while she
# is standing there rather than chase it later -- so the form she fills in is
# this one, unchanged: same fields, same validate_patient_form(), same duplicate
# warning. Nothing here is a second registration form.
#
# What the check-in path adds is only a destination. Carrying it as two hidden
# fields means it survives the round trips the form already makes -- a validation
# failure, or the "a similar patient already exists" acknowledgement -- because
# those redisplay the form and resubmit it. A session flag or a query string
# alone would be lost at the first of those, leaving a patient registered but
# never queued, which is the exact two-step problem this path removes.
CHECK_IN_FLAG_FIELD = "check_in"
CHECK_IN_REASON_FIELD = "check_in_reason"

# Matches the appointments.notes / check-in reason length the dialog allows.
CHECK_IN_REASON_MAX = 200

# Truthy spellings accepted for the flag. It is written by our own template and
# by the dialog's hidden input, so this only has to be liberal enough to survive
# a hand-typed URL.
_CHECK_IN_TRUE = {"1", "yes", "true", "on"}


def check_in_requested(source):
    """True when this Register Patient submit came from the Check In dialog.

    `source` is request.args on a GET and request.form on a POST -- both are
    mappings with .get(), so one function serves both.
    """
    return (source.get(CHECK_IN_FLAG_FIELD) or "").strip().lower() in _CHECK_IN_TRUE


def check_in_reason(source):
    """The reason for the visit typed into the Check In dialog, possibly empty."""
    return (source.get(CHECK_IN_REASON_FIELD) or "").strip()[:CHECK_IN_REASON_MAX]


# The New Appointment dialog's "New patient" path uses the same mechanism one
# step further: the booking is for somebody who has no record yet, so Register
# Patient opens carrying the appointment that has already been agreed at the
# desk, and saving the form registers them *and* books it.
#
# The details are validated before this form is ever opened (see
# process_new_patient_booking_request), so what rides along here is a booking
# already known to be sound -- and it is validated once more on the way out,
# because hidden fields are only ever a claim about what was sent.
BOOKING_FLAG_FIELD = "book_appointment"

# form/query field -> the key the booking model and validator use. Written out
# rather than reusing the model's names directly so the query string stays
# readable and cannot collide with the patient form's own fields.
BOOKING_FIELDS = {
    "booking_date": "appointment_date",
    "booking_time": "appointment_time",
    "booking_type": "appointment_type",
    "booking_staff": "assigned_staff_id",
    "booking_notes": "notes",
}


def booking_requested(source):
    """True when this Register Patient submit came from the New Appointment dialog."""
    return (source.get(BOOKING_FLAG_FIELD) or "").strip().lower() in _CHECK_IN_TRUE


def booking_details(source):
    """The booking carried on the form/query, in the shape the model validates."""
    return {
        model_key: (source.get(field) or "").strip()
        for field, model_key in BOOKING_FIELDS.items()
    }


def booking_query_args(values):
    """A validated booking rendered as the query string Register Patient opens with."""
    args = {BOOKING_FLAG_FIELD: "1"}
    for field, model_key in BOOKING_FIELDS.items():
        value = (values.get(model_key) or "").strip()
        if value:
            args[field] = value
    return args


# Save & Register Another. The submit button carries this name/value pair, the
# shape this project already uses wherever one form has more than one action --
# Patient Records' status buttons and Appointment Scheduling's queue buttons both
# post a plain <button name=... value=...> and let the route read which one was
# pressed.
#
# WHY THIS IS A DESTINATION AND NOTHING ELSE
# ------------------------------------------
# The registration POST is one write path and stays one. This flag is read only
# *after* process_register_patient() has already returned a saved row id, so the
# validation, the duplicate warning and the insert are byte-for-byte the ones the
# ordinary Save runs -- there is no second, looser save. What the flag changes is
# where the operator is put afterwards: back on a fresh Register Patient form
# instead of on the new patient's profile.
#
# It exists for the community health drives the centre runs, where staff sit and
# register a queue of people back to back. Every one of those registrations
# currently ends on a profile nobody asked to see, and the way back to the form
# is the sidebar.
SAVE_ACTION_FIELD = "save_action"
SAVE_AND_REGISTER_ANOTHER = "register_another"


def save_and_register_another_requested(form_data):
    """True when this submit came from the Save & Register Another button."""
    return (form_data.get(SAVE_ACTION_FIELD) or "").strip() == SAVE_AND_REGISTER_ANOTHER


# The address fields the fresh form keeps. Everybody registered in one sitting at
# a health drive is from the same purok, so re-typing the address for each of them
# is the whole cost the button is meant to remove; everything else on the form is
# unique to a person and must arrive blank. Barangay is not here because it is not
# a field: it is fixed to this centre and rendered disabled, never submitted.
ADDRESS_PREFILL_FIELDS = ("address", "municipality", "province", "zip_code")


def address_prefill_args(form_data):
    """The just-used address rendered as the query string the fresh form opens with.

    Carried in the URL rather than the session because the redirect is the only
    thing between the two, and a query string is visible: the operator can see
    what was kept, and clearing it is a matter of opening Register Patient from
    the sidebar instead.
    """
    args = {}
    for field in ADDRESS_PREFILL_FIELDS:
        value = (form_data.get(field) or "").strip()
        if value:
            args[field] = value
    return args


def address_prefill_form(args):
    """A form dict holding only the carried address, for the fresh form's GET.

    Every other key is absent, and the template reads an absent key exactly as it
    reads a blank one -- so name, birth date, sex, civil status, blood type,
    conditions, allergies and the emergency contact all render as they do on a
    form opened with nothing at all.
    """
    values = {}
    for field in ADDRESS_PREFILL_FIELDS:
        value = (args.get(field) or "").strip()
        if value:
            values[field] = value
    return values or None


def registered_patient_name(form_data):
    """The name just saved, for the flash the fresh form lands with.

    Read off the submitted form rather than the stored row: these are the values
    that were validated and inserted, and the flash's job is to confirm to the
    operator which person they have just finished, before the fields they typed
    disappear.
    """
    parts = [
        (form_data.get(field) or "").strip()
        for field in ("first_name", "middle_name", "last_name")
    ]
    return " ".join(part for part in parts if part)


# Handed to the template so every <select>, radio and chip is rendered from the
# same tuples the validator checks against.
FORM_OPTIONS = {
    "civil_statuses": CIVIL_STATUSES,
    "sexes": SEXES,
    "municipalities": MUNICIPALITIES,
    "provinces": PROVINCES,
    "relationships": EMERGENCY_RELATIONSHIPS,
    "blood_types": BLOOD_TYPES,
    "conditions": CONDITION_OPTIONS,
    "allergies": ALLERGY_OPTIONS,
}


def _filter_options(patients):
    """The values the roster actually holds, for Screen 03's filter dropdowns.

    Built from the rows being rendered rather than from a fixed list, so the
    panel cannot offer a cohort that does not exist -- the rule Screen 12's
    module filter already follows. The mockup's dropdown offered seven puroks
    and six statuses including "Prenatal", none of which the schema stores.

    Sorted so the order is stable between loads instead of following whatever
    order the rows arrived in.
    """
    return {
        "sexes": sorted({p["sex"] for p in patients if p.get("sex")}),
        "statuses": sorted({p["status"] for p in patients if p.get("status")}),
    }


def patient_records_context(search=""):
    """Everything Screen 03 renders: the roster and the four stat cards.

    `search` is a term arriving from the header's global search box, and it is
    the whole of what that box does. It is NOT applied here: this screen renders
    every registered patient and narrows them in the browser -- the search box
    and all five Advanced Filter controls run over the rendered rows, which gives
    the same answer a re-query would because there is no unseen page a match
    could be hiding on. Filtering the roster server-side as well would mean two
    matching rules for one box, and the moment they disagreed the screen would be
    showing a count it could not justify.

    So the term is handed to the template, which puts it in the toolbar's own
    search input, and the rule that already lives there does the matching. The
    counter, the empty state and Print List's "filtered by" line all follow from
    that one pass for free. The exports are untouched and still download the
    whole register, which their titles and cover sheets already say outright.

    Truncated rather than rejected: a term nobody can type is a hand-made URL,
    and the honest response to one is to search for the first hundred characters
    of it, not to error. Length is the only thing checked -- the matching is a
    substring test against text the server wrote, so there is nothing to escape
    here that Jinja does not escape on the way out.
    """
    patients = get_all_patients()
    return {
        "patients": patients,
        "stats": get_patient_stats(),
        "filter_options": _filter_options(patients),
        "search_term": (search or "").strip()[:HEADER_SEARCH_MAX],
    }


# The bulk bar's field name, and the one rule for reading it. Both of the things
# that bar does -- Change Status and, now, Export -- post the same checkboxes to
# the server, so both resolve them the same way: digits only, duplicates dropped,
# order preserved. Written once here rather than twice, because two copies of
# "what counts as a submitted id" is how one of them ends up accepting something
# the other rejects.
SELECTION_FIELD = "patient_ids"


def selected_patient_ids(values):
    """Submitted checkbox values as a clean list of ints, in submitted order.

    Everything arriving from a form is a claim, and a POST can be made without
    ever loading the page. Non-numeric values are dropped rather than raising --
    there is no legitimate way for one to be sent, and the caller's "select at
    least one" message is the right answer to a request that ends up with none.
    """
    cleaned = [str(value).strip() for value in values]
    cleaned = [value for value in cleaned if value.isdigit()]
    return [int(value) for value in dict.fromkeys(cleaned)]


def patient_selection_context(form_data):
    """The ticked records only, for the bulk bar's Export. None if nothing valid.

    WHY THIS FILTERS THE ROSTER RATHER THAN QUERYING FOR THE SELECTION
    -----------------------------------------------------------------
    It reads patient_records_context() -- the same builder Screen 03 rendered
    from and the same one the full-roster export reads -- and keeps the rows
    whose id was ticked. It does not go back to the database with a WHERE id IN
    (...), and that is the point: a second query is a second chance for the
    exported row to disagree with the row the operator was looking at when they
    ticked it. This project's rule is one query per screen, and a selection is
    not a different screen.

    It also inherits the roster's order for free. get_all_patients() returns
    surname order, so the file lists the selection in the same order the table
    did -- not in whatever order the browser happened to submit the boxes, which
    is DOM order today and would silently become click order if the markup ever
    changed.

    WHAT IT REPORTS BACK, AND WHY IT COUNTS TWICE
    ---------------------------------------------
    `requested` is how many ids were submitted; len(`patients`) is how many of
    them the register still holds. Those two are equal in ordinary use and the
    difference is not a filter: archiving a patient does not remove them from the
    roster, so a record cannot drop out of this file by being retired. What can
    make them differ is a submitted id the register has no row for -- a hand-made
    POST, or a page open across a migration that renumbered something. The cover
    sheet states both figures and explains the gap when there is one, because a
    file that quietly holds four rows for a five-record selection is the exact
    failure this project's cover sheets exist to prevent.

    Returns None when nothing usable was submitted, so the route can flash and
    redirect rather than serve an empty workbook.
    """
    ids = selected_patient_ids(form_data.getlist(SELECTION_FIELD))
    if not ids:
        return None

    context = patient_records_context()
    wanted = set(ids)
    selected = [p for p in context["patients"] if p["id"] in wanted]
    if not selected:
        return None

    return {
        "patients": selected,
        "requested": len(ids),
        "total_registered": len(context["patients"]),
    }


def process_archive_patients(form_data):
    """Apply Screen 03's status action. Returns the message to flash.

    Both entry points post the same form to the same endpoint: the row-level
    icon fills in single_patient_id, the bulk bar leaves it empty and relies on
    the checked patient_ids. Either way this resolves to one list of ids and one
    call to set_patient_status(), so the single and bulk cases cannot diverge.

    Everything is re-checked here rather than trusted from the page. The status
    arrives as the value of whichever submit button was pressed, and a POST can
    be made without ever loading the form, so the target is validated against
    PATIENT_STATUSES before it reaches the model -- which would otherwise raise
    on the schema's CHECK constraint.

    The current statuses are re-read too. The dialog only offers transitions that
    are legal for the record it was opened on, but that decision was made from a
    page that may since have gone stale, so "not already on that status" and "all
    on one status" are both settled here against the database rather than against
    what the form claims.
    """
    status = (form_data.get("status") or "").strip()
    if status not in PATIENT_STATUSES:
        return "Choose a status to set: Mark Active, Mark Inactive or Mark Deceased."

    single = (form_data.get("single_patient_id") or "").strip()
    submitted = [single] if single else form_data.getlist(SELECTION_FIELD)

    ids = selected_patient_ids(submitted)
    if not ids:
        return "Select at least one patient record to update."

    current = get_patient_statuses(ids)
    if not current:
        return "Select at least one patient record to update."

    distinct = set(current.values())
    if len(distinct) > 1:
        return MIXED_STATUS_MESSAGE

    current_status = distinct.pop()
    if status == current_status:
        subject = "That record is" if len(current) == 1 else "Those records are"
        return f"No change. {subject} already marked {status}."

    changed = set_patient_status(ids, status)
    noun = "record" if changed == 1 else "records"
    # Reactivation is not archiving, so it does not claim to be. The retention
    # note only belongs on the two statuses that retire a record.
    if status == "Active":
        return f"{changed} patient {noun} reactivated and marked Active."
    return f"{changed} patient {noun} marked {status}. Nothing was deleted."


def patient_profile_context(patient_id):
    """Everything Screen 04 renders, or None if no such patient exists.

    Returning None rather than raising lets each blueprint redirect to its own
    Patient Records URL, which differs per role.
    """
    patient = get_patient_by_id(patient_id)
    if patient is None:
        return None

    # Read for every patient, shown for two cases: the paediatric cohort the DOH
    # schedule applies to, and anyone older who nonetheless has doses on file.
    # The second matters -- a child who ages out of the programme keeps their
    # vaccination history, and a screen that hid it the day they turned five
    # would be hiding a medical record, not tidying a form.
    immunization = get_immunization_status(patient)
    show_immunizations = immunization["applicable"] or bool(immunization["records"])

    # Read unconditionally and for every patient: unlike the EPI schedule there
    # is no cohort this is or is not "applicable" to. A row exists or it does
    # not, and the tab says so either way.
    general_vaccinations = get_general_vaccinations_for_patient(patient_id)

    return {
        "patient": patient,
        "consultations": get_consultations_for_patient(patient_id),
        "appointments": get_appointments_for_patient(patient_id),
        "next_appointment": get_next_appointment_for_patient(patient_id),
        "immunization": immunization,
        "show_immunizations": show_immunizations,
        "doses_by_consultation": _doses_by_consultation(immunization["records"]),
        "general_vaccinations": general_vaccinations,
        # The Immunization Record tab is worth opening if either half has
        # anything in it -- and the tab's badge, which counts outstanding EPI
        # doses, deliberately does not count these: nothing here is outstanding,
        # because nothing here is graded.
        "general_vaccinations_by_consultation": _general_by_consultation(
            general_vaccinations
        ),
    }


def _general_by_consultation(records):
    """{consultation_id: [vaccination, ...]} for the View panel on a history row.

    Built from the list the Immunization tab has already read rather than by
    asking the database again -- exactly what _doses_by_consultation() does for
    the EPI doses, and for the same reason: the records carry their
    consultation_id, so the grouping is free.

    A vaccination recorded against no consultation is skipped here; it belongs to
    no visit, so no visit's panel should claim it. It stays on the Immunization
    tab, which is the record of what the patient has had.
    """
    grouped = {}
    for record in records:
        consultation_id = record.get("consultation_id")
        if not consultation_id:
            continue
        grouped.setdefault(consultation_id, []).append(record)
    return grouped


def _doses_by_consultation(records):
    """{consultation_id: [dose, ...]} for the View panel on each history row.

    Built from the dose list get_immunization_status() has already read for the
    Immunization tab rather than by asking the database again -- the records
    carry their consultation_id, so the grouping is free. A per-row call to
    get_immunizations_for_consultation() would have issued one query per
    consultation to recover rows this context is already holding.

    Doses recorded outside a consultation (consultation_id NULL -- a dose
    entered against a patient directly) are skipped: they belong to no visit, so
    no visit's panel should claim them. They remain visible on the Immunization
    tab, which is the record of what the child has had.
    """
    grouped = {}
    for record in records:
        consultation_id = record.get("consultation_id")
        if not consultation_id:
            continue
        dose = dict(record)
        # The one place a dose is turned into words, so this panel names it
        # exactly as the Immunization tab and the consultation form do.
        dose["label"] = dose_label(record["vaccine_code"], record["dose_number"])
        grouped.setdefault(consultation_id, []).append(dose)
    return grouped


def patient_to_form(patient):
    """Render a stored patient back into the flat dict the form template reads.

    The template already knows how to repopulate itself from a `form` dict --
    that is how a failed registration keeps its values -- so edit mode reuses
    exactly that mechanism rather than introducing a second one.

    The one non-trivial part is the reverse of collect_list_field(): stored
    conditions/allergies are a single JSON array, so anything matching a chip
    goes back to its chip and the remainder goes back to the free-text note.
    """
    def split(stored, chip_options):
        chips = [item for item in stored if item in chip_options]
        remainder = [item for item in stored if item not in chip_options]
        return chips, ", ".join(remainder)

    condition_chips, condition_note = split(patient["medical_conditions_list"], CONDITION_OPTIONS)
    allergy_chips, allergy_note = split(patient["allergies_list"], ALLERGY_OPTIONS)

    form = {
        field: patient.get(field) or ""
        for field in (
            "first_name", "middle_name", "last_name", "birth_date", "sex",
            "civil_status", "blood_type", "address", "municipality", "province",
            "zip_code", "contact_number", "emergency_contact_name",
            "emergency_contact_relationship", "emergency_contact_number",
            "emergency_contact_address",
        )
    }
    form["medical_conditions_selected"] = condition_chips
    form["medical_conditions_note"] = condition_note
    form["allergies_selected"] = allergy_chips
    form["allergies_note"] = allergy_note
    return form


def register_patient_context(form=None, errors=None, duplicates=None,
                             acknowledge_duplicate=False, patient=None,
                             check_in=False, check_in_reason_text="",
                             booking=None):
    """Context for the patient form.

    `patient` set means edit mode: the template switches its wording, shows the
    existing Patient ID instead of the next free one, and posts back to the same
    edit URL. On a GET the form is pre-filled from the record; on a redisplay
    after a failed submit the caller passes the submitted values instead, so the
    operator's edits are never thrown away.

    `check_in` set means the form was opened from the Check In dialog: the
    template says so at the top, renames the save button, and renders the two
    hidden fields that carry the intent to the next submit. It is ignored in edit
    mode -- an existing patient is checked in from the dialog's other path, not
    by re-saving their record.

    `booking` is the same idea for the New Appointment dialog: a dict of already
    validated booking details, rendered as hidden fields so saving the form both
    registers the patient and books the visit. Ignored in edit mode for the same
    reason, and mutually exclusive with `check_in` -- the two come from different
    dialogs and a form cannot have been opened by both.
    """
    if patient is not None and form is None:
        form = patient_to_form(patient)

    booking = dict(booking) if booking and patient is None else None
    check_in = bool(check_in) and patient is None and booking is None

    return {
        "patient": patient,
        "next_patient_id": patient["patient_id"] if patient else generate_next_patient_id(),
        "form": form or {},
        "errors": errors or {},
        "duplicates": duplicates or [],
        # Rendered as a hidden field. Its presence is what turns the next submit
        # of this same form into an acknowledged one.
        "acknowledge_duplicate": acknowledge_duplicate,
        "options": FORM_OPTIONS,
        # Same mechanism, one screen further out: rendered as hidden fields so
        # the check-in intent survives a validation failure or a duplicate
        # acknowledgement instead of being dropped on the first round trip.
        "check_in": check_in,
        "check_in_reason": check_in_reason_text if check_in else "",
        "check_in_flag_field": CHECK_IN_FLAG_FIELD,
        "check_in_reason_field": CHECK_IN_REASON_FIELD,
        "check_in_reason_max": CHECK_IN_REASON_MAX,
        # Save & Register Another's name/value, so the button and the route read
        # the same two strings and cannot drift out of agreement.
        "save_action_field": SAVE_ACTION_FIELD,
        "save_and_register_another": SAVE_AND_REGISTER_ANOTHER,
        # Same mechanism again for the advance-booking path. `booking` is what
        # the notice at the top of the form reads; `booking_hidden` is the
        # name/value pairs that carry it to the next submit.
        "booking": booking,
        "booking_flag_field": BOOKING_FLAG_FIELD,
        "booking_hidden": (
            [(field, booking.get(model_key) or "")
             for field, model_key in BOOKING_FIELDS.items()]
            if booking else []
        ),
    }


def _extract_form(form_data):
    """Pull the submitted values into the shape the model and template share.

    The two list fields are collapsed here because request.form is flat: the
    chips arrive as repeated keys and the free-text note as a separate one.
    """
    values = {
        key: (form_data.get(key) or "").strip()
        for key in (
            "first_name", "middle_name", "last_name", "birth_date", "sex",
            "civil_status", "blood_type", "address", "municipality", "province",
            "zip_code", "contact_number", "emergency_contact_name",
            "emergency_contact_relationship", "emergency_contact_number",
            "emergency_contact_address", "medical_conditions_note", "allergies_note",
        )
    }
    values["medical_conditions"] = collect_list_field(
        form_data.getlist("medical_conditions"), values["medical_conditions_note"]
    )
    values["allergies"] = collect_list_field(
        form_data.getlist("allergies"), values["allergies_note"]
    )
    # Kept separately so the chips can be re-checked when the form redisplays.
    values["medical_conditions_selected"] = form_data.getlist("medical_conditions")
    values["allergies_selected"] = form_data.getlist("allergies")
    return values


def process_register_patient(form_data, patient=None):
    """Validate, then insert a new patient or update an existing one.

    `patient` set means edit mode. Validation is identical either way -- the
    same validate_patient_form() with the same required fields and format rules.
    The duplicate check is skipped entirely when editing: the record is already
    identified, so a name-and-birthdate match against itself (or against a real
    namesake) carries none of the "are these two the same person?" risk the
    warning exists to catch.

    Returns (patient_row_id, context). Exactly one is meaningful: a row id means
    the caller should redirect to that profile, a context means the caller should
    re-render the form.

    The check-in intent -- and the advance-booking intent, which works the same
    way -- is read off the submitted form and threaded back into every context
    this builds, so a first-time patient whose form bounces on a validation error
    or a duplicate warning is still on that path when she finally saves.
    """
    values = _extract_form(form_data)
    # Ignored in edit mode by register_patient_context(); read unconditionally so
    # every branch below can pass the same intent through.
    check_in = check_in_requested(form_data)
    reason = check_in_reason(form_data)
    booking = booking_details(form_data) if booking_requested(form_data) else None

    errors = validate_patient_form(values)
    if errors:
        return None, register_patient_context(
            form=values,
            errors=errors,
            patient=patient,
            # Carry an acknowledgment already given through a later validation
            # failure, so the operator is not warned about the same match twice.
            acknowledge_duplicate=form_data.get("confirm_duplicate") == "yes",
            check_in=check_in,
            check_in_reason_text=reason,
            booking=booking,
        )

    if patient is not None:
        update_patient(patient["id"], values)
        return patient["id"], None

    duplicates = find_possible_duplicates(
        values["first_name"], values["last_name"], values["birth_date"]
    )
    if duplicates and form_data.get("confirm_duplicate") != "yes":
        return None, register_patient_context(
            form=values, duplicates=duplicates, acknowledge_duplicate=True,
            check_in=check_in, check_in_reason_text=reason, booking=booking,
        )

    return create_patient(values), None

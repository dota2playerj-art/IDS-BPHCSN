"""Shared context builders for the Record / Edit Consultation screen.

The consultation form is rendered by two blueprints -- once for the
Administrator and once for Health Center Staff -- from the same template with the
same data and the same validation. The logic lives here so the two role variants
cannot drift apart; the routes stay thin and each keeps its own role_required
guard and its own redirect target.

This mirrors routes/patient_views.py, routes/inventory_views.py and
routes/appointment_views.py exactly.

RECORDING AND EDITING ARE THE SAME FORM
---------------------------------------
One template, one validator, one normaliser, distinguished only by whether a
consultation already exists -- the same arrangement Register Patient and Add/Edit
Medicine already use. What differs between the two is deliberately small and all
of it is here:

* recording is anchored to a queue entry and completes it on save;
* editing writes an audit entry naming what moved, and touches neither the
  patient, the visit date, nor who originally recorded it.


WHAT THE TWO ROLES MAY PUT ON THIS FORM, AND WHY THE SERVER DECIDES IT
-----------------------------------------------------------------------
Diagnosing a patient and deciding their treatment is a licensed act, and the
Administrator account is the licensed clinician. Health Center Staff and BHWs
record the intake -- the complaint, the vitals, the growth measurements -- give
the vaccinations and hand over medicine the doctor has prescribed. They do not
write `diagnosis` or `treatment_plan` (models/consultations.py
DOCTOR_ONLY_FIELDS), and this module is where that stops being a claim.

IT IS ENFORCED IN THREE INDEPENDENT PLACES, AND THE ONE ON THE PAGE IS THE
WEAKEST OF THEM ON PURPOSE:

  1. The template does not render the two fields for a role that may not write
     them -- genuinely absent, not disabled. An input the operator cannot use is
     still an input, and this project's rule is that a control which cannot act
     should not be drawn (utils/unavailable.py). But a page is only ever a
     suggestion: this alone would stop nobody who did not use the page.

  2. _apply_clinical_authority() below strips both fields out of EVERY
     submission by such a role, before validation and before anything is stored.
     Not rejected with an error -- stripped, and on an edit replaced by what the
     record already holds, so a forged POST carrying a diagnosis writes the
     stored value back over itself and moves nothing. The refusal is recorded in
     the audit trail.

  3. The role it asks is utils.security.current_role(), which reads the STORED
     account row. There is no form field, query parameter or header that can
     change the answer, so there is nothing for a tampered request to aim at.

The submitted values never reach models.consultations.store_values() at all,
which is the same shape the growth-field rule already has: allowed_growth_fields()
drops a head circumference submitted for an adult rather than trusting the form
not to offer one. A form not offering a field is not the same as the server
refusing it, and only the second is a permission.
"""
from models.appointments import (
    IN_CONSULTATION,
    complete_consultation,
    get_appointment_by_id,
    get_queue_stats,
    queue_display_name,
)
from models.audit import (
    ACTION_CONSULTATION_RESTRICTED,
    ACTION_CONSULTATION_UNRESTRICTED,
    ACTION_CONSULTATION_UPDATED,
    ACTION_DIAGNOSIS_REFUSED,
    MODULE_CONFIDENTIALITY,
    MODULE_CONSULTATIONS,
    describe_changes,
    log_action,
)
from models.consultations import (
    AUDIT_FORMATTERS,
    CONSULTATION_FIELDS,
    DOCTOR_ONLY_FIELDS,
    FIELD_LABELS,
    INFANT_AGE_YEARS,
    NUMERIC_LIMITS,
    PEDIATRIC_AGE_YEARS,
    RESTRICTED_PLACEHOLDER,
    can_diagnose,
    can_view_restricted,
    consultation_age_context,
    create_consultation,
    get_consultation_by_id,
    get_consultation_for_appointment,
    redact,
    set_consultation_restriction,
    update_consultation,
    validate_consultation_form,
)
from models.dispensing import (
    DISPENSE_MAX_ROWS,
    DISPENSE_START_ROWS,
    ITEM_FIELD_PREFIX,
    QUANTITY_FIELD_PREFIX,
    QUANTITY_RANGE,
    check_dispensing,
    dispensable_items,
    dispensing_label,
    get_dispensing_for_consultation,
    item_field,
    parse_dispensing,
    quantity_field,
    record_dispensing,
)
from models.dispensing import FIELD_LABELS as DISPENSING_LABELS
from models.general_vaccinations import (
    COMMON_VACCINES,
    MAX_NAME_LENGTH,
    OTHER_KEY,
    OTHER_NAME_FIELD,
    VACCINE_FIELD,
    dose_field,
    get_general_vaccinations_for_consultation,
    parse_general_vaccinations,
    record_general_vaccinations,
    vaccination_label,
    vaccines_for_age,
)
from models.general_vaccinations import FIELD_LABELS as GENERAL_VACCINE_LABELS
from models.immunizations import (
    EPI_SCHEDULE,
    IMMUNIZATION_ELSEWHERE_FIELD,
    REPORTED_DATE_LABELS,
    UNKNOWN_DATE_TEXT,
    dose_label,
    get_immunization_status,
    get_immunizations_for_consultation,
    parse_dose_keys,
    parse_reported_doses,
    record_immunizations,
    record_reported_immunizations,
    reported_date_field,
)
from models.patients import get_patient_by_id
from utils.dates import display_date, today
from utils.security import current_role

# The consultation form posts one checkbox per scheduled dose under this name,
# each valued "CODE:DOSE". Named once so the template, the parser and the audit
# description cannot disagree about it.
IMMUNIZATION_FIELD = "immunizations"

# The Administrator's "Restricted" checkbox on this form, and the field the
# Patient Profile's own seal dialog posts. Named here for the reason
# IMMUNIZATION_FIELD is: the template that draws the box, the parser that reads
# it and the audit description that reports it must not be able to disagree about
# what it is called.
RESTRICT_FIELD = "is_restricted"
# The seal dialog on Patient Profile posts which consultation it means and which
# way it is moving the flag. Separate from RESTRICT_FIELD because that one is a
# checkbox whose absence means "not sealed", and this one is an explicit
# direction -- the dialog is opened to do one specific thing and says which.
RESTRICT_CONSULTATION_FIELD = "consultation_id"
RESTRICT_ACTION_FIELD = "restrict_action"
RESTRICT_ON = "restrict"
RESTRICT_OFF = "lift"


def _extract_form(form_data):
    """Pull the submitted values into the shape the model and template share."""
    return {
        field: (form_data.get(field) or "").strip() for field in CONSULTATION_FIELDS
    }


def _apply_clinical_authority(values, stored, role):
    """Remove the doctor-only fields from a submission by a role that may not
    write them. Returns (values, refused) -- `values` is the same dict, mutated.

    `stored` is the consultation as it is on file for an edit, and None for a new
    record. That distinction is the whole of the function's care:

        recording   the two fields are set to None. The record is saved without a
                    diagnosis, which is the honest state of a visit whose intake
                    has been taken and whose clinical judgement has not yet been
                    made. The Administrator adds it later through Edit
                    Consultation.

        editing     the two fields are set back to WHAT THE RECORD ALREADY HOLDS.
                    Not to None -- that is the trap this function exists to
                    avoid. update_consultation() writes every column in
                    CONSULTATION_FIELDS on every save, so a staff member fixing a
                    mistyped temperature on a visit the doctor had already
                    written up would, with the fields merely absent from their
                    submission, have erased the doctor's diagnosis and treatment
                    plan. The restriction is on writing them, not on the record
                    keeping them.

    A field is `refused` only when the submission actually carried something
    DIFFERENT from what is stored. An empty box on a form that did not render it
    is not an attempt at anything, and neither is a stale tab replaying the value
    that is already there -- reporting either as a refusal would fill the audit
    trail with an event nobody caused, and bury the one submission that really
    did try to write a diagnosis it was not entitled to.
    """
    if can_diagnose(role):
        return values, []

    refused = []
    for field in DOCTOR_ONLY_FIELDS:
        submitted = str(values.get(field) or "").strip()
        current = str((stored or {}).get(field) or "").strip()
        if submitted and submitted != current:
            refused.append(field)
        values[field] = (stored or {}).get(field) if stored else None
    return values, refused


def _log_refused_diagnosis(refused, patient, consultation_id, role, user_id,
                           ip_address):
    """Record that a submission tried to write a field its role may not write.

    Nothing is written when nothing was refused, which is the ordinary case for
    every save Health Center Staff makes through the form as it is drawn -- the
    two fields are not on their page, so their submissions do not carry them.

    THE SUBMITTED TEXT IS NOT IN THE ENTRY, AND THAT PROHIBITION IS ABSOLUTE.
    It is the same rule models/audit.py states for a password, and it binds here
    for a reason of its own: the value is an unlicensed guess at what a named
    patient has, and audit_logs is readable by every Administrator and is
    exported whole by routes/audit_export.py. Writing it down would create
    exactly the record the refusal exists to prevent, in the one place in this
    system designed to be read and downloaded. What the entry records is which
    fields were dropped, on whose record, by an account holding which role --
    every fact a reviewer can act on.

    The acting account is audit_logs.user_id and is not repeated in the text, for
    the reason routes/vaccination_correction_views.py gives: a second copy of one
    fact is a thing that can disagree with the first.
    """
    if not refused:
        return None

    names = ", ".join(FIELD_LABELS.get(field, field) for field in refused)
    anchor = (
        f"consultation #{consultation_id}" if consultation_id
        else "a new consultation"
    )
    return log_action(
        user_id=user_id,
        action=ACTION_DIAGNOSIS_REFUSED,
        module=MODULE_CONFIDENTIALITY,
        details=(
            f"A submission for {anchor} for {patient['full_name']} "
            f"({patient['patient_id']}) carried {len(refused)} field"
            f"{'s' if len(refused) != 1 else ''} the submitting account's role "
            f"({role or 'no role'}) may not write — {names}. The value"
            f"{'s were' if len(refused) != 1 else ' was'} discarded before "
            "validation and nothing was stored from "
            f"{'them' if len(refused) != 1 else 'it'}; the rest of the "
            "submission was saved normally. Diagnosis and treatment planning are "
            "restricted to the Administrator, who is the licensed clinician, so "
            "these fields are not rendered for this role at all — a submission "
            "carrying them did not come from the form as it is drawn. The "
            "submitted text is deliberately not recorded here: it is an "
            "unlicensed judgement about a named patient and this trail is "
            "readable and exportable"
        ),
        ip_address=ip_address,
    )


def _log_restriction(outcome, consultation_id, patient, user_id, ip_address,
                     visit_date=None, recorded_by_name=None):
    """Record that a consultation was sealed, or that a seal was lifted.

    `outcome` is set_consultation_restriction()'s own return, so this cannot
    report a seal the database did not take: "unchanged" and "missing" write
    nothing, which is the rule process_edit_consultation() follows -- a save that
    moved nothing is not an event.

    Self-contained, exactly as the consultation edit entry and the vaccination
    correction entry are: read months later, on its own, it must say which record
    was sealed, whose it is, when the visit was and who wrote it up, without
    anyone having to open the record -- which, in this one case, is a reader who
    may not be able to open it at all.

    THE DIAGNOSIS IS NOT IN IT. That prohibition is stated at the two phrases in
    models/audit.py and is the reason this function takes a patient and a date
    rather than the consultation dict: there is nothing here to accidentally
    interpolate. An audit trail that quoted the sealed text would carry the
    privileged information into the one part of this system that is designed to
    be read by every Administrator and downloaded whole.

    A lifting says plainly that the record is legible to every role again. That
    sentence is the point of having a second phrase: it is the fact a reviewer
    asking "was this patient's privileged record ever opened back up" needs, and
    it must not have to be inferred from the absence of a seal.
    """
    if outcome not in ("restricted", "lifted"):
        return None

    visit = f", visit of {display_date(visit_date)}" if visit_date else ""
    author = f", recorded by {recorded_by_name}" if recorded_by_name else ""
    subject = (
        f"Consultation #{consultation_id} for {patient['full_name']} "
        f"({patient['patient_id']}){visit}{author}."
    )

    if outcome == "restricted":
        action = ACTION_CONSULTATION_RESTRICTED
        details = (
            f"{subject} Marked Restricted. Its diagnosis and treatment plan are "
            "now withheld from every role but Administrator, which is the role "
            "licensed to record them; the visit date, chief complaint, vital "
            "signs, immunisations and dispensing on the same record stay legible "
            "to Health Center Staff, who take the intake and hand the medicine "
            "over. Health workers who open this patient's profile are shown a "
            "placeholder naming the restriction rather than an empty field, and "
            "each such view is recorded. The condition itself is deliberately "
            "not named in this entry"
        )
    else:
        action = ACTION_CONSULTATION_UNRESTRICTED
        details = (
            f"{subject} Restriction lifted. Its diagnosis and treatment plan are "
            "legible again to every role that can open the patient's profile, "
            "including Health Center Staff, and views of it are no longer "
            "recorded as withheld. The record is unchanged — nothing about what "
            "the consultation says was edited by this, only who may read it"
        )

    return log_action(
        user_id=user_id,
        action=action,
        module=MODULE_CONFIDENTIALITY,
        details=details,
        ip_address=ip_address,
    )


def _consultation_to_form(consultation):
    """Render a stored consultation back into the flat dict the template reads.

    The template already repopulates itself from a `form` dict -- that is how a
    failed save keeps its values -- so edit mode reuses exactly that mechanism
    rather than introducing a second one.
    """
    values = {}
    for field in CONSULTATION_FIELDS:
        value = consultation.get(field)
        if value is None:
            values[field] = ""
        elif isinstance(value, float):
            # 37.2 not 37.20, and 12 not 12.0 -- the form should show what was
            # typed, not the storage format.
            values[field] = f"{value:g}"
        else:
            values[field] = str(value)
    return values


def _immunization_context(patient, consultation, visit_date, ticked=None,
                          reported_submitted=None):
    """The "Immunizations Given Today" section's state for this visit.

    Every scheduled dose is offered, not only the ones outstanding, because a
    health worker catching a child up needs to see the whole schedule to know
    where they are in it. What differs per dose is whether it can still be
    ticked:

        already on file        locked, with where it came from and when
        not yet given          free to tick, badged Due / Overdue / Upcoming

    A dose that is free to tick can be ticked two different ways, and the second
    one is why this feature exists. "Given today" records a dose this health
    center has just administered. "Previously given elsewhere" records a dose the
    parent has told the health worker about -- given at another hospital or in
    another barangay -- which is a fact learned at this consultation and stored
    against it, but is emphatically not this health center's own work. The child
    stops showing Overdue either way; only the second one is honest about a dose
    the health center did not give, and before it existed the only way to clear a
    false Overdue was to claim the dose as this health center's own.

    ANY recorded dose is locked -- including one this very consultation recorded.
    It used to be that a dose given at this visit stayed an ordinary ticked
    checkbox, so unticking it deleted the immunisation record. That made the
    absence of a checkbox mean "destroy this dose", and an HTML checkbox is
    absent from a submission for many reasons that have nothing to do with
    intent: a partial or programmatic POST, a serialiser that drops unchecked
    inputs, a form rebuilt by script. A clinical record that a child was
    vaccinated is not something a missing form field should be able to erase.

    Locking it reuses exactly the treatment a dose from another visit already
    had, for the same stated reason -- the form cannot be used to rewrite a
    vaccination that has already happened. The consequence is that this form is
    add-only for immunisations: see _apply_immunization_edit().

    `ticked` and `reported_submitted` carry the operator's selection back through
    a validation bounce, so a rejected save does not throw away which boxes they
    had checked or the date they had typed against one of them.
    """
    status = get_immunization_status(patient, on_date=visit_date)
    this_visit = {
        (dose["vaccine_code"], dose["dose_number"])
        for dose in get_immunizations_for_consultation(
            consultation["id"] if consultation else None
        )
    }
    reported_ticked = set((reported_submitted or {}).get("ticked", ()))
    reported_dates = (reported_submitted or {}).get("dates", {})

    for item in status["schedule"]:
        pair = (item["code"], item["dose_number"])
        # Kept so the template can say *which* visit recorded it, which is still
        # a different sentence even though both states are now locked.
        item["given_here"] = pair in this_visit
        item["locked"] = item["given"]
        if ticked is None:
            item["checked"] = item["given_here"]
        else:
            item["checked"] = item["key"] in ticked
        # Never pre-ticked from the record. A dose already reported is locked
        # like any other dose on file, so this box only ever comes back ticked
        # because the operator ticked it on the submission that bounced.
        item["reported_checked"] = item["key"] in reported_ticked
        item["reported_date_value"] = reported_dates.get(item["key"], "")
    return status


def _general_vaccination_context(consultation, submitted=None, age_context=None):
    """The "Other Vaccinations Given" section's state for this visit.

    Deliberately much thinner than _immunization_context(). That one has to
    resolve a whole national schedule against a child's birthday and grade every
    dose in it; this one has no schedule to resolve, so it offers a short list of
    tick boxes, a free-text row for anything not on it, and the rows already
    recorded at this visit shown as fact.

    Already-recorded rows are LOCKED, exactly as a recorded EPI dose is, and for
    the reason models/immunizations.py gives: an absent checkbox is not evidence
    that a vaccination never happened. A partial POST, a script-rebuilt form or a
    serialiser that drops unchecked inputs all produce one, and none of them mean
    "erase this". So this section, like the EPI section, is add-only -- a
    vaccination that happened, happened.

    `submitted` carries the operator's selection back through a validation
    bounce, so a rejected save does not throw away what they had ticked or typed.

    `age_context` decides which tick boxes get printed, and only that. The
    section itself is still shown at every age -- that is the whole point of it,
    and a rabies course given to a bitten infant is the case that settled it.
    What the age changes is the length of the list: for a patient under one,
    models.general_vaccinations.vaccines_for_age() drops the rows that age cannot
    be given, so a health worker writing up a four-month-old is not reading past
    a Td booster and a senior's pneumococcal dose to reach the row they want. The
    free-text row is printed at every age and is never dropped, so the shorter
    list is a shorter list of prompts and not a shorter list of possibilities.

    Omitted (None) means the whole list, which is what every caller outside the
    consultation form wants and what an unaged patient gets.
    """
    recorded = get_general_vaccinations_for_consultation(
        consultation["id"] if consultation else None
    )
    ticked = set(submitted.get("ticked", ())) if submitted else set()
    doses = submitted.get("doses", {}) if submitted else {}

    rows = [
        {
            "key": key,
            "name": name,
            "protects": protects,
            "dose_field": dose_field(key),
            "checked": key in ticked,
            "dose_value": doses.get(key, ""),
        }
        for key, name, protects in vaccines_for_age(
            bool(age_context and age_context.get("is_infant"))
        )
    ]
    rows.append({
        "key": OTHER_KEY,
        "name": "Other vaccine",
        "protects": "Anything not listed above — name it on the right",
        "dose_field": dose_field(OTHER_KEY),
        "checked": OTHER_KEY in ticked,
        "dose_value": doses.get(OTHER_KEY, ""),
        "is_other": True,
    })

    return {
        "rows": rows,
        "recorded": recorded,
        "vaccine_field": VACCINE_FIELD,
        "other_name_field": OTHER_NAME_FIELD,
        "other_name_value": (submitted or {}).get("other_name", ""),
        "max_name_length": MAX_NAME_LENGTH,
    }


def _dispensing_context(consultation, submitted=None):
    """The "Items Dispensed" section's state for this visit.

    Thinner again than the two vaccination sections above it, because there is no
    list to offer and no schedule to resolve: the choices are whatever is
    actually on the shelf today, which models.dispensing.dispensable_items()
    decides from the live inventory. What the section adds instead is a stock
    figure beside every option, so the operator sees the ceiling before they hit
    it rather than after.

    Rows already dispensed at this visit are shown as LOCKED FACT, for the reason
    the immunisation and vaccination sections give and one more of its own. The
    shared reason: an absent form field is not evidence that something never
    happened, and a partial or script-rebuilt POST produces one. The extra reason
    here: un-recording a dispensing would have to put units back on the shelf, and
    a stock increase with no supplier, no batch and no expiry date behind it is
    not a restock -- it is a hole in the inventory that looks like one. So this
    section is add-only too, and models/dispensing.py contains no DELETE at all.

    `submitted` carries the operator's lines back through a validation bounce, so
    a rejected save does not throw away what they had chosen and typed.
    """
    recorded = get_dispensing_for_consultation(
        consultation["id"] if consultation else None
    )
    values = submitted or {}
    low, high = QUANTITY_RANGE

    return {
        "options": dispensable_items(),
        "rows": [
            {
                "index": index,
                "item_field": item_field(index),
                "quantity_field": quantity_field(index),
                "item_value": values.get(item_field(index), ""),
                "quantity_value": values.get(quantity_field(index), ""),
            }
            for index in range(_dispensing_row_count(values))
        ],
        "recorded": recorded,
        "start_rows": DISPENSE_START_ROWS,
        "max_rows": DISPENSE_MAX_ROWS,
        # The two halves of a line's field names, for the script that adds a
        # line after the page has rendered. Handed over rather than spelled out
        # in the template, so the name the browser posts and the name
        # parse_dispensing() reads have one definition -- item_field() -- and
        # cannot drift apart.
        "item_prefix": ITEM_FIELD_PREFIX,
        "quantity_prefix": QUANTITY_FIELD_PREFIX,
        "min_quantity": low,
        "max_quantity": high,
    }


def _dispensing_row_count(values):
    """How many item lines to render: the starting number, or more.

    A fresh form gets DISPENSE_START_ROWS and the operator adds the rest with the
    button. A bounced one has to come back with every line they had asked for,
    including the ones the button created -- rendering only the first two would
    silently drop the third item from a form the operator is being told to
    correct, which is the one moment they are least likely to notice it missing.

    Counted from the highest index carrying anything at all, so a line that was
    half-filled (and is therefore holding an error message of its own) survives
    the bounce alongside the complete ones.
    """
    highest = -1
    for index in range(DISPENSE_MAX_ROWS):
        if values.get(item_field(index)) or values.get(quantity_field(index)):
            highest = index
    return max(DISPENSE_START_ROWS, highest + 1)


def _submitted_dispensing(form_data):
    """What the operator had chosen and typed, for replay through a bounce."""
    values = {}
    for index in range(DISPENSE_MAX_ROWS):
        for field in (item_field(index), quantity_field(index)):
            values[field] = (form_data.get(field) or "").strip()
    return values


def _dispensing_labels(records):
    """['Paracetamol — 20 tablets'] for a list of stored dispensing rows."""
    return [dispensing_label(record) for record in records]


def _submitted_general_vaccinations(form_data):
    """What the operator had ticked and typed, for replay through a bounce."""
    return {
        "ticked": (form_data.getlist(VACCINE_FIELD)
                   if hasattr(form_data, "getlist") else []),
        "other_name": (form_data.get(OTHER_NAME_FIELD) or "").strip(),
        "doses": {
            key: (form_data.get(dose_field(key)) or "").strip()
            for key in [row[0] for row in COMMON_VACCINES] + [OTHER_KEY]
        },
    }


def _submitted_reported_doses(form_data):
    """The "previously given elsewhere" ticks and dates, for replay through a bounce.

    Built the same way _submitted_general_vaccinations() above is, and for the
    same reason: a form that bounces on one bad date must come back holding every
    other box the operator ticked. A dose reported at the counter is something
    the parent said out loud once, and losing it to a validation error means
    asking them to say it again.

    Every scheduled row's date box is read, not only the ticked ones, so a date
    typed against a row whose box was missed comes back with the date still in
    it -- which is what makes parse_reported_doses()'s "tick the box or clear the
    date" refusal something the operator can act on rather than a message about a
    field that has been emptied.
    """
    return {
        "ticked": (form_data.getlist(IMMUNIZATION_ELSEWHERE_FIELD)
                   if hasattr(form_data, "getlist") else []),
        "dates": {
            f"{row[0]}:{row[3]}": (
                form_data.get(reported_date_field(f"{row[0]}:{row[3]}")) or ""
            ).strip()
            for row in EPI_SCHEDULE
        },
    }


def consultation_form_context(patient, appointment=None, consultation=None,
                              form=None, errors=None, ticked=None,
                              general_submitted=None, dispensing_submitted=None,
                              restrict_submitted=None, reported_submitted=None):
    """Everything the Record / Edit Consultation screen renders.

    `consultation` set means edit mode: the template switches its wording, shows
    the original visit date and author as read-only fact, and posts back to the
    edit URL.

    The age context is computed against the consultation's own date in edit mode
    and against today for a new record, so which growth fields appear is decided
    by how old the patient was at the visit -- not by how old they are now. The
    immunisation schedule is resolved against that same date for the same reason.

    THE ROLE IS READ HERE RATHER THAN PASSED IN, and read from the signed-in
    account. Both blueprints render this screen through this one function, so a
    role handed in as an argument would be a value each of them could get wrong
    independently; utils.security.current_role() reads the stored account row and
    cannot be reached by anything the request carried.

    Two things follow from the answer and both are done before the template is
    given anything. The doctor-only fields are dropped from `form`, so they are
    not in the render context and therefore not in the page -- the template also
    declines to draw them, but this is what makes their absence a fact about the
    response rather than a fact about the markup. And a sealed consultation is
    redacted, for the case an Edit URL is opened directly on one.
    """
    visit_date = consultation["consultation_date"] if consultation else today()
    age_context = consultation_age_context(patient, on_date=visit_date)

    role = current_role()
    may_diagnose = can_diagnose(role)

    if form is None:
        form = _consultation_to_form(consultation) if consultation else {}

    if not may_diagnose:
        # Off the form dict entirely rather than blanked, so there is no key for
        # a template expression to reach even by accident. `form` is rebuilt
        # rather than mutated: on a validation bounce it is the caller's dict.
        form = {
            field: value for field, value in form.items()
            if field not in DOCTOR_ONLY_FIELDS
        }
        # An error against a field this role cannot see would print in the
        # summary at the top of the page with nowhere to go -- and it cannot
        # arise anyway, since the validator stops requiring these two and the
        # values are stripped before it runs. Dropped for the same reason the
        # fields are: nothing on this page should mention them to this role.
        errors = {
            field: message for field, message in (errors or {}).items()
            if field not in DOCTOR_ONLY_FIELDS
        }
        # The stored record still goes to the template -- it draws the visit
        # date, the original author and the edited banner from it -- so a sealed
        # one is redacted before it gets there.
        if consultation is not None:
            consultation = redact(consultation, can_view_restricted(role))

    return {
        "patient": patient,
        "appointment": appointment,
        "consultation": consultation,
        "form": form,
        # Whether to draw the Assessment & Plan fields at all, and whether to
        # offer the Restricted checkbox beside them. The template asks this and
        # nothing else about roles -- it does not compare role strings, so it
        # cannot come to disagree with the server about who may diagnose.
        "can_diagnose": may_diagnose,
        "restrict_field": RESTRICT_FIELD,
        # Ticked from what was submitted when a save bounced, and otherwise from
        # the stored record -- so a rejected form comes back still holding the
        # seal the clinician had just ticked, rather than quietly losing it and
        # saving the record unsealed on the second attempt.
        "restrict_checked": (
            bool(restrict_submitted) if restrict_submitted is not None
            else bool((consultation or {}).get("is_restricted"))
        ),
        "restricted_placeholder": RESTRICTED_PLACEHOLDER,
        "errors": errors or {},
        "age_context": age_context,
        "visit_date": visit_date,
        # Merged rather than reaching into models.consultations.FIELD_LABELS:
        # the error summary prints field_labels.get(field, field) and would
        # otherwise show a raw field name for a general-vaccination error. The
        # consultation's own label map is left exactly as it was, so the audit
        # trail still describes only the fields it describes.
        "field_labels": dict(FIELD_LABELS, **GENERAL_VACCINE_LABELS,
                             **DISPENSING_LABELS, **REPORTED_DATE_LABELS),
        # (field, label, unit, low, high, whole) -- the form prints the unit in
        # each field's hint and the range in its out-of-range message, from the
        # same tuples the validator checks against.
        "numeric_limits": NUMERIC_LIMITS,
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "infant_age_years": INFANT_AGE_YEARS,
        # Only computed for the cohort the schedule applies to; the template
        # renders the section inside the same is_pediatric guard.
        "immunization": (
            _immunization_context(patient, consultation, visit_date, ticked,
                                  reported_submitted)
            if age_context["is_pediatric"] else None
        ),
        "immunization_field": IMMUNIZATION_FIELD,
        # The second column of tick boxes in that section: the dose the child
        # already had somewhere else. Named to the template from here rather than
        # spelled in the markup, exactly as the field above it is.
        "immunization_elsewhere_field": IMMUNIZATION_ELSEWHERE_FIELD,
        "unknown_date_text": UNKNOWN_DATE_TEXT,
        # Offered for every patient, with no age guard at all -- that is the
        # whole point of the section. An adult receiving a hepatitis B dose had
        # nowhere to be recorded before it existed, and a child can have both
        # this and their EPI doses at the same visit.
        "general_vaccination": _general_vaccination_context(
            consultation, general_submitted, age_context
        ),
        # Offered for every patient at every age, like the section above and
        # unlike the EPI one -- there is no cohort a medicine belongs to. What
        # narrows this section is the shelf, not the patient: the options are the
        # in-service, unexpired, in-stock medicines and nothing else.
        "dispensing": _dispensing_context(consultation, dispensing_submitted),
    }


def record_consultation_context(appointment_id):
    """Context for writing up one queue entry, or (None, message) if it cannot be.

    Returns (context, error_message). Exactly one is meaningful.

    A consultation is recorded for the patient who is with the clinician now, so
    this refuses anything else: the queue's In Consultation row is the one visit
    being written up, and offering the form for a patient still in the waiting
    room would produce a record of something that has not happened.
    """
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return None, "That queue entry could not be found."

    name = queue_display_name(appointment)

    existing = get_consultation_for_appointment(appointment_id)
    if existing:
        return None, (
            f"{name}'s visit has already been written up. Open it from their "
            "profile's Consultation History to make changes."
        )

    if appointment["status"] != IN_CONSULTATION:
        return None, (
            f"{name} is marked {appointment['status']}, not In Consultation. "
            "Start the consultation from the queue before recording it."
        )

    patient = get_patient_by_id(appointment["patient_id"])
    if patient is None:
        return None, "That patient record could not be found."

    return consultation_form_context(patient, appointment=appointment), None


def edit_consultation_context(consultation_id):
    """Context for editing a saved consultation, or (None, message)."""
    consultation = get_consultation_by_id(consultation_id)
    if consultation is None:
        return None, "That consultation record could not be found."

    patient = get_patient_by_id(consultation["patient_id"])
    if patient is None:
        return None, "That patient record could not be found."

    return consultation_form_context(patient, consultation=consultation), None


def _submitted_restriction(form_data):
    """Whether the Restricted box came back ticked. An HTML checkbox posts its
    name only when it is checked, so absence is False -- which is the right
    reading here and is why this is a plain presence test rather than a value
    comparison."""
    return bool(form_data.get(RESTRICT_FIELD))


def process_record_consultation(appointment_id, form_data, user_id,
                                ip_address=None):
    """Save a new consultation and close its queue entry.

    Returns (patient_id, context, message). A patient_id means the caller should
    redirect to that profile; a context means re-render the form; the message is
    flashed either way.

    Everything the form claims about the visit is re-established here rather than
    trusted: the queue entry is re-read, its status re-checked, and the patient's
    age recomputed. A POST can arrive without the page ever having been loaded,
    and the page it was loaded from may since have gone stale.
    """
    context, message = record_consultation_context(appointment_id)
    if context is None:
        return None, None, message

    patient = context["patient"]
    appointment = context["appointment"]
    age_context = context["age_context"]

    role = current_role()
    may_diagnose = can_diagnose(role)

    values = _extract_form(form_data)
    # THE DIAGNOSIS AND TREATMENT PLAN, IF THIS ROLE MAY NOT WRITE THEM, ARE GONE
    # FROM `values` BY THE NEXT LINE. Stripped before validation and before
    # anything is stored -- exactly the shape of the growth-field rule below it,
    # and for the same stated reason: the form not offering a field is not the
    # same as the server refusing it. `stored` is None because this is a new
    # record, so both fields go in NULL and the Administrator writes them later.
    values, refused = _apply_clinical_authority(values, None, role)
    # The schedule only applies to the paediatric cohort, so doses submitted for
    # anyone else are dropped here rather than stored -- the same second refusal
    # store_values() gives the growth measurements, and for the same reason: the
    # form not offering a field is not the same as the server refusing it.
    ticked = form_data.getlist(IMMUNIZATION_FIELD) if age_context["is_pediatric"] else []
    dose_keys = parse_dose_keys(ticked)

    # The doses reported at this visit as already given somewhere else. Behind
    # the same age gate and dropped by the same rule, because they are graded
    # against the same schedule: the reading a reported dose changes is the EPI
    # schedule's Overdue, and outside the under-five cohort there is no such
    # reading to change. `given_today` is handed in so a dose ticked in both
    # columns is refused rather than silently resolved -- see
    # models.immunizations.parse_reported_doses().
    reported_entries, reported_errors = (
        parse_reported_doses(form_data, patient, context["visit_date"], dose_keys)
        if age_context["is_pediatric"] else ([], {})
    )
    reported_submitted = _submitted_reported_doses(form_data)

    # No age guard here, deliberately: a general vaccination is a record that a
    # vaccine was given, which is true of a patient of any age. The EPI doses
    # above are gated because the schedule they are graded against only covers
    # the under-five cohort; there is no schedule here to be outside of.
    general_entries, general_errors = parse_general_vaccinations(form_data)
    general_submitted = _submitted_general_vaccinations(form_data)

    # No age guard here either. What limits dispensing is the shelf, not the
    # patient. The two hard blocks -- insufficient stock and expired medicine --
    # are asked *before* the consultation is written, so a refusal comes back as
    # a form with the reason under the line rather than as a saved record with a
    # failure notice attached to it. models/dispensing.py asks them again inside
    # the write transaction, and that is the pair that actually governs.
    dispense_entries, dispense_errors = parse_dispensing(form_data)
    dispense_submitted = _submitted_dispensing(form_data)
    if not dispense_errors:
        dispense_errors = check_dispensing(dispense_entries)

    restrict = _submitted_restriction(form_data) and may_diagnose

    errors = validate_consultation_form(
        values, age_context, require_diagnosis=may_diagnose
    )
    errors.update(general_errors)
    errors.update(reported_errors)
    errors.update(dispense_errors)
    if errors:
        return None, consultation_form_context(
            patient, appointment=appointment, form=values, errors=errors,
            ticked=set(ticked), general_submitted=general_submitted,
            dispensing_submitted=dispense_submitted,
            restrict_submitted=restrict,
            reported_submitted=reported_submitted,
        ), (
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} "
            f"need{'s' if len(errors) == 1 else ''} attention. "
            "Nothing has been saved yet."
        )

    consultation_id = create_consultation(
        patient_id=patient["id"],
        recorded_by=user_id,
        values=values,
        age_context=age_context,
        appointment_id=appointment["id"],
    )

    # Written after the record exists, because the refusal entry names the
    # consultation it was aimed at and there was no id to name until now. Nothing
    # is written on the ordinary path: the two fields are not on this role's page,
    # so an honest submission from it does not carry them.
    _log_refused_diagnosis(
        refused, patient, consultation_id, role, user_id, ip_address
    )

    # The seal, if the clinician ticked it while writing the record up. Applied
    # here rather than as a column on the INSERT so that one function owns every
    # change to this flag -- the three columns are written together, the audit
    # entry has one shape, and there is no second path that could set the flag
    # without stamping who did it. `restrict` is already False for any role that
    # may not diagnose, so this is unreachable for them twice over.
    if restrict:
        outcome = set_consultation_restriction(consultation_id, True, user_id)
        if outcome == "restricted":
            _log_restriction(
                outcome, consultation_id, patient, user_id, ip_address,
                visit_date=context["visit_date"], recorded_by_name=None,
            )

    # Dated to the visit, not to now: a consultation written up is a record of
    # that day, and the dose was given during it.
    given = record_immunizations(
        patient_id=patient["id"],
        dose_keys=dose_keys,
        administered_by=user_id,
        date_administered=context["visit_date"],
        consultation_id=consultation_id,
    )

    # The doses the parent reported at this visit as already given elsewhere.
    # Same table, same consultation anchor -- and deliberately NOT the visit
    # date: each carries the date it was reportedly given, or none at all where
    # nobody knows it. That is the difference between the two calls and the
    # reason there are two. Writing these through record_immunizations() with the
    # visit date would file another facility's work as this one's, on today, in
    # this operator's name, which is the defect the whole feature exists to end.
    reported = record_reported_immunizations(
        patient_id=patient["id"],
        entries=reported_entries,
        recorded_by=user_id,
        consultation_id=consultation_id,
    )

    # Same visit date, same author, same consultation anchor -- a separate table,
    # not a separate event. A child can receive both at one visit and both are
    # written here.
    general_given = record_general_vaccinations(
        patient_id=patient["id"],
        entries=general_entries,
        administered_by=user_id,
        date_administered=context["visit_date"],
        consultation_id=consultation_id,
    )

    # Same visit date, same author, same consultation anchor as the two
    # vaccination writes above -- and, unlike them, this one also moves the
    # shelf. Each row inserted here decrements its medicine's stock_quantity in
    # the same transaction, so Medicine Inventory, both dashboards' low-stock
    # cards and the sidebar badge all reflect the issue on their next render
    # without any of them being touched by this feature.
    dispensed, dispense_failures = record_dispensing(
        patient_id=patient["id"],
        entries=dispense_entries,
        dispensed_by=user_id,
        date_dispensed=context["visit_date"],
        consultation_id=consultation_id,
    )

    # Reuses the queue's own transition rather than writing 'Completed' here, so
    # the one-patient-at-a-time invariant and the "only the visit in progress may
    # be completed" guard both still apply -- and completing frees the clinician
    # for whoever is next exactly as it does from the queue screen.
    outcome = complete_consultation(appointment["id"])

    message = (
        f"Consultation recorded for {patient['full_name']} "
        f"({patient['patient_id']})."
    )
    if restrict:
        # Said at the moment it takes effect, and said in terms of consequence
        # rather than of the flag: "Marked Restricted" alone would leave the
        # clinician to work out what that does to everyone else's screen.
        message += (
            " Marked Restricted — its diagnosis and treatment plan are withheld "
            "from Health Center Staff, who still see the visit, the vitals and "
            "what was dispensed."
        )
    if given:
        message += (
            f" {len(given)} immunisation{'s' if len(given) != 1 else ''} recorded: "
            + ", ".join(dose_label(code, dose) for code, dose in given) + "."
        )
    if reported:
        # Worded as what the record now says rather than as what was ticked. The
        # operator needs to be able to read this line back and see that the
        # health center has not claimed the dose -- so it says "reported as given
        # elsewhere", and it says which of them went in without a date, because
        # that is the part they may still be able to fill in from a card in the
        # parent's bag before the family leaves.
        message += (
            " {} dose{} recorded as previously given elsewhere: ".format(
                len(reported), "s" if len(reported) != 1 else "")
            + ", ".join(_reported_labels(reported)) + "."
        )
    if given or reported:
        # Say what is still outstanding while the parent is still in the room --
        # a catch-up visit is the moment that information is worth anything. Read
        # after both writes, so a dose just reported from elsewhere has already
        # stopped counting as outstanding by the time this sentence is composed.
        after_doses = get_immunization_status(patient, on_date=context["visit_date"])
        if after_doses["attention_items"]:
            message += (
                " Still "
                + ", ".join(
                    f"{item['label']} ({item['status'].lower()})"
                    for item in after_doses["attention_items"][:3]
                )
                + "."
            )
    if general_given:
        message += (
            " {} other vaccination{} recorded: ".format(
                len(general_given), "s" if len(general_given) != 1 else "")
            + ", ".join(_general_labels(general_given)) + "."
        )
    message += _dispensing_message(dispensed, dispense_failures)

    if outcome == "completed":
        stats = get_queue_stats()
        message += " Their visit is now marked Completed."
        if stats["next_up_name"]:
            message += (
                f" {stats['next_up_name']} is next and can be started now."
            )
        else:
            message += " Nobody else is waiting."
    else:
        # The record is saved either way -- it is the clinical fact. Say plainly
        # that the queue did not move rather than implying the whole save failed.
        message += (
            " The record was saved, but their queue entry could not be marked "
            f"Completed ({outcome}) — check the queue."
        )

    return patient["id"], None, message


def _dispensing_message(dispensed, failures):
    """What to add to the save's flash message about what was dispensed.

    Two things it deliberately says that a bare count would not.

    The stock left behind, per item. A health worker who has just taken the last
    twelve tablets off a shelf should be told so at the moment they do it,
    while the patient is still in the room and while restocking is still a
    decision somebody can make today -- not on the next render of a dashboard
    they may not open. The figure is the one record_dispensing() wrote, read back
    off its own return rather than re-queried, so the sentence cannot report a
    level the shelf does not hold.

    And a refusal that arrived too late to bounce the form. check_dispensing()
    runs before the consultation is written, so this is only reachable when the
    shelf moved between that check and the save -- another dispensing committing
    in between. The consultation is saved either way, because it is the clinical
    fact and it happened; what did not happen is the stock leaving the store, and
    saying so plainly is the only honest option. Quietly dropping it would leave a
    record of a visit whose prescription vanished.
    """
    if failures:
        return (
            " The consultation was saved, but nothing was dispensed: "
            + " ".join(failures.values())
            + " Stock has not been changed — record it from the patient's "
            "consultation history once the shelf is right."
        )
    if not dispensed:
        return ""

    given = ", ".join(_dispensing_labels(dispensed))
    remaining = ", ".join(
        "{} now {}".format(row["medicine_name"], row["stock_after"])
        for row in dispensed
    )
    return (
        " {} item{} dispensed: {}. Stock updated — {}.".format(
            len(dispensed), "s" if len(dispensed) != 1 else "", given, remaining
        )
    )


def _apply_immunization_edit(patient, consultation_id, consultation, ticked,
                             user_id, age_context, reported_entries=None):
    """Record any newly ticked doses for this visit. Add-only.

    Returns (added, removed, reported). `added` and `removed` are lists of
    (code, dose_number); `reported` is the (code, dose_number, date) triples
    record_reported_immunizations() stored. `removed` is always empty and is kept
    in the signature because the audit line, the flash message and the caller all
    read it; the day a deliberate correction path exists it is what that path
    will report through.

    WHY THIS NO LONGER REMOVES ANYTHING
    -----------------------------------
    It used to delete every dose this consultation had recorded whose checkbox
    did not come back ticked. That made an absent form field mean "erase this
    child's vaccination record", which is the one thing this module's own header
    says must not happen -- "a vaccination that happened, happened". The absence
    of a checkbox is not evidence of intent: a partial POST, a script-rebuilt
    form or a serialiser that drops unchecked inputs all produce it, and each
    silently destroyed a dose whose only remaining trace was an audit line.

    Removal is not merely gated here, it is absent. A confirm-and-delete control
    on this form would still leave deletion reachable from a routine correction
    screen -- the same screen a health worker opens to fix a typo in a treatment
    plan -- and this project already puts its genuinely destructive action
    (changing a patient's status) behind a dedicated modal and its own endpoint
    rather than inside a general edit form. Un-recording a dose given in error is
    rarer and more consequential than an archive, so it belongs on a deliberate
    correction path of its own, not as a side effect of saving this page.

    models.immunizations.remove_immunizations() is deliberately left in place,
    unused, for that path to call: it already scopes its DELETE to the
    consultation that recorded the dose, which is the hard part.

    Adding is unchanged. Only doses not already on file anywhere are candidates,
    so saving an edit still cannot re-date somebody else's vaccination.

    A dose reported as previously given elsewhere is added the same way and under
    the same rules -- add-only, never re-dating what is already on file -- and
    comes back as the third element of the return so the audit line can name it
    separately. It has to be named separately: "immunisations added: BCG" would
    describe a dose this health center gave, and the point of the whole feature
    is that the record never says that about a dose it did not give.
    """
    if not age_context["is_pediatric"]:
        return [], [], []

    current = {
        (dose["vaccine_code"], dose["dose_number"])
        for dose in get_immunizations_for_consultation(consultation_id)
    }

    added = record_immunizations(
        patient_id=patient["id"],
        dose_keys=[pair for pair in parse_dose_keys(ticked) if pair not in current],
        administered_by=user_id,
        date_administered=consultation["consultation_date"],
        consultation_id=consultation_id,
    )
    reported = record_reported_immunizations(
        patient_id=patient["id"],
        entries=[entry for entry in (reported_entries or [])
                 if (entry["code"], entry["dose_number"]) not in current],
        recorded_by=user_id,
        consultation_id=consultation_id,
    )
    return added, [], reported


def _general_labels(entries):
    """['Hepatitis B', 'Rabies dose 3'] for a list of stored entries."""
    return [vaccination_label(entry["vaccine_name"], entry["dose_number"])
            for entry in entries]


def _reported_labels(stored):
    """['BCG (Mar 04, 2026)', 'OPV dose 1 (date not known)'] for reported doses.

    `stored` is what record_reported_immunizations() returns: (code, dose, date)
    triples, the date being None where nobody knew it.

    The date is printed inside the label rather than left off, and an absent one
    is named rather than skipped. A flash message listing "BCG, OPV dose 1" would
    read identically whether both dates were captured or neither was, and the
    whole point of the entry is that the record says exactly as much as is
    actually known about each dose.
    """
    return [
        "{} ({})".format(
            dose_label(code, dose),
            display_date(day) if day else UNKNOWN_DATE_TEXT.lower(),
        )
        for code, dose, day in stored
    ]


def _apply_general_vaccination_edit(patient, consultation_id, consultation,
                                    entries, user_id):
    """Record any newly ticked general vaccinations for this visit. Add-only.

    Returns the entries actually stored.

    Add-only for exactly the reason _apply_immunization_edit() is: a vaccination
    on file is a record that the patient was vaccinated, and the absence of a
    checkbox in a submission is not evidence that it never happened. Rows already
    recorded against this visit are rendered as locked fact rather than as
    checkboxes, so no submission -- however it was produced -- can remove one.

    There is no removal function in models/general_vaccinations.py at all, which
    is a step further than the EPI module goes: that one keeps
    remove_immunizations() in place, unused, for the deliberate correction path
    that would one day call it. Nothing here needs a head start on a path that
    does not exist yet, and an unused DELETE is a thing that can be called by
    mistake.

    Rows whose vaccine and date already match something on file are absorbed by
    the table's UNIQUE constraint rather than duplicated, so re-saving an edit
    without changing this section adds nothing and reports nothing changed.
    """
    return record_general_vaccinations(
        patient_id=patient["id"],
        entries=entries,
        administered_by=user_id,
        date_administered=consultation["consultation_date"],
        consultation_id=consultation_id,
    )


def _describe_dose_changes(added, removed, general_added=(), dispensed=(),
                           reported=()):
    """The vaccination and dispensing half of an audit line.

    Returns (summary, changed_labels).

    Named in full rather than counted -- "2 immunisations changed" would tell a
    later reader nothing about which child got what, which is the whole reason
    the entry exists.

    EPI doses, other vaccinations and dispensed medicine are reported as separate
    phrases rather than pooled into one count, so an entry read months later still
    says which kind of record moved -- a scheduled infant dose, an adult booster
    and twenty tablets off a shelf are not interchangeable facts.

    A dose reported as previously given elsewhere gets a fourth phrase of its
    own, for the same reason and more sharply. Folded into "Immunisations added"
    it would put a permanent, uneditable claim in the audit trail that this
    health center administered a dose it never touched -- and the audit trail is
    the one record in the project that cannot later be put right.

    Dispensing earns its place in the audit trail more plainly than either
    vaccination does: it is the only edit reachable from this form that changes a
    figure on a *different* screen. Twenty tablets recorded here leave Medicine
    Inventory twenty lighter, and a stock movement that no entry names is exactly
    the kind of change an audit log exists to make answerable.
    """
    parts, changed = [], []
    if added:
        parts.append(
            "Immunisations added: "
            + ", ".join(dose_label(code, dose) for code, dose in added)
        )
        changed.append("immunisations added")
    if removed:
        parts.append(
            "Immunisations removed: "
            + ", ".join(dose_label(code, dose) for code, dose in removed)
        )
        changed.append("immunisations removed")
    if reported:
        parts.append(
            "Doses recorded as previously given elsewhere: "
            + ", ".join(_reported_labels(reported))
        )
        changed.append("doses reported as given elsewhere")
    if general_added:
        parts.append(
            "Other vaccinations added: " + ", ".join(_general_labels(general_added))
        )
        changed.append("other vaccinations added")
    if dispensed:
        parts.append(
            "Medicine dispensed: "
            + ", ".join(
                "{} (stock now {})".format(dispensing_label(row), row["stock_after"])
                for row in dispensed
            )
        )
        changed.append("items dispensed")
    return "; ".join(parts), changed


def process_edit_consultation(consultation_id, form_data, user_id, ip_address=None):
    """Apply an edit and record it in the audit trail.

    Returns (patient_id, context, message), as above.

    The audit entry is written from the values read back *after* the update, not
    from what the form was given, so it describes what the record actually holds
    now rather than what was asked for. Nothing is logged when nothing moved: a
    save that changed no field is not an event, and logging it would bury the
    edits that matter.
    """
    context, message = edit_consultation_context(consultation_id)
    if context is None:
        return None, None, message

    patient = context["patient"]
    age_context = context["age_context"]

    # READ AGAIN, FROM THE MODEL, RATHER THAN TAKING context["consultation"].
    #
    # This is one extra primary-key lookup and it closes a real defect that the
    # obvious version had. consultation_form_context() redacts the record it
    # returns, because it builds a page and a page must not carry a sealed
    # diagnosis to a viewer who may not read it. `before` is used for the
    # opposite purpose: it is what _apply_clinical_authority() writes BACK into
    # the record for a role that may not change those fields, and what
    # describe_changes() compares the saved row against. Feeding it the redacted
    # copy meant a staff member correcting a temperature on a sealed visit stored
    # the placeholder text as the patient's diagnosis, and the audit entry then
    # reported no change -- the doctor's assessment destroyed, silently, by the
    # very rule written to protect it.
    #
    # So the render path and the write path read the same row through two
    # deliberately different doors: one redacts, one does not, and neither is
    # derived from the other. get_consultation_by_id()'s own docstring states
    # that it is the unredacted one and why.
    before = get_consultation_by_id(consultation_id)
    if before is None:
        return None, None, "That consultation record could not be found."

    role = current_role()
    may_diagnose = can_diagnose(role)

    values = _extract_form(form_data)
    # `before` rather than None, and that difference is the one that matters on
    # this path. update_consultation() writes every column in CONSULTATION_FIELDS
    # on every save, so a staff member correcting a mistyped temperature would
    # otherwise erase the doctor's diagnosis by not having been shown it. Here the
    # two fields are put back to exactly what the record holds, so the UPDATE
    # writes them over themselves, describe_changes() reports no movement, and a
    # forged value never touches the database. See _apply_clinical_authority().
    values, refused = _apply_clinical_authority(values, before, role)
    # Judge a follow-up date against the visit it belongs to, not against today.
    values["_consultation_date"] = before["consultation_date"]
    ticked = form_data.getlist(IMMUNIZATION_FIELD) if age_context["is_pediatric"] else []
    # Reported doses are validated against the VISIT's date, not today's. A dose
    # given elsewhere must predate the encounter that recorded it, and on an edit
    # that encounter is the one being edited -- judging it against today would
    # let a date after the visit through on any record opened later.
    reported_entries, reported_errors = (
        parse_reported_doses(form_data, patient, before["consultation_date"],
                             parse_dose_keys(ticked))
        if age_context["is_pediatric"] else ([], {})
    )
    reported_submitted = _submitted_reported_doses(form_data)
    general_entries, general_errors = parse_general_vaccinations(form_data)
    general_submitted = _submitted_general_vaccinations(form_data)

    # consultation_id is passed to the pre-check here and not on the record path,
    # because only an edit can meet a visit that already has dispensing on file.
    # It is what turns a repeat line into "Paracetamol is already recorded for
    # this visit (20 tablets)" instead of a UNIQUE constraint failure.
    dispense_entries, dispense_errors = parse_dispensing(form_data)
    dispense_submitted = _submitted_dispensing(form_data)
    if not dispense_errors:
        dispense_errors = check_dispensing(dispense_entries, consultation_id)

    restrict = _submitted_restriction(form_data) and may_diagnose

    errors = validate_consultation_form(
        values, age_context, require_diagnosis=may_diagnose
    )
    errors.update(general_errors)
    errors.update(reported_errors)
    errors.update(dispense_errors)
    if errors:
        return None, consultation_form_context(
            patient, consultation=before, form=values, errors=errors, ticked=set(ticked),
            general_submitted=general_submitted,
            dispensing_submitted=dispense_submitted,
            restrict_submitted=restrict if may_diagnose else None,
            reported_submitted=reported_submitted,
        ), (
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} "
            f"need{'s' if len(errors) == 1 else ''} attention. "
            "Your changes have not been saved."
        )

    update_consultation(consultation_id, values, age_context)

    _log_refused_diagnosis(
        refused, patient, consultation_id, role, user_id, ip_address
    )

    # The seal moves with the save, in whichever direction the checkbox is now.
    #
    # AN UNTICKED BOX LIFTS A SEAL, AND ONLY THE ADMINISTRATOR CAN PRODUCE ONE.
    # That is a deliberate exception to the add-only rule the vaccination and
    # dispensing sections of this same form follow, and the reason those two are
    # add-only does not apply here. Their rule exists because an absent checkbox
    # would otherwise destroy a clinical record -- a dose a child was actually
    # given. Nothing is destroyed here: the diagnosis is untouched either way,
    # and what changes is who may read it. A seal that could be set but never
    # lifted would leave a record wrongly marked as privileged with no way back,
    # which is the same "cannot be put right" failure
    # routes/vaccination_correction_views.py was built to close.
    #
    # The box is only rendered for, and only read from, a role that may diagnose
    # -- `restrict` is forced False above for every other role, so a staff edit
    # cannot lift a seal by submitting a form that never had the box on it. That
    # is why the call below is inside this guard rather than beside it.
    restriction_outcome = None
    if may_diagnose:
        restriction_outcome = set_consultation_restriction(
            consultation_id, restrict, user_id
        )
        _log_restriction(
            restriction_outcome, consultation_id, patient, user_id, ip_address,
            visit_date=before["consultation_date"],
            recorded_by_name=before["recorded_by_name"],
        )

    # Immunisations are added the same way the clinical fields are corrected, and
    # audited the same way. They are not removed here: a dose already on file is
    # rendered as a locked fact rather than a checkbox, so no submission -- however
    # it was produced -- can delete one. See _apply_immunization_edit() for why
    # removal belongs on its own deliberate path instead.
    added, removed, reported = _apply_immunization_edit(
        patient, consultation_id, before, ticked, user_id, age_context,
        reported_entries,
    )
    general_added = _apply_general_vaccination_edit(
        patient, consultation_id, before, general_entries, user_id
    )
    # Add-only, exactly as the two above are, and dated to the visit rather than
    # to today -- a medicine recorded late was still handed over on the day of
    # the consultation. The stock movement, however, is real and current: the
    # units come off the shelf now, because now is when the system learned they
    # had gone.
    dispensed, dispense_failures = record_dispensing(
        patient_id=patient["id"],
        entries=dispense_entries,
        dispensed_by=user_id,
        date_dispensed=before["consultation_date"],
        consultation_id=consultation_id,
    )

    after = get_consultation_by_id(consultation_id)
    summary, changed = describe_changes(
        before, after, FIELD_LABELS, formatters=AUDIT_FORMATTERS
    )
    dose_summary, dose_changed = _describe_dose_changes(
        added, removed, general_added, dispensed, reported
    )
    if dose_summary:
        summary = f"{summary}; {dose_summary}" if summary else dose_summary
    changed = list(changed) + dose_changed

    # The seal is deliberately NOT added to `changed`. That list is what the
    # ACTION_CONSULTATION_UPDATED entry counts and names, and it means "fields of
    # the clinical record that moved" -- sealing one moves none of them, and it
    # has an entry of its own under its own module saying so. What it does have
    # to do is stop the save reporting "No changes" to somebody who just sealed a
    # record, which is why it is a separate sentence and its own branch below.
    seal_message = _restriction_message(restriction_outcome, patient, before)

    if not changed:
        # `dispensed` is empty on this path by construction -- anything stored
        # would have put "items dispensed" into `changed` -- so the only thing
        # _dispensing_message() can add here is a late refusal, which still has to
        # be said. A save that silently dropped a dispensing line would read as
        # "no changes" to the person who typed one.
        if seal_message:
            return patient["id"], None, (
                seal_message
                + " No clinical field was changed by this save."
                + _dispensing_message(dispensed, dispense_failures)
            )
        return patient["id"], None, (
            f"No changes. {patient['full_name']}'s consultation of "
            f"{display_date(before['consultation_date'])} is unchanged."
            + _dispensing_message(dispensed, dispense_failures)
        )

    # Self-contained on purpose: an audit entry read months later, on its own,
    # must say which record was touched, whose it is, and what moved -- without
    # anyone having to open the consultation to find out.
    details = (
        f"Consultation #{consultation_id} for {patient['full_name']} "
        f"({patient['patient_id']}), visit of "
        f"{display_date(before['consultation_date'])}, originally recorded by "
        f"{before['recorded_by_name']}. {len(changed)} field"
        f"{'s' if len(changed) != 1 else ''} changed — {summary}"
    )
    log_action(
        user_id=user_id,
        action=ACTION_CONSULTATION_UPDATED,
        module=MODULE_CONSULTATIONS,
        details=details,
        ip_address=ip_address,
    )

    # Dose changes arrive already worded ("immunisations added"), so the lookup
    # falls back to the entry itself rather than requiring a FIELD_LABELS key.
    field_names = ", ".join(FIELD_LABELS.get(field, field).lower() for field in changed)
    return patient["id"], None, (
        f"{patient['full_name']}'s consultation updated — {len(changed)} field"
        f"{'s' if len(changed) != 1 else ''} changed ({field_names}). "
        "The change has been recorded in the audit log."
        + (f" {seal_message}" if seal_message else "")
        + _dispensing_message(dispensed, dispense_failures)
    )


def _restriction_message(outcome, patient, consultation):
    """What to say about a seal that moved on this save, or "" if none did.

    Worded as consequence rather than as state. "Marked Restricted" is the flag;
    what the clinician needs told is which fields that takes away from whom, and
    which it deliberately leaves alone -- because the whole point of the design is
    that a sealed record is still one Health Center Staff can dispense against.
    """
    if outcome == "restricted":
        return (
            f"{patient['first_name']}'s consultation of "
            f"{display_date(consultation['consultation_date'])} is now Restricted "
            "— its diagnosis and treatment plan are withheld from Health Center "
            "Staff, who still see the visit, the vitals and what was dispensed."
        )
    if outcome == "lifted":
        return (
            f"The restriction on {patient['first_name']}'s consultation of "
            f"{display_date(consultation['consultation_date'])} has been lifted "
            "— its diagnosis and treatment plan are legible to Health Center "
            "Staff again."
        )
    return ""


# ---------------------------------------------------------------------------
# SEALING A RECORD AFTER IT WAS WRITTEN
#
# The checkbox on the form above covers the case the clinician knows at the time
# -- they are typing the diagnosis and can see it is sensitive. This covers the
# other one: a record already on file that should have been sealed, or one sealed
# in error and needing to be opened again.
#
# WHY IT IS ITS OWN ENDPOINT RATHER THAN A SECOND USE OF EDIT CONSULTATION.
# Opening the edit form to seal a record means loading a page whose every field
# is writable, saving it, and hoping nothing else moved on the way through. This
# changes one flag and touches nothing else -- so a seal set from the profile
# cannot alter a temperature by accident, and the audit trail is not left with a
# consultation edit that changed no field sitting beside the entry that explains
# it.
#
# It is reached from Patient Profile and not from the consultation form, which is
# the same separation routes/vaccination_correction_views.py sets out at length:
# the recording form is worked at speed with a patient in the room, and a
# deliberate act belongs on the screen where records are reviewed.
#
# There is NO Health Center Staff copy of the route this feeds, and that is the
# enforcement rather than a decoration of it -- the same arrangement that makes
# the Staff role view-only on community broadcasts. See routes/admin.py.
# ---------------------------------------------------------------------------
def process_consultation_restriction(form_data, user_id, ip_address=None):
    """Seal or unseal one consultation from the Patient Profile.

    Returns (patient_id, message). A patient_id of None means it could not
    resolve one and the caller should fall back to Patient Records.

    Everything the dialog claims is re-established here rather than trusted: the
    direction is checked against the two words this system recognises, the
    consultation is re-read, and the patient is read off that record rather than
    off the form. A POST can arrive without the page ever having been loaded, and
    the page it was loaded from may since have gone stale -- the same reasoning
    process_vaccination_correction() and process_archive_patients() both state.

    THE ROLE IS NOT CHECKED HERE, AND THAT IS NOT AN OMISSION. This function is
    reachable through exactly one route, which carries @role_required("Admin");
    there is no Health Center Staff endpoint for it to be reached through, so
    there is no request from another role for a check here to catch. Duplicating
    the guard would suggest the route's own is not sufficient, which is the
    opposite of what this project's other POST-only administrative paths say
    about themselves.
    """
    direction = str(form_data.get(RESTRICT_ACTION_FIELD) or "").strip().lower()
    if direction not in (RESTRICT_ON, RESTRICT_OFF):
        return None, "That is not something this system can do to a consultation."

    raw_id = str(form_data.get(RESTRICT_CONSULTATION_FIELD) or "").strip()
    if not raw_id.isdigit():
        return None, "Choose the consultation to change."
    consultation_id = int(raw_id)

    consultation = get_consultation_by_id(consultation_id)
    if consultation is None:
        return None, "That consultation record could not be found."

    patient = get_patient_by_id(consultation["patient_id"])
    if patient is None:
        return None, "That patient record could not be found."

    outcome = set_consultation_restriction(
        consultation_id, direction == RESTRICT_ON, user_id
    )
    if outcome == "missing":
        # Reachable only if the record was removed between the two reads above.
        return patient["id"], "That consultation record could not be found."

    if outcome == "unchanged":
        state = "already Restricted" if direction == RESTRICT_ON else "not Restricted"
        return patient["id"], (
            f"No change. {patient['first_name']}'s consultation of "
            f"{display_date(consultation['consultation_date'])} is {state}, and "
            "nothing has been written to the audit log."
        )

    _log_restriction(
        outcome, consultation_id, patient, user_id, ip_address,
        visit_date=consultation["consultation_date"],
        recorded_by_name=consultation["recorded_by_name"],
    )
    return patient["id"], (
        _restriction_message(outcome, patient, consultation)
        + " The change has been recorded in the audit log."
    )

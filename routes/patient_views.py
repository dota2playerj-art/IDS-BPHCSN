"""Shared context builders for the patient screens.

Screens 03 and 04 are rendered by two blueprints each -- once for the
Administrator and once for Health Center Staff -- from the same templates with
the same data. The queries live here so the two role variants cannot drift
apart; the routes stay thin and each keeps its own role_required guard and its
own redirect target.
"""
from flask import request, session

from models.appointments import (
    IN_CONSULTATION,
    WAITING,
    find_active_queue_entry,
    get_appointments_for_patient,
)
from models.audit import (
    ACTION_RESTRICTED_WITHHELD,
    MODULE_CONFIDENTIALITY,
    log_action,
)
from models.consultations import (
    RESTRICTED_PLACEHOLDER,
    can_view_restricted,
    get_consultations_for_patient,
)
from models.dispensing import get_dispensing_for_patient
from models.general_vaccinations import get_general_vaccinations_for_patient
from models.immunizations import (
    UNKNOWN_DATE_TEXT,
    dose_label,
    get_immunization_status,
)
from models.patients import (
    ALLERGY_OPTIONS,
    BLOOD_TYPES,
    CIVIL_STATUSES,
    CONDITION_OPTIONS,
    DOCTOR_ONLY_STATUS,
    EMERGENCY_RELATIONSHIPS,
    MUNICIPALITIES,
    PATIENT_STATUSES,
    PROVINCES,
    SEXES,
    can_declare_death,
    collect_list_field,
    create_patient,
    find_possible_duplicates,
    generate_next_patient_id,
    get_all_patients,
    get_patient_by_id,
    get_patient_statuses,
    get_patient_stats,
    set_patient_status,
    status_change_needs_doctor,
    update_patient,
    validate_patient_form,
)
from routes.consultation_views import (
    RESTRICT_ACTION_FIELD,
    RESTRICT_CONSULTATION_FIELD,
    RESTRICT_OFF,
    RESTRICT_ON,
)
from routes.vaccination_correction_views import correction_options
from utils.context import HEADER_SEARCH_MAX
from utils.dates import display_date
from utils.security import current_role

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


# THE REASON NEVER TRAVELS IN THE URL. The Check In dialog POSTs it to Register
# Patient with this marker. The route keeps it in the signed session and
# redirects to ?check_in=1, and the form reads it back only from the session.
# So a link typed by anyone cannot put words on this page: a check_in_reason in
# the query string is ignored.
CHECK_IN_HANDOFF_FIELD = "check_in_start"
_CHECK_IN_SESSION_KEY = "check_in_reason"


def check_in_handoff_requested(form_data):
    """True when this POST is the Check In dialog handing a reason over."""
    return (form_data.get(CHECK_IN_HANDOFF_FIELD) or "").strip() == "1"


def store_check_in_reason(form_data):
    """Keep the dialog's reason in the session until the patient is saved."""
    session[_CHECK_IN_SESSION_KEY] = check_in_reason(form_data)


def stored_check_in_reason():
    """The reason the dialog handed over, or "" if there is none."""
    return (session.get(_CHECK_IN_SESSION_KEY) or "")[:CHECK_IN_REASON_MAX]


def clear_check_in_reason():
    """Forget the handed-over reason once the new patient is checked in."""
    session.pop(_CHECK_IN_SESSION_KEY, None)


# Save & Register Another. The submit button carries this name/value pair, the
# shape this project already uses wherever one form has more than one action --
# Patient Records' status buttons and the Patient Queue's row buttons both
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


# THE URL CARRIES A PATIENT ID, NOT AN ADDRESS. It used to carry the address text
# itself, so a link could put any words in the form's boxes. Now it carries the
# id of the patient just saved, and the fresh form reads the address from that
# stored record. An id that names no patient fills nothing. Opening Register
# Patient from the sidebar still gives an empty form.
PREFILL_FROM_FIELD = "prefill_from"


def address_prefill_args(saved_patient_id):
    """The query string the fresh form opens with: the id of the patient just saved."""
    return {PREFILL_FROM_FIELD: saved_patient_id}


def address_prefill_form(args):
    """A form dict holding only the address of the patient named in the URL.

    Read from the stored record, never from the URL. Every other key is absent,
    and the template reads an absent key exactly as it reads a blank one -- so
    name, birth date, sex, civil status, blood type, conditions, allergies and
    the emergency contact all render as they do on a form opened with nothing.
    """
    raw = (args.get(PREFILL_FROM_FIELD) or "").strip()
    if not raw.isdigit():
        return None
    source = get_patient_by_id(int(raw))
    if source is None:
        return None
    values = {}
    for field in ADDRESS_PREFILL_FIELDS:
        value = str(source.get(field) or "").strip()
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
        # Whether the status dialog may offer Deceased, and may offer anything
        # at all on a record that already holds it. Answered from the signed-in
        # account's stored role, like every clinical permission here; the
        # template asks this rather than comparing role strings.
        # process_archive_patients() asks the same question again at the write,
        # which is the half that is the permission.
        "can_declare_death": can_declare_death(current_role()),
        "doctor_only_status": DOCTOR_ONLY_STATUS,
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

    # DECLARING DEATH, AND REVERSING IT, IS THE DOCTOR'S.
    # Asked here, at the write, of the signed-in account's stored role -- not of
    # anything the form carried -- and before set_patient_status() is reached,
    # so a refused request writes nothing at all. The status dialog does not
    # offer these moves to any other role, which makes that the presentation;
    # this is the permission, and a POST built by hand meets it just the same.
    # Active <-> Inactive is not asked about and stays with every role that
    # reaches this screen. See models/patients.py DOCTOR_ONLY_STATUS.
    if status_change_needs_doctor(current_status, status) and not can_declare_death(
        current_role()
    ):
        return (
            f"Only the Doctor can mark a patient {DOCTOR_ONLY_STATUS} or change a "
            f"{DOCTOR_ONLY_STATUS} record's status — declaring a death is a "
            "clinical decision. Nothing was changed."
        )

    changed = set_patient_status(ids, status)
    noun = "record" if changed == 1 else "records"
    # Reactivation is not archiving, so it does not claim to be. The retention
    # note only belongs on the two statuses that retire a record.
    if status == "Active":
        return f"{changed} patient {noun} reactivated and marked Active."
    return f"{changed} patient {noun} marked {status}. Nothing was deleted."


def immunization_next_step(patient, immunization):
    """What to actually do about this patient's Due/Overdue doses, or None.

    A dose that is merely Due or Overdue is not a record -- it is the schedule
    saying the dose has not happened yet -- so the Immunization Record tab
    deliberately offers no way to mark it given. That is the correct clinical
    rule: a vaccination is recorded during the visit it was given in, on the
    consultation form, against a real queue entry. What the tab used to do,
    though, was leave those rows blank, which reads as a dead end rather than as
    a rule. This says what the next step is instead.

    The step depends on where the child actually is right now, which is read from
    today's queue:

        "in_consultation"   they are with a clinician now, and that visit's
                            write-up is the screen the dose belongs on -- so the
                            row links straight to Record Consultation for that
                            appointment id.
        "waiting"           they are here and in today's queue, but the visit has
                            not been started. Record Consultation refuses a
                            Waiting row by design (see
                            record_consultation_context), so linking there would
                            hand over an error message. The row links to the
                            queue, where the consultation is started, which is
                            the real next action.
        "none"             they are not at the health center, and no link could
                            be honest about a visit that is not happening. The
                            row says to record it at the next consultation.

    Returns None when nothing is outstanding, so the template renders nothing
    rather than an empty panel.
    """
    if not immunization["attention_count"]:
        return None

    name = patient["first_name"]
    entry = find_active_queue_entry(patient["id"])
    status = entry["status"] if entry else None

    if status == IN_CONSULTATION:
        return {
            "state": "in_consultation",
            "appointment_id": entry["id"],
            "label": "Record now",
            "detail": (
                f"{name} is In Consultation now. Open Record Consultation for "
                "this visit and record the dose there."
            ),
            "banner": (
                f"{name} is In Consultation now. Record any dose given on that "
                "visit's consultation form."
            ),
        }

    if status == WAITING:
        return {
            "state": "waiting",
            "appointment_id": entry["id"],
            "label": "In today's queue",
            "detail": (
                f"{name} is Waiting in today's queue. Start the consultation from "
                "the queue, then record the dose on the consultation form."
            ),
            "banner": (
                f"{name} is Waiting in today's queue. Start that consultation, "
                "then record any dose given on its form."
            ),
        }

    return {
        "state": "none",
        "appointment_id": None,
        "label": "At next visit",
        "detail": (
            f"{name} is not at the health center today. Record this during their "
            "next consultation."
        ),
        "banner": (
            f"{name} is not in today's queue. These doses are recorded during a "
            "consultation, so they are given and recorded at the next visit."
        ),
    }


def _log_withheld_consultations(patient, withheld, viewer_role):
    """Record that this render kept a sealed consultation back from its viewer.

    ONE ENTRY PER PAGE THAT ACTUALLY WITHHELD SOMETHING, naming every entry it
    withheld. Not one per sealed consultation, and not one per profile opened.
    That boundary is drawn on purpose and models/audit.py's note on
    ACTION_RESTRICTED_WITHHELD sets out why: the event a reviewer is asking about
    is "this health worker was at this patient's privileged record", which is one
    thing however many visits are on the page. A row per sealed entry would
    multiply one access by the length of the patient's history, and a row per
    profile view would file an entry about an ordinary page.

    Nothing is written when nothing was withheld, which is every render for the
    Administrator and every render of a patient with no sealed visit -- so the
    ordinary use of this screen adds nothing to the trail.

    THE ACCESS RULE IS NOT ENFORCED HERE. The content is already gone by the time
    this runs: get_consultations_for_patient() redacted it at the read, and this
    counts what came back marked `withheld`. If this function were deleted the
    seal would still hold and the only loss would be the evidence that it did --
    which is exactly the right relationship between an access control and its
    log, and the reason a failure to write the row (log_action() returns None for
    an unattributable request) does not cost the viewer their page.
    """
    if not withheld:
        return None

    visits = ", ".join(
        "#{} ({})".format(entry["id"], display_date(entry["consultation_date"]))
        for entry in withheld
    )
    return log_action(
        user_id=session.get("user_id"),
        action=ACTION_RESTRICTED_WITHHELD,
        module=MODULE_CONFIDENTIALITY,
        details=(
            f"Patient Profile for {patient['full_name']} "
            f"({patient['patient_id']}) was rendered for an account holding the "
            f"role {viewer_role or 'no role'}, which may not read a restricted "
            f"consultation. {len(withheld)} consultation"
            f"{'s were' if len(withheld) != 1 else ' was'} withheld — {visits}. "
            f'Each showed "{RESTRICTED_PLACEHOLDER}" in place of its diagnosis '
            "and treatment plan; the withheld text was not sent to the browser "
            "at all, having been removed before the page was built. The visit "
            "date, chief complaint, vital signs, immunisations and dispensing on "
            "the same records were shown as normal, so intake and dispensing are "
            "unaffected"
        ),
        ip_address=request.remote_addr,
    )


def patient_profile_context(patient_id):
    """Everything Screen 04 renders, or None if no such patient exists.

    Returning None rather than raising lets each blueprint redirect to its own
    Patient Records URL, which differs per role.

    THIS FUNCTION CAN WRITE TO THE AUDIT TRAIL, which no other context builder in
    this project does, and it is worth saying out loud rather than leaving to be
    discovered. A consultation the clinician has sealed is withheld from a viewer
    who may not read it, and RA 11166 makes a health center answerable for who
    has been at privileged medical information -- so the withholding is recorded.
    It is done here, in the one place both blueprints build this screen from,
    because doing it in each route would be two copies of a confidentiality rule
    that could come to disagree. See _log_withheld_consultations().
    """
    patient = get_patient_by_id(patient_id)
    if patient is None:
        return None

    # Read once from the signed-in account and used for every read below, so a
    # single page cannot redact its Consultation History against one answer and
    # its Dispensing History against another.
    viewer_role = current_role()
    may_view_restricted = can_view_restricted(viewer_role)

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

    # Read unconditionally too, and for the same reason. This is the tab that
    # said "Medicine dispensing is not recorded yet" for the whole life of the
    # project; there is now a table behind it, so it shows what that table holds
    # for this patient and an honest empty state when it holds nothing.
    dispensing = get_dispensing_for_patient(patient_id, viewer_role)

    # Redacted at the read, so what a viewer may not see is not in this list and
    # therefore not in the render context and not in the response body. The
    # template's placeholder is what it prints, not what it hides.
    consultations = get_consultations_for_patient(patient_id, viewer_role)
    withheld = [entry for entry in consultations if entry.get("withheld")]
    _log_withheld_consultations(patient, withheld, viewer_role)

    return {
        "patient": patient,
        # What a Due/Overdue row should tell staff to do next. None when nothing
        # is outstanding. Deliberately not a way to record a dose from here --
        # see immunization_next_step() for why the schedule half of this tab
        # carries guidance rather than an action.
        "immunization_next_step": immunization_next_step(patient, immunization),
        "consultations": consultations,
        # Whether this viewer is being shown everything. The template asks this
        # rather than comparing role strings, so it cannot come to disagree with
        # the server about who may read a sealed record -- and it is what decides
        # whether the seal control and the "you are seeing everything" wording
        # appear at all.
        "may_view_restricted": may_view_restricted,
        # How many entries on this page are sealed, so the tab can say so once at
        # the top instead of leaving a health worker to notice it row by row.
        "withheld_count": len(withheld),
        "restricted_placeholder": RESTRICTED_PLACEHOLDER,
        "restrict_consultation_field": RESTRICT_CONSULTATION_FIELD,
        "restrict_action_field": RESTRICT_ACTION_FIELD,
        "restrict_on": RESTRICT_ON,
        "restrict_off": RESTRICT_OFF,
        "appointments": get_appointments_for_patient(patient_id),
        "immunization": immunization,
        "show_immunizations": show_immunizations,
        # What the page prints where a reported dose's date would go and there is
        # none. From the model rather than typed into the template, so the
        # profile, the consultation form and the flash message say it the same
        # way -- and so it stays a sentence rather than becoming a dash, which
        # would read as an empty field instead of as "this dose happened and
        # nobody here knows the day".
        "immunization_unknown_date_text": UNKNOWN_DATE_TEXT,
        "doses_by_consultation": _doses_by_consultation(immunization["records"]),
        "general_vaccinations": general_vaccinations,
        # The Immunization Record tab is worth opening if either half has
        # anything in it -- and the tab's badge, which counts outstanding EPI
        # doses, deliberately does not count these: nothing here is outstanding,
        # because nothing here is graded.
        "general_vaccinations_by_consultation": _general_by_consultation(
            general_vaccinations
        ),
        # The vocabularies the Correct dialog offers -- the EPI schedule's dose
        # list, the common vaccine names, the dose range and today's date as the
        # picker's ceiling. Read from
        # routes/vaccination_correction_views.correction_options() rather than
        # assembled here, so the dialog cannot offer a value the endpoint behind
        # it would refuse, or omit one it would accept.
        "correction": correction_options(),
        # The Dispensing History tab, and the stat card above it. Both were
        # placeholders until medicine_dispensing existed.
        "dispensing": dispensing,
        "dispensing_by_consultation": _dispensing_by_consultation(dispensing),
        # Units, not rows: "3 issues" and "60 tablets" answer different questions,
        # and the card is headed with the one a health worker asks. Summed from
        # the list already read rather than by a second query.
        "dispensed_units": sum(row["quantity_dispensed"] for row in dispensing),
    }


def _dispensing_by_consultation(records):
    """{consultation_id: [dispensing, ...]} for the View panel on a history row.

    Built from the list the Dispensing History tab has already read rather than by
    asking the database again -- exactly what _doses_by_consultation() and
    _general_by_consultation() do, and for the same reason: the records carry
    their consultation_id, so the grouping is free.

    A dispensing recorded against no consultation is skipped, as the vaccinations
    are: it belongs to the patient's history but to no row in this table. That
    only arises if a consultation is deleted out from under it -- the column is
    ON DELETE SET NULL -- and the item still shows on the tab itself.
    """
    grouped = {}
    for record in records:
        if record.get("consultation_id"):
            grouped.setdefault(record["consultation_id"], []).append(record)
    return grouped


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
                             check_in=False, check_in_reason_text=""):
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

    """
    if patient is not None and form is None:
        form = patient_to_form(patient)

    check_in = bool(check_in) and patient is None

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

    The check-in intent is read off the submitted form and threaded back into
    every context this builds, so a first-time patient whose form bounces on a
    validation error or a duplicate warning is still on that path when she
    finally saves.
    """
    values = _extract_form(form_data)
    # Ignored in edit mode by register_patient_context(); read unconditionally so
    # every branch below can pass the same intent through.
    check_in = check_in_requested(form_data)
    reason = check_in_reason(form_data)

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
            check_in=check_in, check_in_reason_text=reason,
        )

    return create_patient(values), None

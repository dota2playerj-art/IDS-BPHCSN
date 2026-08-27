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
"""
from models.appointments import (
    IN_CONSULTATION,
    complete_consultation,
    get_appointment_by_id,
    get_queue_stats,
    queue_display_name,
)
from models.audit import (
    ACTION_CONSULTATION_UPDATED,
    MODULE_CONSULTATIONS,
    describe_changes,
    log_action,
)
from models.consultations import (
    AUDIT_FORMATTERS,
    CONSULTATION_FIELDS,
    FIELD_LABELS,
    INFANT_AGE_YEARS,
    NUMERIC_LIMITS,
    PEDIATRIC_AGE_YEARS,
    consultation_age_context,
    create_consultation,
    get_consultation_by_id,
    get_consultation_for_appointment,
    update_consultation,
    validate_consultation_form,
)
from models.dispensing import (
    DISPENSE_ROWS,
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
)
from models.general_vaccinations import FIELD_LABELS as GENERAL_VACCINE_LABELS
from models.immunizations import (
    dose_label,
    get_immunization_status,
    get_immunizations_for_consultation,
    parse_dose_keys,
    record_immunizations,
)
from models.patients import get_patient_by_id
from utils.dates import display_date, today

# The consultation form posts one checkbox per scheduled dose under this name,
# each valued "CODE:DOSE". Named once so the template, the parser and the audit
# description cannot disagree about it.
IMMUNIZATION_FIELD = "immunizations"


def _extract_form(form_data):
    """Pull the submitted values into the shape the model and template share."""
    return {
        field: (form_data.get(field) or "").strip() for field in CONSULTATION_FIELDS
    }


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


def _immunization_context(patient, consultation, visit_date, ticked=None):
    """The "Immunizations Given Today" section's state for this visit.

    Every scheduled dose is offered, not only the ones outstanding, because a
    health worker catching a child up needs to see the whole schedule to know
    where they are in it. What differs per dose is whether it can still be
    ticked:

        already on file        locked, with the date it was actually given
        not yet given          free to tick, badged Due / Overdue / Upcoming

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

    `ticked` carries the operator's selection back through a validation bounce,
    so a rejected save does not throw away which boxes they had checked.
    """
    status = get_immunization_status(patient, on_date=visit_date)
    this_visit = {
        (dose["vaccine_code"], dose["dose_number"])
        for dose in get_immunizations_for_consultation(
            consultation["id"] if consultation else None
        )
    }

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
    return status


def _general_vaccination_context(consultation, submitted=None):
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
        for key, name, protects in COMMON_VACCINES
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
    """The "Medicines Dispensed" section's state for this visit.

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
            for index in range(DISPENSE_ROWS)
        ],
        "recorded": recorded,
        "min_quantity": low,
        "max_quantity": high,
    }


def _submitted_dispensing(form_data):
    """What the operator had chosen and typed, for replay through a bounce."""
    values = {}
    for index in range(DISPENSE_ROWS):
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


def consultation_form_context(patient, appointment=None, consultation=None,
                              form=None, errors=None, ticked=None,
                              general_submitted=None, dispensing_submitted=None):
    """Everything the Record / Edit Consultation screen renders.

    `consultation` set means edit mode: the template switches its wording, shows
    the original visit date and author as read-only fact, and posts back to the
    edit URL.

    The age context is computed against the consultation's own date in edit mode
    and against today for a new record, so which growth fields appear is decided
    by how old the patient was at the visit -- not by how old they are now. The
    immunisation schedule is resolved against that same date for the same reason.
    """
    visit_date = consultation["consultation_date"] if consultation else today()
    age_context = consultation_age_context(patient, on_date=visit_date)

    if form is None:
        form = _consultation_to_form(consultation) if consultation else {}

    return {
        "patient": patient,
        "appointment": appointment,
        "consultation": consultation,
        "form": form,
        "errors": errors or {},
        "age_context": age_context,
        "visit_date": visit_date,
        # Merged rather than reaching into models.consultations.FIELD_LABELS:
        # the error summary prints field_labels.get(field, field) and would
        # otherwise show a raw field name for a general-vaccination error. The
        # consultation's own label map is left exactly as it was, so the audit
        # trail still describes only the fields it describes.
        "field_labels": dict(FIELD_LABELS, **GENERAL_VACCINE_LABELS,
                             **DISPENSING_LABELS),
        # (field, label, unit, low, high, whole) -- the form prints the unit in
        # each field's hint and the range in its out-of-range message, from the
        # same tuples the validator checks against.
        "numeric_limits": NUMERIC_LIMITS,
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "infant_age_years": INFANT_AGE_YEARS,
        # Only computed for the cohort the schedule applies to; the template
        # renders the section inside the same is_pediatric guard.
        "immunization": (
            _immunization_context(patient, consultation, visit_date, ticked)
            if age_context["is_pediatric"] else None
        ),
        "immunization_field": IMMUNIZATION_FIELD,
        # Offered for every patient, with no age guard at all -- that is the
        # whole point of the section. An adult receiving a hepatitis B dose had
        # nowhere to be recorded before it existed, and a child can have both
        # this and their EPI doses at the same visit.
        "general_vaccination": _general_vaccination_context(
            consultation, general_submitted
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


def process_record_consultation(appointment_id, form_data, user_id):
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

    values = _extract_form(form_data)
    # The schedule only applies to the paediatric cohort, so doses submitted for
    # anyone else are dropped here rather than stored -- the same second refusal
    # store_values() gives the growth measurements, and for the same reason: the
    # form not offering a field is not the same as the server refusing it.
    ticked = form_data.getlist(IMMUNIZATION_FIELD) if age_context["is_pediatric"] else []
    dose_keys = parse_dose_keys(ticked)

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

    errors = validate_consultation_form(values, age_context)
    errors.update(general_errors)
    errors.update(dispense_errors)
    if errors:
        return None, consultation_form_context(
            patient, appointment=appointment, form=values, errors=errors,
            ticked=set(ticked), general_submitted=general_submitted,
            dispensing_submitted=dispense_submitted,
        ), (
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} need attention. "
            "Nothing has been saved yet."
        )

    consultation_id = create_consultation(
        patient_id=patient["id"],
        recorded_by=user_id,
        values=values,
        age_context=age_context,
        appointment_id=appointment["id"],
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
    if given:
        message += (
            f" {len(given)} immunisation{'s' if len(given) != 1 else ''} recorded: "
            + ", ".join(dose_label(code, dose) for code, dose in given) + "."
        )
        # Say what is still outstanding while the parent is still in the room --
        # a catch-up visit is the moment that information is worth anything.
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
    """What to add to the save's flash message about the medicine given.

    Two things it deliberately says that a bare count would not.

    The stock left behind, per medicine. A health worker who has just taken the
    last twelve tablets off a shelf should be told so at the moment they do it,
    while the patient is still in the room and while restocking is still a
    decision somebody can make today -- not on the next render of a dashboard
    they may not open. The figure is the one record_dispensing() wrote, read back
    off its own return rather than re-queried, so the sentence cannot report a
    level the shelf does not hold.

    And a refusal that arrived too late to bounce the form. check_dispensing()
    runs before the consultation is written, so this is only reachable when the
    shelf moved between that check and the save -- another dispensing committing
    in between. The consultation is saved either way, because it is the clinical
    fact and it happened; what did not happen is the medicine leaving the store,
    and saying so plainly is the only honest option. Quietly dropping it would
    leave a record of a visit whose prescription vanished.
    """
    if failures:
        return (
            " The consultation was saved, but no medicine was dispensed: "
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
        " {} medicine{} dispensed: {}. Stock updated — {}.".format(
            len(dispensed), "s" if len(dispensed) != 1 else "", given, remaining
        )
    )


def _apply_immunization_edit(patient, consultation_id, consultation, ticked,
                             user_id, age_context):
    """Record any newly ticked doses for this visit. Add-only.

    Returns (added, removed) as lists of (code, dose_number). `removed` is always
    empty and is kept in the signature because the audit line, the flash message
    and the caller all read it; the day a deliberate correction path exists it is
    what that path will report through.

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
    """
    if not age_context["is_pediatric"]:
        return [], []

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
    return added, []


def _general_labels(entries):
    """['Hepatitis B', 'Rabies dose 3'] for a list of stored entries."""
    return [vaccination_label(entry["vaccine_name"], entry["dose_number"])
            for entry in entries]


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


def _describe_dose_changes(added, removed, general_added=(), dispensed=()):
    """The vaccination and dispensing half of an audit line.

    Returns (summary, changed_labels).

    Named in full rather than counted -- "2 immunisations changed" would tell a
    later reader nothing about which child got what, which is the whole reason
    the entry exists.

    EPI doses, other vaccinations and dispensed medicine are reported as separate
    phrases rather than pooled into one count, so an entry read months later still
    says which kind of record moved -- a scheduled infant dose, an adult booster
    and twenty tablets off a shelf are not interchangeable facts.

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
        changed.append("medicine dispensed")
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
    before = context["consultation"]
    age_context = context["age_context"]

    values = _extract_form(form_data)
    # Judge a follow-up date against the visit it belongs to, not against today.
    values["_consultation_date"] = before["consultation_date"]
    ticked = form_data.getlist(IMMUNIZATION_FIELD) if age_context["is_pediatric"] else []
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

    errors = validate_consultation_form(values, age_context)
    errors.update(general_errors)
    errors.update(dispense_errors)
    if errors:
        return None, consultation_form_context(
            patient, consultation=before, form=values, errors=errors, ticked=set(ticked),
            general_submitted=general_submitted,
            dispensing_submitted=dispense_submitted,
        ), (
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} need attention. "
            "Your changes have not been saved."
        )

    update_consultation(consultation_id, values, age_context)

    # Immunisations are added the same way the clinical fields are corrected, and
    # audited the same way. They are not removed here: a dose already on file is
    # rendered as a locked fact rather than a checkbox, so no submission -- however
    # it was produced -- can delete one. See _apply_immunization_edit() for why
    # removal belongs on its own deliberate path instead.
    added, removed = _apply_immunization_edit(
        patient, consultation_id, before, ticked, user_id, age_context
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
        added, removed, general_added, dispensed
    )
    if dose_summary:
        summary = f"{summary}; {dose_summary}" if summary else dose_summary
    changed = list(changed) + dose_changed

    if not changed:
        # `dispensed` is empty on this path by construction -- anything stored
        # would have put "medicine dispensed" into `changed` -- so the only thing
        # _dispensing_message() can add here is a late refusal, which still has to
        # be said. A save that silently dropped a medicine line would read as
        # "no changes" to the person who typed one.
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
        + _dispensing_message(dispensed, dispense_failures)
    )

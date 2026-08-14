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
from models.immunizations import (
    dose_label,
    get_immunization_status,
    get_immunizations_for_consultation,
    parse_dose_keys,
    record_immunizations,
    remove_immunizations,
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

        given at THIS visit    ticked, and untickable only by untickng it here
        given at another visit locked, with the date it was actually given
        not yet given          free to tick, badged Due / Overdue / Upcoming

    A dose recorded elsewhere is locked rather than hidden so the form cannot be
    used to silently re-date a vaccination that already happened -- which is
    exactly what an unlocked, pre-ticked checkbox would invite.

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
        item["given_here"] = pair in this_visit
        # Locked when it is on file from some other visit.
        item["locked"] = item["given"] and pair not in this_visit
        if ticked is None:
            item["checked"] = item["given_here"]
        else:
            item["checked"] = item["key"] in ticked
    return status


def consultation_form_context(patient, appointment=None, consultation=None,
                              form=None, errors=None, ticked=None):
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
        "field_labels": FIELD_LABELS,
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

    errors = validate_consultation_form(values, age_context)
    if errors:
        return None, consultation_form_context(
            patient, appointment=appointment, form=values, errors=errors,
            ticked=set(ticked),
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


def _apply_immunization_edit(patient, consultation_id, consultation, ticked,
                             user_id, age_context):
    """Bring this visit's recorded doses in line with the ticked boxes.

    Returns (added, removed) as lists of (code, dose_number).

    Only doses this consultation recorded are candidates for removal, and only
    doses not already on file anywhere are candidates for addition -- a box that
    is ticked because another visit gave that dose is left entirely alone, so
    saving an edit cannot re-date somebody else's vaccination.
    """
    if not age_context["is_pediatric"]:
        return [], []

    selected = set(parse_dose_keys(ticked))
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
    removed = remove_immunizations(
        patient_id=patient["id"],
        dose_keys=[pair for pair in sorted(current) if pair not in selected],
        consultation_id=consultation_id,
    )
    return added, removed


def _describe_dose_changes(added, removed):
    """The immunisation half of an audit line. Returns (summary, changed_labels).

    Named in full rather than counted -- "2 immunisations changed" would tell a
    later reader nothing about which child got what, which is the whole reason
    the entry exists.
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

    errors = validate_consultation_form(values, age_context)
    if errors:
        return None, consultation_form_context(
            patient, consultation=before, form=values, errors=errors, ticked=set(ticked),
        ), (
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} need attention. "
            "Your changes have not been saved."
        )

    update_consultation(consultation_id, values, age_context)

    # Immunisations are corrected the same way the clinical fields are, and
    # audited the same way -- a dose ticked by mistake is a clerical error like
    # any other, and leaving it uncorrectable would mean the only way to fix it
    # was to edit the database by hand.
    #
    # Scoped to this visit: only doses recorded *here* can be removed here.
    # remove_immunizations() enforces that in its WHERE clause rather than
    # relying on this list being right.
    added, removed = _apply_immunization_edit(
        patient, consultation_id, before, ticked, user_id, age_context
    )

    after = get_consultation_by_id(consultation_id)
    summary, changed = describe_changes(
        before, after, FIELD_LABELS, formatters=AUDIT_FORMATTERS
    )
    dose_summary, dose_changed = _describe_dose_changes(added, removed)
    if dose_summary:
        summary = f"{summary}; {dose_summary}" if summary else dose_summary
    changed = list(changed) + dose_changed

    if not changed:
        return patient["id"], None, (
            f"No changes. {patient['full_name']}'s consultation of "
            f"{display_date(before['consultation_date'])} is unchanged."
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
    )

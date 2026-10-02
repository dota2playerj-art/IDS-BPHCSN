"""The deliberate correction path for a vaccination that was recorded wrongly.

That was the right call and it left a real gap, which this module closes. A
genuine mistake -- the wrong vaccine ticked, the wrong dose number, the wrong
date -- could be made but not put right. "The record is wrong and cannot be
corrected" is not a safer state than "the record can be corrected carelessly";
it is a different failure, and on a child's immunisation history it is the one
that gets read as fact for years.
"""
from datetime import datetime

from models.audit import (
    ACTION_GENERAL_VACCINATION_CORRECTED,
    ACTION_IMMUNIZATION_CORRECTED,
    MODULE_IMMUNIZATIONS,
    describe_changes,
    log_action,
)
from models.consultations import as_date
from models.general_vaccinations import (
    COMMON_VACCINES,
    DOSE_RANGE,
    MAX_NAME_LENGTH,
    clean_dose_number,
    clean_vaccine_name,
    correct_general_vaccination,
    get_general_vaccination_by_id,
    vaccination_label,
)
from models.immunizations import (
    EPI_SCHEDULE,
    SCHEDULE_KEYS,
    correct_immunization,
    dose_label,
    get_immunization_by_id,
)
from models.patients import get_patient_by_id
from utils.dates import display_date, today

# What the dialog posts to say which record it is correcting. The two tables have
# independent id sequences, so the kind is what decides which one an id means --
# it is validated against KINDS below before anything is looked up, exactly as
# process_archive_patients() validates its status against PATIENT_STATUSES.
KIND_FIELD = "record_kind"
RECORD_FIELD = "record_id"
EPI_KIND = "epi"
GENERAL_KIND = "general"

# The fields a correction may move, as the dialog posts them. Named here so the
# template, the parsers and the error messages cannot disagree.
VACCINE_FIELD = "correct_vaccine"
NAME_FIELD = "correct_vaccine_name"
DOSE_FIELD = "correct_dose_number"
DATE_FIELD = "correct_date"

# How far back a date of administration may be corrected to when the patient has
# no birth date on file, which Register Patient permits. The real floor is the
# patient's own birthday and that is what is used wherever one exists; this is
# the fallback, wider than the under-five cohort the EPI schedule covers and wide
# enough for an adult's booster history, while still catching a mistyped year.
MAX_BACKDATE_YEARS = 10


def _labels_for(kind):
    """The audit label map for one kind, in the order an entry lists its fields."""
    if kind == EPI_KIND:
        # One label, not two. A vaccine and its dose number are stored in two
        # columns but read as one fact -- "Pentavalent dose 2" -- and an entry
        # reporting "Vaccine: PENTA -> OPV; Dose number: 2 -> 1" would make a
        # reader reassemble what dose_label() already assembles everywhere else.
        return {
            "vaccine_label": "Vaccine / dose",
            "date_administered": "Date given",
        }
    # Kept as three separate fields here, deliberately unlike the EPI map above.
    # A dose number in this table is optional and independently meaningful: it is
    # blank for most vaccines and clearing a wrongly typed one is a correction in
    # its own right, which "Influenza dose 3 -> Influenza" would report as a
    # change of vaccine rather than of dose.
    return {
        "vaccine_name": "Vaccine",
        "dose_number": "Dose number",
        "date_administered": "Date given",
    }


def _date_renderer(value):
    """A stored date as a person reads it, or its raw text if it will not parse."""
    return display_date(value, fallback=str(value) if value else "not recorded")


_FORMATTERS = {"date_administered": _date_renderer}


def _snapshot(kind, record):
    """One stored row rendered into the flat dict describe_changes() compares.

    The before and the after both go through this, so a field can never be
    described one way going in and another coming out.
    """
    if kind == EPI_KIND:
        return {
            "vaccine_label": dose_label(record["vaccine_code"], record["dose_number"]),
            "date_administered": record["date_administered"],
        }
    return {
        "vaccine_name": record["vaccine_name"],
        "dose_number": record["dose_number"],
        "date_administered": record["date_administered"],
    }


def _validate_date(raw, patient, required=True):
    """The one date rule both kinds are held to. Returns (date_text, error).

    Shared rather than written twice because it is the same clinical claim in
    both tables: this is the day the patient actually received the vaccine.

    Three refusals, each of something that cannot have happened:

      * a date that is not a date at all;
      * a date in the future -- a dose given tomorrow has not been given;
      * a date before the patient was born.

    The third falls back to MAX_BACKDATE_YEARS where no birth date is on file, so
    a record for a patient registered without one is still held to something.

    `required` is False for exactly one kind of record: an EPI dose stored as
    reported from another facility. Its date belongs to somebody else's files and
    may genuinely be unknown -- models/immunizations.py explains why the column is
    nullable for that case and only that case -- so a correction to such a record
    must be able to leave it, or put it back to, blank. Every other record here
    is one this health center administered, and for those an absent date is still
    a refusal: correcting a record must not be a way to remove a fact the
    original entry was required to supply.
    """
    text = str(raw or "").strip()
    if not text:
        if required:
            return None, "Enter the date the vaccine was actually given."
        return None, None

    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None, "Enter a valid date in YYYY-MM-DD format."

    now = today()
    if parsed > now:
        return None, (
            "The date given cannot be in the future — a dose recorded for "
            f"{display_date(parsed)} has not been administered yet."
        )

    birth_text = patient.get("birth_date") if patient else None
    if birth_text:
        birth = as_date(birth_text)
        if parsed < birth:
            return None, (
                f"The date given cannot be before {patient['first_name']} was born "
                f"({display_date(birth)})."
            )
    elif parsed.year < now.year - MAX_BACKDATE_YEARS:
        return None, (
            f"The date given cannot be more than {MAX_BACKDATE_YEARS} years ago. "
            "This patient has no birth date on file to check it against."
        )

    return parsed.isoformat(), None


def _parse_epi(form_data, record, patient):
    """Read the dialog's EPI half. Returns (values, errors).

    The vaccine arrives as the same "CODE:DOSE" pair the consultation form's
    checkboxes post, and is held to the same gate parse_dose_keys() applies
    there: only a pair the DOH schedule actually lists survives, so a hand-made
    POST cannot correct a dose into "Pentavalent dose 7".

    The one addition is that the record's OWN current pair is accepted even if
    the schedule no longer lists it. get_immunization_status() reports such a
    dose under extra_records -- a vaccine given before a schedule revision, say
    -- and refusing it here would mean the one field on that record which can be
    genuinely wrong, its date, could not be corrected without also forcing the
    vaccine onto the current schedule. Accepting only the pair already stored
    lets nothing new off-schedule be invented.
    """
    errors = {}
    raw = str(form_data.get(VACCINE_FIELD) or "").strip()
    code, _, dose = raw.partition(":")
    code = code.strip().upper()
    dose = dose.strip()

    pair = None
    if dose.isdigit():
        candidate = (code, int(dose))
        current = (record["vaccine_code"], record["dose_number"])
        if candidate in SCHEDULE_KEYS or candidate == current:
            pair = candidate
    if pair is None:
        errors[VACCINE_FIELD] = "Choose the vaccine and dose from the DOH EPI schedule."

    # Blank is permitted only where the stored record is one reported from
    # elsewhere. The question is asked of the RECORD, never of the form: a POST
    # cannot declare its own date optional by claiming a source, because the
    # source is read from the row being corrected.
    date_text, date_error = _validate_date(
        form_data.get(DATE_FIELD), patient,
        required=not record.get("reported"),
    )
    if date_error:
        errors[DATE_FIELD] = date_error

    if errors:
        return None, errors
    return {
        "vaccine_code": pair[0],
        "dose_number": pair[1],
        "date_administered": date_text,
    }, {}


def _parse_general(form_data, record, patient):
    """Read the dialog's general half. Returns (values, errors).

    Held to exactly the rules models/general_vaccinations.py already applies when
    one of these is first recorded, through that module's own cleaners rather
    than through a second copy of them: the name is whitespace-collapsed and
    length-capped by clean_vaccine_name(), the dose number is range-checked by
    clean_dose_number(). A correction is not a back door around the validation
    the original entry passed.
    """
    errors = {}
    name = clean_vaccine_name(form_data.get(NAME_FIELD))
    if not name:
        errors[NAME_FIELD] = "Name the vaccine that was given."

    dose_number, ok = clean_dose_number(form_data.get(DOSE_FIELD))
    if not ok:
        low, high = DOSE_RANGE
        errors[DOSE_FIELD] = (
            f"Enter the dose number as a whole number between {low} and {high}, "
            "or leave it blank if this vaccine has no dose count."
        )

    date_text, date_error = _validate_date(form_data.get(DATE_FIELD), patient)
    if date_error:
        errors[DATE_FIELD] = date_error

    if errors:
        return None, errors
    return {
        "vaccine_name": name,
        "dose_number": dose_number,
        "date_administered": date_text,
    }, {}


def _apply_epi(record_id, values):
    return correct_immunization(
        record_id,
        values["vaccine_code"],
        values["dose_number"],
        values["date_administered"],
    )


def _apply_general(record_id, values):
    return correct_general_vaccination(
        record_id,
        values["vaccine_name"],
        values["dose_number"],
        values["date_administered"],
    )


def _epi_corrected_label(values):
    return dose_label(values["vaccine_code"], values["dose_number"])


def _general_corrected_label(values):
    return vaccination_label(values["vaccine_name"], values["dose_number"])


# The whole of what differs between the two kinds, in one table. Everything below
# reads this rather than branching on the kind, so the correction mechanism
# exists once.
KINDS = {
    EPI_KIND: {
        "noun": "EPI immunisation",
        "fetch": get_immunization_by_id,
        "parse": _parse_epi,
        "apply": _apply_epi,
        "action": ACTION_IMMUNIZATION_CORRECTED,
        "label": lambda record: dose_label(
            record["vaccine_code"], record["dose_number"]
        ),
        "submitted_label": _epi_corrected_label,
        "duplicate": (
            "{patient} already has {label} recorded. Correct that record, or choose a different "
            "dose."
        ),
        # The field the duplicate message tells the operator to change.
        "duplicate_field": VACCINE_FIELD,
    },
    GENERAL_KIND: {
        "noun": "Vaccination",
        "fetch": get_general_vaccination_by_id,
        "parse": _parse_general,
        "apply": _apply_general,
        "action": ACTION_GENERAL_VACCINATION_CORRECTED,
        "label": lambda record: vaccination_label(
            record["vaccine_name"], record["dose_number"]
        ),
        "submitted_label": _general_corrected_label,
        "duplicate": (
            "{patient} already has {label} recorded on that date. Correct that record, or check "
            "the date."
        ),
        "duplicate_field": DATE_FIELD,
    },
}


def correction_options():
    """The vocabularies the confirmation dialog offers. Read by Patient Profile.

    Rendered from the same constants the entry forms render from, so the dialog
    cannot offer a vaccine the models would refuse or omit one they accept.
    """
    return {
        "epi_kind": EPI_KIND,
        "general_kind": GENERAL_KIND,
        "kind_field": KIND_FIELD,
        "record_field": RECORD_FIELD,
        "vaccine_field": VACCINE_FIELD,
        "name_field": NAME_FIELD,
        "dose_field": DOSE_FIELD,
        "date_field": DATE_FIELD,
        # Every scheduled dose, in schedule order, as (posted key, printed label).
        "epi_doses": [
            {"key": f"{code}:{dose_number}", "label": dose_label(code, dose_number)}
            for code, _v, _p, dose_number, _t, _val, _u, _n in EPI_SCHEDULE
        ],
        # The convenience list the consultation form ticks, offered here as
        # suggestions rather than as a closed set -- this table stores a typed
        # name, so the dialog must accept one.
        "common_vaccine_names": [name for _key, name, _protects in COMMON_VACCINES],
        "dose_range": DOSE_RANGE,
        "max_name_length": MAX_NAME_LENGTH,
        # The dialog's own date cap. The server re-checks it in _validate_date();
        # this only stops the picker offering a day that would be refused.
        "today": today(),
    }


def _reopen(kind, record_id, record, form_data, errors, banner):
    """The dialog's state after a submit that did not save.

    Everything the reopened dialog needs to come back exactly as it was left:
    which record it is correcting, what was typed into it, and what was wrong
    with each field. The same shape process_create_user() hands User Management
    and process_register_patient() hands Register Patient.

    `current` is the record as it is STORED, and it is here because two of these
    fields cannot be redisplayed from what was posted. The EPI vaccine arrives as
    a "CODE:DOSE" pair and the only way it fails is by not being a pair the
    schedule lists -- so there is no option to re-select, and the select falls
    back to the pair the record actually holds. The subject line likewise
    describes the record, not the attempt. Everything the operator genuinely
    typed -- the name, the dose number, the date -- comes back from `form`.
    """
    return {
        "open": True,
        "kind": kind,
        "record_id": record_id,
        "errors": errors,
        "banner": banner,
        "form": {
            VACCINE_FIELD: str(form_data.get(VACCINE_FIELD) or "").strip(),
            NAME_FIELD: str(form_data.get(NAME_FIELD) or "").strip(),
            DOSE_FIELD: str(form_data.get(DOSE_FIELD) or "").strip(),
            DATE_FIELD: str(form_data.get(DATE_FIELD) or "").strip(),
        },
        "current": {
            "vaccine_key": (
                f"{record['vaccine_code']}:{record['dose_number']}"
                if kind == EPI_KIND
                else ""
            ),
            "label": KINDS[kind]["label"](record),
            "recorded_by": record["administered_by_name"],
            # Carried so the reopened dialog says the same thing about this
            # record's date that the dialog opened from the button says. Only an
            # EPI row has a source; a general vaccination is always one the
            # health center gave and its date is always required.
            "reported": bool(record.get("reported")),
            "source_label": record.get("source_label") or "",
        },
    }


def process_vaccination_correction(form_data, user_id, ip_address=None):
    """Apply one correction and record it in the audit trail.

    Returns (patient_id, reopen, message).

    `reopen` is the dialog's state after a submit that did not save, and it is
    the one of the three that decides what the caller does. When it is set the
    caller re-renders Patient Profile with the correction dialog open on what was
    typed, with the errors beside the fields they belong to, and flashes nothing;
    `message` is None in that case because the dialog carries its own banner.
    When it is None the outcome is terminal -- saved, or refused for a reason no
    amount of retyping fixes -- so the caller flashes `message` and redirects to
    the profile. A patient_id of None means it could not resolve one and the
    caller should fall back to Patient Records.

    WHY A FAILED CORRECTION NOW REDISPLAYS RATHER THAN REDIRECTING.
    It used to flash one sentence naming every problem and send the operator back
    to the profile with the dialog shut. That was a defensible reading -- the
    record is untouched and the page behind is still correct -- and it was the
    last form in the project that did it, which is what settled it. A correction
    is typed into three fields chosen with some care; throwing them away to
    deliver an error that names them is the one thing every other form here stops
    doing. Consistency is the argument, and it is a real one: an operator should
    not have to know which dialog in this system keeps their work.

    Everything the dialog claims is re-established here rather than trusted. The
    kind is checked against KINDS, the record is re-read from the table, the
    patient is re-read from the record rather than from the form, and the
    submitted values are validated as strictly as the original entry was. A POST
    can arrive without the page ever having been loaded, and the page it was
    loaded from may since have gone stale -- the same reasoning
    process_archive_patients() states for the status dialog.

    The audit entry is written from the values read back AFTER the update rather
    than from what the form asked for, so it describes what the record actually
    holds now. Nothing is logged when nothing moved: a correction that changed no
    field is not an event, and logging it would bury the ones that matter. That
    is the rule process_edit_consultation() follows and this is the same rule.
    """
    kind = str(form_data.get(KIND_FIELD) or "").strip().lower()
    spec = KINDS.get(kind)
    if spec is None:
        return None, None, "That is not a kind of record this system can correct."

    raw_id = str(form_data.get(RECORD_FIELD) or "").strip()
    if not raw_id.isdigit():
        return None, None, "Choose the vaccination record to correct."
    record_id = int(raw_id)

    before_record = spec["fetch"](record_id)
    if before_record is None:
        return None, None, "That vaccination record could not be found."

    patient = get_patient_by_id(before_record["patient_id"])
    if patient is None:
        return None, None, "That patient record could not be found."

    patient_id = patient["id"]
    original_label = spec["label"](before_record)

    values, errors = spec["parse"](form_data, before_record, patient)
    if errors:
        # The dialog comes back on what was typed, with each message beside the
        # field it is about, rather than one flash naming every problem over a
        # dialog that has shut. The record is untouched either way -- what
        # changed is that the operator keeps the edit they were part-way through.
        return patient_id, _reopen(
            kind, record_id, before_record, form_data, errors,
            "{} was not corrected. Correct the {} highlighted field{} below. "
            "Nothing has been saved.".format(
                original_label,
                len(errors),
                "" if len(errors) == 1 else "s",
            ),
        ), None

    outcome = spec["apply"](record_id, values)
    if outcome == "missing":
        return patient_id, None, "That vaccination record could not be found."
    if outcome == "date_required":
        # The model's own refusal, reached only if a record's source changed
        # between _parse_epi() reading it and correct_immunization() writing --
        # or if a POST reached here by some path that skipped the parse. Reopened
        # like any other field error rather than flashed away, because it is
        # fixed by typing a date into the dialog that is still on screen.
        refusal = (
            "A dose recorded as given at this health center must say when it "
            "was given. Enter the date, or leave the record as it is. Nothing "
            "has been saved."
        )
        return patient_id, _reopen(
            kind, record_id, before_record, form_data,
            {DATE_FIELD: refusal}, refusal,
        ), None
    if outcome == "duplicate":
        # A conflict, not a mistyping -- but it is fixed the same way the field
        # errors above are, by changing what is in the dialog and saving again.
        # So it reopens too, with the sentence on the field that identifies the
        # clashing record: the dose for an EPI record, the date for a general one,
        # which is what each kind's message already tells the operator to check.
        conflict = spec["duplicate"].format(
            patient=patient["full_name"], label=spec["submitted_label"](values)
        ) + " Nothing has been saved."
        return patient_id, _reopen(
            kind, record_id, before_record, form_data,
            {spec["duplicate_field"]: conflict}, conflict,
        ), None

    after_record = spec["fetch"](record_id)
    labels = _labels_for(kind)
    summary, changed = describe_changes(
        _snapshot(kind, before_record),
        _snapshot(kind, after_record),
        labels,
        formatters=_FORMATTERS,
    )

    if not changed:
        return patient_id, None, (
            f"No change. {original_label} for {patient['full_name']} is "
            "unchanged, and nothing has been written to the audit log."
        )
    # The entry names the corrected fields and never their values (Task 5c):
    # which vaccine a named patient had, and when, is an immunization record, and
    # Audit Logs are read by the Administrator, who is not part of their care.
    summary = "Changed: " + ", ".join(labels[field] for field in changed)

    # Self-contained on purpose, exactly as the consultation entry is: read
    # months later, on its own, it must say which record was touched, whose it
    # is, who recorded it in the first place and what moved -- without anyone
    # having to open the profile to find out. The consultation anchor is named
    # when there is one, because a corrected date that no longer matches the
    # visit it was recorded at is a thing a reviewer will want to see.
    anchor = (
        f" during consultation #{before_record['consultation_id']}"
        if before_record.get("consultation_id")
        else " outside any consultation"
    )
    details = (
        f"{spec['noun']} #{record_id} for {patient['full_name']} "
        f"({patient['patient_id']}){anchor}. {len(changed)} field"
        f"{'s' if len(changed) != 1 else ''} corrected — {summary}"
    )
    log_action(
        user_id=user_id,
        action=spec["action"],
        module=MODULE_IMMUNIZATIONS,
        details=details,
        ip_address=ip_address,
    )

    field_names = ", ".join(labels[field].lower() for field in changed)
    corrected_label = spec["label"](after_record)
    subject = original_label
    if corrected_label != original_label:
        subject = f"{original_label} corrected to {corrected_label}"
    else:
        subject = f"{original_label} corrected"
    return patient_id, None, (
        f"{subject} for {patient['full_name']} — {len(changed)} field"
        f"{'s' if len(changed) != 1 else ''} changed ({field_names}). "
        "The correction has been recorded in the audit log."
    )

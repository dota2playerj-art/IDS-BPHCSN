"""Vaccinations given to any patient, at any age, with no schedule attached.

WHY THIS IS NOT PART OF models/immunizations.py
------------------------------------------------
Two different clinical questions, deliberately kept apart:

    "was this vaccine given?"        record-keeping. True of any patient of any
                                     age -- a 19-year-old having a hepatitis B
                                     dose is exactly as real a clinical event as
                                     an infant having one.

    "is this patient on schedule?"   evaluation. Only answerable where an
                                     official schedule genuinely exists. In the
                                     Philippines that is the DOH Expanded Program
                                     on Immunization infant schedule, which
                                     covers children under five and nobody else.

models/immunizations.py answers the second, and to do it it needs the first as
well -- so it stores doses *and* grades them. That is correct for the cohort the
EPI schedule describes and wrong for everyone else: there is no single national
adult immunisation schedule to grade an adult against, so any due/overdue reading
this module produced would be invented. It therefore produces none. There is no
due date, no grace period, no status badge and no "overdue" anywhere in this
file, and that absence is the design rather than an omission.

This is the same separation the HL7 FHIR standard draws between Immunization
(the administration that happened) and ImmunizationRecommendation (a forecast a
schedule produces). Only the first kind of record is written here.

The consequence worth stating plainly: before this module existed, an adult who
received a vaccine at the health center had nowhere in the system for it to go.
The EPI screens quite correctly refused them -- they are not the EPI cohort --
and there was no second place to look. The dose simply was not recorded.


WHY THERE IS NO SCHEDULE CONSTANT HERE
--------------------------------------
COMMON_VACCINES below is a *convenience list for the entry form*, not policy. It
is what the health center gives often enough to be worth a tick box, and it ends
in a free-text row precisely because it does not claim to be exhaustive. Nothing
reads it to decide anything about a patient; the row that gets stored carries the
vaccine's name as text, so a vaccine nobody anticipated is recorded exactly as
well as one on the list.

That is the opposite of EPI_SCHEDULE, which *is* national policy, is closed, and
is the yardstick every EPI status is measured against. Storing a name here rather
than a code is the same decision read from the other side: a code only earns its
keep when something looks the record up, and nothing looks these up.


WHAT IS STORED, AND WHAT IS NOT
-------------------------------
Patient, vaccine name, an optional dose number, the date, who gave it, and the
consultation it was given during -- the same anchoring the EPI table uses, so a
visit's record is complete read from either direction.

dose_number is nullable, unlike the EPI table's, because most of these have no
fixed dose count. "Influenza" is one shot a year forever; a Td booster is not
"dose 3 of 3" of anything a barangay health station tracks. Requiring a number
would force a health worker to invent one, and an invented number in a clinical
record is worse than an absent one.
"""
from database.connection import get_db

# (key, name, protects_against) -- the vaccines the entry form offers as tick
# boxes. `key` is what the form posts and is never stored; `name` is what is
# stored and printed. Ordered by how often a barangay health station gives them.
#
# This list can grow freely: adding a row adds a tick box and nothing else, and
# removing one orphans not a single stored record, because records hold the name
# rather than the key.
COMMON_VACCINES = (
    ("hepatitis-b",  "Hepatitis B",   "Hepatitis B"),
    ("tetanus-td",   "Tetanus / Td",  "Tetanus, diphtheria"),
    ("influenza",    "Influenza",     "Seasonal influenza"),
    ("pneumococcal", "Pneumococcal",  "Pneumococcal disease"),
    ("covid-19",     "COVID-19",      "COVID-19"),
    ("rabies",       "Rabies",        "Rabies"),
)

VACCINE_NAMES = {key: name for key, name, _ in COMMON_VACCINES}
VACCINE_KEYS = frozenset(VACCINE_NAMES)

# The free-text row. Its name comes from the operator rather than the list, which
# is what keeps the list a convenience instead of a limit.
OTHER_KEY = "other"

# The longest a typed vaccine name may be. Long enough for the real ones
# ("Japanese encephalitis", "Typhoid (Vi polysaccharide)") and short enough that
# the field cannot be used as a notes box -- the consultation already has one of
# those, and a paragraph filed as a vaccine name would print as one on every
# screen that lists it.
MAX_NAME_LENGTH = 60

# A dose number, when there is one at all. Five covers the longest series the
# health center actually gives (rabies post-exposure); ten leaves headroom for a
# genuinely long course without letting a mistyped year through as a dose.
DOSE_RANGE = (1, 10)


def dose_field(key):
    """The form field carrying the dose number for one row."""
    return "general_dose_" + key


# What the consultation form posts. Named here so the template, the parser and
# the error messages cannot disagree about a field name.
VACCINE_FIELD = "general_vaccinations"
OTHER_NAME_FIELD = "general_vaccine_other"

# Labels for the error summary at the top of the consultation form, which prints
# `field_labels.get(field, field)` and would otherwise show a raw field name.
FIELD_LABELS = dict(
    [(OTHER_NAME_FIELD, "Other vaccine name")]
    + [(dose_field(key), name + " dose number") for key, name, _ in COMMON_VACCINES]
    + [(dose_field(OTHER_KEY), "Other vaccine dose number")]
)


def vaccination_label(vaccine_name, dose_number):
    """'Influenza', or 'Rabies dose 3' when a dose number was recorded.

    The one place a general vaccination is turned into words, so the profile
    list, the consultation form and the audit line all name it identically --
    the same job dose_label() does for the EPI schedule.
    """
    name = str(vaccine_name or "").strip() or "Vaccination"
    if dose_number is None:
        return name
    return "{} dose {}".format(name, dose_number)


def clean_vaccine_name(raw):
    """Collapse a typed vaccine name to the single form that gets stored.

    Public rather than module-private because it now has a second caller. The
    correction path in routes/vaccination_correction_views.py cleans a corrected
    name through this exact function rather than through a copy of it, so a
    vaccine name put right months later is normalised the same way the one first
    recorded was -- a correction must not be a route around the validation the
    original entry passed.
    """
    return " ".join(str(raw or "").split())[:MAX_NAME_LENGTH]


def clean_dose_number(raw):
    """'3' -> (3, True); '' -> (None, True); anything else -> (None, False).

    Public for the reason clean_vaccine_name() above is: the correction dialog
    range-checks a corrected dose number through this same function.
    """
    text = str(raw or "").strip()
    if not text:
        return None, True
    if not text.isdigit():
        return None, False
    value = int(text)
    low, high = DOSE_RANGE
    if not (low <= value <= high):
        return None, False
    return value, True


def _ticked_keys(form_data):
    """The rows whose tick box came back, deduplicated and in form order."""
    raw_values = (
        form_data.getlist(VACCINE_FIELD)
        if hasattr(form_data, "getlist")
        else (form_data.get(VACCINE_FIELD) or [])
    )
    ticked = []
    for raw in raw_values:
        key = str(raw or "").strip().lower()
        if (key in VACCINE_KEYS or key == OTHER_KEY) and key not in ticked:
            ticked.append(key)
    # Back into the order the section prints, so a flash message and an audit
    # line list a visit's vaccinations the way the form reads.
    order = [key for key, _, _ in COMMON_VACCINES] + [OTHER_KEY]
    ticked.sort(key=order.index)
    return ticked


def parse_general_vaccinations(form_data):
    """Read the "Other Vaccinations Given" section. Returns (entries, errors).

    `entries` is [{'key', 'vaccine_name', 'dose_number'}] in the order the form
    lists them; `dose_number` is None when none was given, which is the common
    case and not an error.

    `errors` is {field: message}, merged by the caller into the consultation's
    own errors so one refusal summary covers the whole form.

    This is the gate between the form and the table. A key the list does not
    contain is dropped rather than stored, so a hand-made POST cannot file a dose
    under a vaccine this form never offered -- the same refusal parse_dose_keys()
    gives the EPI checkboxes. The one row whose name is not fixed is the
    free-text row, and that name is whitespace-collapsed and length-capped before
    it is trusted.
    """
    ticked = _ticked_keys(form_data)
    other_name = clean_vaccine_name(form_data.get(OTHER_NAME_FIELD))

    entries, errors = [], {}

    for key in ticked:
        if key == OTHER_KEY:
            if not other_name:
                errors[OTHER_NAME_FIELD] = (
                    "Name the vaccine that was given, or untick Other vaccine."
                )
                continue
            name = other_name
        else:
            name = VACCINE_NAMES[key]

        dose_number, ok = clean_dose_number(form_data.get(dose_field(key)))
        if not ok:
            low, high = DOSE_RANGE
            errors[dose_field(key)] = (
                "Enter the dose number as a whole number between {} and {}, or "
                "leave it blank if this vaccine has no dose count.".format(low, high)
            )
            continue

        entries.append({"key": key, "vaccine_name": name, "dose_number": dose_number})

    # A name typed into the free-text box with the box left unticked is a save
    # about to silently discard what somebody entered. Say so rather than drop it.
    if other_name and OTHER_KEY not in ticked:
        errors[OTHER_NAME_FIELD] = (
            "Tick Other vaccine to record {}, or clear the name.".format(other_name)
        )

    return entries, errors


def get_general_vaccinations_for_patient(patient_id):
    """Every general vaccination on file for one patient, most recent first.

    Newest first, unlike the EPI dose list: that one is read against a schedule
    that runs in order from birth, while this is a plain history whose most
    useful line is the last thing the patient was given.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT g.id, g.patient_id, g.consultation_id, g.vaccine_name, g.dose_number,
               g.date_administered, g.administered_by, g.created_at,
               u.full_name AS administered_by_name
        FROM general_vaccinations g
        JOIN users u ON u.id = g.administered_by
        WHERE g.patient_id = ?
        ORDER BY g.date_administered DESC, g.id DESC
        """,
        (patient_id,),
    ).fetchall()
    conn.close()
    records = [dict(row) for row in rows]
    for record in records:
        record["label"] = vaccination_label(record["vaccine_name"], record["dose_number"])
    return records


def get_general_vaccinations_for_consultation(consultation_id):
    """The general vaccinations recorded during one visit, oldest row first."""
    if not consultation_id:
        return []
    conn = get_db()
    rows = conn.execute(
        """
        SELECT g.id, g.vaccine_name, g.dose_number, g.date_administered,
               u.full_name AS administered_by_name
        FROM general_vaccinations g
        JOIN users u ON u.id = g.administered_by
        WHERE g.consultation_id = ?
        ORDER BY g.id
        """,
        (consultation_id,),
    ).fetchall()
    conn.close()
    records = [dict(row) for row in rows]
    for record in records:
        record["label"] = vaccination_label(record["vaccine_name"], record["dose_number"])
    return records


def record_general_vaccinations(patient_id, entries, administered_by,
                                date_administered, consultation_id=None):
    """Write the general vaccinations given at one visit. Returns what was stored.

    INSERT OR IGNORE against UNIQUE (patient_id, vaccine_name, date_administered):
    the same vaccine, to the same patient, on the same day is one event however
    many times the form is submitted. Unlike the EPI table there is no constraint
    spanning dose numbers -- influenza recurs every year and a Td booster a decade
    later is a new dose, not a duplicate -- so the date is what makes a row
    unique. See migrate_add_general_vaccinations.py for the full reasoning.

    Returns the entries actually stored, so a caller names what it wrote rather
    than what it asked for.
    """
    if not entries:
        return []

    day = date_administered
    day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    stored = []
    conn = get_db()
    for entry in entries:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO general_vaccinations
                (patient_id, consultation_id, vaccine_name, dose_number,
                 date_administered, administered_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (patient_id, consultation_id, entry["vaccine_name"],
             entry["dose_number"], day, administered_by),
        )
        if cursor.rowcount:
            stored.append(entry)
    conn.commit()
    conn.close()
    return stored


def get_general_vaccination_by_id(record_id):
    """One recorded vaccination by primary key, or None.

    The mirror of models.immunizations.get_immunization_by_id(), down to what it
    deliberately leaves out: the patient is resolved by the caller through
    models.patients.get_patient_by_id() so a corrected record is named by the
    same full_name builder every other screen uses.
    """
    conn = get_db()
    row = conn.execute(
        """
        SELECT g.id, g.patient_id, g.consultation_id, g.vaccine_name, g.dose_number,
               g.date_administered, g.administered_by, g.created_at,
               u.full_name AS administered_by_name
        FROM general_vaccinations g
        JOIN users u ON u.id = g.administered_by
        WHERE g.id = ?
        """,
        (record_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def correct_general_vaccination(record_id, vaccine_name, dose_number, date_administered):
    """Correct one recorded vaccination's name, dose number and date.

    Returns "corrected", "missing" or "duplicate", exactly as
    models.immunizations.correct_immunization() does -- one vocabulary for both
    halves of the correction path, so the shared flow that calls them does not
    have to know which table it is talking to.

    The duplicate this one can hit is a different constraint from the EPI table's
    and catches a different mistake. Here it is UNIQUE (patient_id, vaccine_name,
    date_administered): correcting a row onto a vaccine and date the patient
    already has on file would be claiming the same shot twice. The dose number is
    outside the constraint on purpose -- influenza recurs yearly and a Td booster
    a decade later is a new dose, not a duplicate, so the date is what makes a row
    unique here. See migrate_add_general_vaccinations.py.

    THIS FILE NOW HAS A WRITER THAT IS NOT AN INSERT, AND THAT IS A CHANGE WORTH
    NAMING. Until now the module's only writer was record_general_vaccinations(),
    and routes/consultation_views.py's _apply_general_vaccination_edit() said in
    as many words that there is no removal function here at all -- a step further
    than the EPI module goes -- because "an unused DELETE is a thing that can be
    called by mistake". That still holds: there is no DELETE here and this is not
    one. An UPDATE that moves three named columns on a row that keeps existing is
    the correction the add-only forms deliberately left to a path of its own, and
    the row survives it. Nothing in this module can make a vaccination record
    disappear.
    """
    day = date_administered
    day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    conn = get_db()
    row = conn.execute(
        "SELECT patient_id FROM general_vaccinations WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return "missing"

    clash = conn.execute(
        """
        SELECT id FROM general_vaccinations
         WHERE patient_id = ? AND vaccine_name = ? AND date_administered = ?
           AND id <> ?
        """,
        (row["patient_id"], vaccine_name, day, record_id),
    ).fetchone()
    if clash is not None:
        conn.close()
        return "duplicate"

    conn.execute(
        """
        UPDATE general_vaccinations
           SET vaccine_name = ?, dose_number = ?, date_administered = ?
         WHERE id = ?
        """,
        (vaccine_name, dose_number, day, record_id),
    )
    conn.commit()
    conn.close()
    return "corrected"

"""Context for Screen 02 (Administrator) and Screen 14 (Health Center Staff).

One builder for both, for the reason every other shared screen in this project
has one: the two dashboards report several of the same figures -- today's queue,
low stock, immunisation defaulters -- and two builders would eventually disagree
about them while each looked right on its own.

Nothing here counts anything itself. Every number is read from the model function
that already owns it and that some other screen is already reporting from, so a
dashboard card and the screen it links to cannot show different totals:

    patients            models/patients.py       get_patient_stats()
    today's queue       models/appointments.py   get_todays_appointments/get_queue_stats
    consultations       models/consultations.py  get_consultation_stats/get_consultation_report
    inventory           models/inventory.py      get_inventory_stats/get_low_stock_alert
    immunisation        models/immunizations.py  get_immunization_alert()
    broadcasts          models/broadcasts.py     get_broadcast_stats/audience_options
    system activity     models/audit.py          get_audit_logs/get_audit_stats

WHAT THESE SCREENS CANNOT SHOW
------------------------------
Both dashboards were drawn with panels the schema has no source for. They are
listed in UNTRACKED and the templates print the reason next to the panel rather
than the mockup figure that used to sit there -- the rule Screen 03's Prenatal
card set and Screen 10 follows.
"""
from models.appointments import (
    get_active_consultation,
    get_calendar_month,
    get_queue_stats,
    get_todays_appointments,
    queue_display_name,
)
from models.audit import get_audit_logs, get_audit_stats
from models.broadcasts import audience_options, get_broadcast_stats
from models.consultations import (
    PEDIATRIC_AGE_YEARS,
    get_consultation_report,
    get_consultation_stats,
)
from models.dispensing import get_dispensing_by_consultation, get_dispensing_stats
from models.immunizations import get_immunization_alert
from models.inventory import get_inventory_stats, get_low_stock_alert
from models.patients import (
    format_age,
    get_all_patients,
    get_patient_stats,
    get_registration_trend,
)
from utils.dates import to_clinic_time, today
from models.doctor_worklist import count_waiting_for_doctor, get_waiting_for_doctor
from utils.roles import holds_clinical_authority, is_care_team
from utils.security import current_role

# How many rows each dashboard list shows before it stops.
RECENT_CONSULTATIONS = 5
RECENT_REGISTRATIONS = 3
ACTIVITY_EVENTS = 5
ALERT_ROWS = 5
# Six months, matching TREND_MONTHS on Screen 10 so the dashboard's mini charts
# and the full report plot the same window.
TREND_MONTHS = 6

UNTRACKED = {
    # THERE IS NO "dispensing" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said dispensing is not recorded, and that units dispensed per month and
    # the medicine given at a consultation could not be recovered. Both of those
    # were exactly what this dashboard was missing, and both are now recorded:
    # medicine_dispensing holds one row per issue, anchored to the consultation
    # that justified it. So the Medicine Units Dispensed chart plots a real
    # series and the Medicine column on Recent Consultations reads a real value,
    # and the reason that explained their absence goes with the absence. See the
    # matching note in routes/report_views.UNTRACKED for what its removal does
    # *not* claim -- supplies and equipment leaving the store are still not
    # recorded anywhere.
    "notifications": (
        "Per-user notifications are not recorded. There is no notifications "
        "table and nothing writes one, so this panel would have to invent its "
        "own alerts. The live alerts on this page -- low stock and immunisation "
        "follow-up -- are the real ones."
    ),
    "staff_activity": (
        "Per-staff totals are not shown here. Audit Logs records who registered, "
        "checked in, recorded, dispensed or changed stock, but this dashboard "
        "does not add them up per person."
    ),
    # THERE IS NO "consultation_status" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said a consultation has no status of its own and pointed at the visit
    # on the Patient Queue for the outcome. Nothing quotes it. The Status
    # column on the Recent Consultations table prints "Recorded" -- which is a
    # fact about the row rather than a gap in the system: a consultation that is
    # in this table is one that was written up, and that is all the column ever
    # claimed. So the cell states it in the template, the way user_views.py's
    # "Never signed in" does, and the reason that used to be quoted beside it
    # goes rather than sitting here explaining an absence the screen no longer
    # has. A reason with nothing quoting it is exactly the drift
    # utils/unavailable.py exists to prevent.
}


def _recent_registrations(limit):
    """The newest patient records, by when they were created.

    Sorted here rather than in SQL because get_all_patients() already returns the
    roster with full_name, initials and age derived, and re-querying would mean a
    second definition of what a patient row looks like.
    """
    roster = [p for p in get_all_patients() if p.get("created_at")]
    roster.sort(key=lambda p: str(p["created_at"]), reverse=True)
    rows = []
    for patient in roster[:limit]:
        stamp = to_clinic_time(patient["created_at"])
        rows.append({
            **patient,
            "registered_time": stamp.strftime("%I:%M %p").lstrip("0") if stamp else "",
            "registered_date": stamp.strftime("%b %d, %Y") if stamp else "",
        })
    return rows


def _recent_consultations(limit, reference):
    """The latest visits written up, with the age the patient was on the day.

    The Medicine column on this table printed an em dash for the whole life of
    the project, with UNTRACKED["dispensing"] under the table saying why. It now
    reads what was actually handed over at each visit.

    One query for the whole panel rather than one per row:
    get_dispensing_by_consultation() takes the five consultation ids this table
    is already holding and returns their issues grouped. A five-row panel that
    issued six queries would be the kind of quiet cost that only shows up once
    the register is large.
    """
    role = current_role()
    entries = get_consultation_report(role, limit=limit)["entries"]
    dispensed = get_dispensing_by_consultation(
        (entry.get("id") for entry in entries), role
    )
    rows = []
    for entry in entries:
        stamp = to_clinic_time(entry.get("created_at"))
        issues = dispensed.get(entry.get("id"), [])
        rows.append({
            **entry,
            # Named in full rather than counted. "2 medicines" in a column headed
            # Medicine tells a reader nothing they came to this table for.
            "medicines": issues,
            "medicines_text": ", ".join(record["label"] for record in issues),
            "full_name": f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip(),
            # format_age(), not calculate_age(): this column prints the value,
            # and the numeric form is what makes an infant read as "0".
            "age": format_age(entry.get("birth_date"), on_date=reference),
            "recorded_time": stamp.strftime("%I:%M %p").lstrip("0") if stamp else "—",
        })
    return rows


def _immunization_alert(care_team):
    """The immunization figure: the list for the care team, counts for anyone else."""
    alert = get_immunization_alert(limit=ALERT_ROWS)
    if care_team:
        return alert
    return {key: value for key, value in alert.items() if key != "children"}


def _activity_feed(limit):
    """Recent audit entries, as the dashboard's System Activity list.

    The same rows Screen 12 shows. This panel used to hold five invented events;
    it now shows what was actually done, or says the trail is empty.
    """
    events = []
    for entry in get_audit_logs(limit=limit):
        stamp = to_clinic_time(entry.get("created_at"))
        events.append({
            **entry,
            "when": (f"{stamp.strftime('%b %d')} · "
                     f"{stamp.strftime('%I:%M %p').lstrip('0')}") if stamp else "—",
        })
    return events


def dashboard_context():
    """Everything both dashboards render. Neither adds a figure of its own."""
    reference = today()
    # Clinical lists are the care team's (Task 5c). For the Administrator this
    # builder reads counts only: no recent consultation, and no child named with
    # the dose they are due.
    care_team = is_care_team(current_role())

    # Resolved once and handed to both, for the reason spelled out at the
    # active-consultation block below: the queue's flow fields, its stat cards
    # and this dashboard's shortcut all have to be answering from one reading of
    # who holds the room, or they can contradict each other on the same page.
    active = get_active_consultation()
    queue = get_todays_appointments(active=active)
    queue_stats = get_queue_stats(queue, active=active)
    patient_stats = get_patient_stats()
    consultation_stats = get_consultation_stats(months=TREND_MONTHS,
                                                viewer_role=current_role())
    dispensing_stats = get_dispensing_stats(months=TREND_MONTHS,
                                            viewer_role=current_role())
    inventory_stats = get_inventory_stats()

    # THE ONE VISIT IN PROGRESS, FOR THE DASHBOARD SHORTCUT.
    #
    # Recording a consultation is reached through the Patient Queue, and
    # that is the right primary route -- the visit belongs to the appointment, so
    # the appointment is where it starts. What it is not is a good route back
    # into a consultation already under way: a clinician who navigated away has
    # to reload the queue and find the row again, mid-visit, with the patient
    # sitting there.
    #
    # So this is a shortcut, not a second way to start one. It only ever names a
    # consultation the queue has already started, and it disappears the moment
    # that visit is completed.
    #
    # get_active_consultation() is the same call the Patient Queue uses to
    # decide who may start a consultation, and it is deliberately not scoped to
    # today -- see its docstring. Reusing it means the dashboard and the queue
    # can never disagree about whether the room is occupied. It is read once at
    # the top of this function and used here.

    # Visits waiting for the Doctor (Task 6, M4). One rule in models/doctor_worklist.py
    # for all three readers. The Doctor gets the list, with names. Health Center
    # Staff and the Administrator get the count only, and for them no name is read.
    doctor = holds_clinical_authority(current_role())
    waiting_for_doctor = get_waiting_for_doctor() if doctor else None
    waiting_for_doctor_count = (len(waiting_for_doctor) if doctor
                                else count_waiting_for_doctor())

    return {
        "clinic_date": reference,
        "waiting_for_doctor": waiting_for_doctor,
        "waiting_for_doctor_count": waiting_for_doctor_count,
        "patient_stats": patient_stats,
        "queue": queue if care_team else [],
        "queue_stats": queue_stats,
        # None when nobody is in consultation, which both dashboards render as a
        # stated "nobody right now" rather than an empty panel.
        "active_consultation": active,
        # Named through the one helper the queue and the flash messages use, so
        # the shortcut cannot spell a patient differently from the row it came
        # from.
        "active_consultation_name": queue_display_name(active),
        "consultation_stats": consultation_stats,
        "recent_consultations": (
            _recent_consultations(RECENT_CONSULTATIONS, reference) if care_team else []
        ),
        "recent_registrations": _recent_registrations(RECENT_REGISTRATIONS),
        "inventory_stats": inventory_stats,
        "low_stock": get_low_stock_alert(limit=ALERT_ROWS),
        "immunization_alert": _immunization_alert(care_team),
        "broadcast_stats": get_broadcast_stats(),
        "audience_options": audience_options(),
        "activity": _activity_feed(ACTIVITY_EVENTS),
        # The Staff dashboard's mini calendar. Same builder Appointment
        # Scheduling draws its month grid with, so the day marked today and the
        # days marked as having appointments agree between the two screens.
        "calendar_month": get_calendar_month(),
        "audit_stats": get_audit_stats(),
        # The two mini trend charts. Emitted through | tojson by the templates,
        # exactly as Screen 10 emits its eight.
        "registration_trend": get_registration_trend(months=TREND_MONTHS),
        "consultation_trend": consultation_stats["trend"],
        # The third mini trend chart, and the one that had no source until
        # medicine_dispensing existed. Same six-month window as the two beside
        # it, from the same TREND_MONTHS, so the three x axes line up.
        "dispensing_stats": dispensing_stats,
        "dispensing_trend": dispensing_stats["trend"],
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "untracked": UNTRACKED,
    }

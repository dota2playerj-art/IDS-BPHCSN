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
    upcoming bookings   models/appointments.py   get_upcoming_appointments()
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
    get_upcoming_appointments,
    queue_display_name,
)
from models.audit import get_audit_logs, get_audit_stats
from models.broadcasts import audience_options, get_broadcast_stats
from models.consultations import (
    PEDIATRIC_AGE_YEARS,
    get_consultation_report,
    get_consultation_stats,
)
from models.immunizations import get_immunization_alert
from models.inventory import get_inventory_stats, get_low_stock_alert
from models.patients import (
    format_age,
    get_all_patients,
    get_patient_stats,
    get_registration_trend,
)
from utils.dates import to_clinic_time, today

# How many rows each dashboard list shows before it stops.
RECENT_CONSULTATIONS = 5
RECENT_REGISTRATIONS = 3
ACTIVITY_EVENTS = 5
ALERT_ROWS = 5
UPCOMING_ROWS = 5
VACCINATION_ROWS = 5

# How the Staff dashboard's vaccination panel recognises one of its own rows in
# the upcoming bookings. appointment_type is free text on the booking form, so
# this matches on what a clerk would actually type rather than on a fixed list.
VACCINATION_WORDS = ("immuniz", "immunis", "vaccin")

# Six months, matching TREND_MONTHS on Screen 10 so the dashboard's mini charts
# and the full report plot the same window.
TREND_MONTHS = 6

UNTRACKED = {
    "dispensing": (
        "Medicine dispensing is not recorded. inventory_items holds the current "
        "stock level only, with no per-issue history, so units dispensed per "
        "month and the medicine given at a consultation cannot be recovered."
    ),
    "notifications": (
        "Per-user notifications are not recorded. There is no notifications "
        "table and nothing writes one, so this panel would have to invent its "
        "own alerts. The live alerts on this page -- low stock and immunisation "
        "follow-up -- are the real ones."
    ),
    "staff_activity": (
        "Per-staff activity is not recorded for most actions. Consultations "
        "store who wrote them, but registrations, check-ins and stock edits do "
        "not, so a weekly total for one worker cannot be assembled."
    ),
    "consultation_status": (
        "A consultation has no status of its own. The visit it belongs to "
        "carries the outcome, on Appointment Scheduling."
    ),
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
    """The latest visits written up, with the age the patient was on the day."""
    entries = get_consultation_report(limit=limit)["entries"]
    rows = []
    for entry in entries:
        stamp = to_clinic_time(entry.get("created_at"))
        rows.append({
            **entry,
            "full_name": f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip(),
            # format_age(), not calculate_age(): this column prints the value,
            # and the numeric form is what makes an infant read as "0".
            "age": format_age(entry.get("birth_date"), on_date=reference),
            "recorded_time": stamp.strftime("%I:%M %p").lstrip("0") if stamp else "—",
        })
    return rows


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


def _upcoming_vaccinations(upcoming_all, limit):
    """Booked immunisation visits still to come.

    A filter over get_upcoming_appointments(), not a second query: the rows are
    the ones Appointment Scheduling already lists, narrowed to the visits that
    are about a dose. This panel is empty whenever nothing is booked, which is
    the honest answer -- the children who are *due* a dose without a booking are
    a different list, and get_immunization_alert() already reports them in the
    Immunization Follow-up panel beside it.
    """
    rows = [
        entry for entry in upcoming_all
        if any(word in str(entry.get("appointment_type") or "").lower()
               for word in VACCINATION_WORDS)
    ]
    return rows[:limit]


def dashboard_context():
    """Everything both dashboards render. Neither adds a figure of its own."""
    reference = today()

    queue = get_todays_appointments()
    queue_stats = get_queue_stats(queue)
    patient_stats = get_patient_stats()
    consultation_stats = get_consultation_stats(months=TREND_MONTHS)
    inventory_stats = get_inventory_stats()
    upcoming_all = get_upcoming_appointments()

    # THE ONE VISIT IN PROGRESS, FOR THE DASHBOARD SHORTCUT.
    #
    # Recording a consultation is reached through Appointment Scheduling, and
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
    # get_active_consultation() is the same call Appointment Scheduling uses to
    # decide who may start a consultation, and it is deliberately not scoped to
    # today -- see its docstring. Reusing it means the dashboard and the queue
    # can never disagree about whether the room is occupied.
    active = get_active_consultation()

    return {
        "clinic_date": reference,
        "patient_stats": patient_stats,
        "queue": queue,
        "queue_stats": queue_stats,
        # None when nobody is in consultation, which both dashboards render as a
        # stated "nobody right now" rather than an empty panel.
        "active_consultation": active,
        # Named through the one helper the queue and the flash messages use, so
        # the shortcut cannot spell a patient differently from the row it came
        # from.
        "active_consultation_name": queue_display_name(active),
        "upcoming": upcoming_all[:UPCOMING_ROWS],
        "upcoming_count": len(upcoming_all),
        "upcoming_vaccinations": _upcoming_vaccinations(upcoming_all, VACCINATION_ROWS),
        "consultation_stats": consultation_stats,
        "recent_consultations": _recent_consultations(RECENT_CONSULTATIONS, reference),
        "recent_registrations": _recent_registrations(RECENT_REGISTRATIONS),
        "inventory_stats": inventory_stats,
        "low_stock": get_low_stock_alert(limit=ALERT_ROWS),
        "immunization_alert": get_immunization_alert(limit=ALERT_ROWS),
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
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "untracked": UNTRACKED,
    }

"""Context for Screen 15, the Barangay Official dashboard.

Built the way routes/report_views.py and routes/dashboard_views.py are: nothing
here counts anything itself. Every figure is read from the function that already
owns it and that some other screen this role can already reach is already
reporting from, so this dashboard and the screen it links to cannot show
different totals.

WHAT THIS ROLE MAY SEE, AND WHY THAT DECIDES THE SOURCES
--------------------------------------------------------
09_UI_Architecture §2 keeps the Barangay Official out of Patient Records,
Medicine Inventory and Appointment Scheduling. This dashboard therefore draws
only from the two screens the role does hold:

    Reports & Analytics (Screen 10)   routes/report_views.py
    SMS Notifications  (Screen 09)    models/broadcasts.py

reports_analytics_context() is called rather than the models beneath it on
purpose -- it is the exact context this role is already served at
/official/reports_analytics, so no figure can appear here that the role could
not already read there. Nothing patient-identifying, nothing from the inventory
roster and nothing from the appointment queue is passed. The month grid is the
one exception and is stripped to dates only; see the template.

WHAT THIS SCREEN CANNOT SHOW
----------------------------
This screen was drawn almost entirely from invented community figures -- a
barangay population of 2,418, six health programmes, three vaccination
campaigns, twelve generated reports, five programme progress bars. None of them
has a table behind it. They are listed in UNTRACKED and the template prints the
reason where the number used to be, following the rule Screen 03's Prenatal card
set: a figure with no data source reports its own absence.

Most of those reasons are not written here. They are reports_analytics_context()'s
own UNTRACKED entries, reused, so that this screen and Screen 10 explain the
same gap in the same words.
"""
from models.appointments import get_calendar_month
from models.broadcasts import audience_options, get_broadcast_history, get_broadcast_stats
from models.consultations import PEDIATRIC_AGE_YEARS
from routes.report_views import reports_analytics_context
from utils.dates import today

# How many rows the announcement feed shows before it stops.
ANNOUNCEMENT_ROWS = 5

# The gaps specific to this screen. Everything else it cannot show is already
# named by report_views.UNTRACKED and is merged in below rather than restated.
LOCAL_UNTRACKED = {
    "population": (
        "Barangay population is not recorded. This system holds registered "
        "patients only -- 09_UI_Architecture gives it no residents table and no "
        "census import -- so a coverage figure against 'all eligible residents' "
        "has no denominator. The immunisation and senior figures beside this "
        "note are counted against the patient roster, which is a different and "
        "smaller population, and are labelled as such."
    ),
    "events": (
        "Community health events are not recorded. Nothing in the schema stores "
        "a barangay event, its date or its venue, so an events list would have "
        "to invent its own. Clinic appointments are recorded, but those belong "
        "to Appointment Scheduling and are not this role's to read."
    ),
    "campaigns": (
        "Vaccination campaigns are not recorded. Individual doses are -- see "
        "Immunization Doses Recorded above -- but nothing groups them into a "
        "named campaign with a target group, a date range or a coverage goal."
    ),
    "announcements": (
        "Announcements are SMS broadcasts. The separate Community Announcements "
        "screen was retired -- it had no store and wrote nothing -- so the "
        "messages this barangay has actually published are its broadcasts. "
        "Those are what this feed shows, and they are the same rows SMS "
        "Notifications lists."
    ),
    "delivery": (
        "Delivery is never confirmed. sms_broadcasts records what was handed to "
        "the gateway, which is where the Sent and Failed counts above come "
        "from, but nothing reports back that a handset received a message -- so "
        "there is no 'delivered' figure, and the legend that used to show one "
        "was inventing it."
    ),
    "notifications": (
        "Per-user notifications are not recorded. There is no notifications "
        "table and nothing writes one, so this panel would have to invent its "
        "own alerts."
    ),
}


def _announcement_feed(limit):
    """The community messages this barangay has actually published.

    get_broadcast_history() -- the same call behind Screen 09's history table,
    which this role already reads and writes through Compose Broadcast. See
    LOCAL_UNTRACKED["announcements"] for why this and not an announcements table.
    """
    return [dict(row) for row in get_broadcast_history(limit=limit)]


def official_dashboard_context():
    """Everything Screen 15 renders. It adds no figure of its own."""
    reports = reports_analytics_context()
    broadcast_stats = get_broadcast_stats()

    patients = reports["patient_report"]
    immunization = reports["immunization_coverage"]

    # Both dictionaries are keyed by slot, and the two have no key in common --
    # report_views owns sms/dispensing/prenatal/programs/generated_reports, this
    # module owns the five above. Merged so the template looks one up by name
    # without caring which file wrote it.
    untracked = {**reports["untracked"], **LOCAL_UNTRACKED}

    return {
        "clinic_date": today(),
        # --- Screen 10's figures, unchanged, for the cards and the two charts.
        "patient_report": patients,
        "immunization_coverage": immunization,
        "appointment_report": reports["appointment_report"],
        "consultation_stats": reports["consultation_report_stats"],
        "programs": reports["programs"],
        "senior_age": patients["senior_age"],
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "registration_trend": patients["registration_trend"],
        "trend_months": reports["trend_months"],
        # --- Screen 09's figures, for the feed and the delivery donut.
        "broadcast_stats": broadcast_stats,
        "announcements": _announcement_feed(ANNOUNCEMENT_ROWS),
        "audience_options": audience_options(),
        # Dates only once it reaches the template; the per-day booking counts
        # this also carries are deliberately not rendered for this role.
        "calendar_month": get_calendar_month(),
        "untracked": untracked,
    }

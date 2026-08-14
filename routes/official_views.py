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
from models.immunizations import (
    GRACE_PERIOD_DAYS,
    get_dose_coverage,
    get_immunization_coverage,
)
from routes.report_views import UNTRACKED, reports_analytics_context
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
    "program_schedule": (
        "Programme start and end dates are not recorded. There is no programmes "
        "table at all -- the two memberships below are counted from the patient "
        "roster and the dose records, not read from a programme that was set up "
        "somewhere -- so a launch date, a closing date, an Active/Upcoming "
        "status and a target headcount have nothing to come from."
    ),
    "non_epi_vaccines": (
        "Only the DOH EPI infant schedule is tracked. COVID-19 boosters, "
        "influenza, HPV and tetanus toxoid are not on it, and the consultation "
        "form cannot record a dose of any of them -- models/immunizations.py "
        "accepts only the schedule's own vaccine codes -- so there is no dose "
        "history behind them and no coverage to report."
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


def health_programs_context():
    """Everything Screen 16 renders.

    Same construction as the dashboard above: no figure is counted here. The
    programme list is report_views.programs -- the identical pair Screen 10 and
    the dashboard's membership panel already print -- so the three screens cannot
    report different memberships for the same programme.

    WHAT THIS SCREEN CANNOT SHOW
    ----------------------------
    It was drawn as a roster of eight barangay programmes with categories,
    target audiences, enrolment counts, statuses and 2026 date ranges. None of
    that has a table behind it: there is no programmes table, no enrolment table
    and nothing that dates a programme. Six of the eight -- Prenatal, TB DOTS,
    Nutrition, Family Planning, Oral Health and Dengue Prevention -- have no
    source of any kind, which is the same gap report_views.UNTRACKED["programs"]
    already names for Screen 10 and the dashboard, reused here rather than
    restated.

    The two that survive are the two the stored data can actually establish, and
    each carries the basis it was counted on so the reader can see it is a
    derived membership rather than an enrolment somebody recorded.
    """
    reports = reports_analytics_context()
    patients = reports["patient_report"]
    programs = reports["programs"]

    # A patient counted under both programmes would be counted twice here, so
    # this is reported as memberships rather than people -- see the template.
    membership_total = sum(program["count"] for program in programs)

    return {
        "clinic_date": today(),
        "programs": programs,
        "membership_total": membership_total,
        "patient_report": patients,
        "immunization_coverage": reports["immunization_coverage"],
        "senior_age": patients["senior_age"],
        "untracked": {**reports["untracked"], **LOCAL_UNTRACKED},
    }


def vaccination_campaigns_context():
    """Everything Screen 17 renders.

    THE CAMPAIGN CONCEPT HAS NO SOURCE, THE DOSES DO
    ------------------------------------------------
    This screen listed nine named vaccination drives, each with a target
    population, a date range, a dose count and a coverage percentage. Nothing in
    the schema groups doses into a campaign -- there is no campaign table, no
    target group and no coverage goal -- so every one of those rows, and the four
    coverage donuts under them, was invented. That gap is already named by
    LOCAL_UNTRACKED["campaigns"], written for the dashboard panel that used to
    show the same three campaigns, and it is reused here unchanged.

    What the health center does record is every dose given to every child, and
    the DOH EPI schedule says which doses each child should have had by now. So
    the real unit this screen reports is the scheduled dose, from
    get_dose_coverage() -- built on the same _roster_statuses() behind the
    dashboards' follow-up figure, so the coverage table and the "children behind
    schedule" count cannot disagree.

    The headline cards come from get_immunization_coverage(), which is what
    Screen 10 and the Barangay Official dashboard already print, for the same
    reason.
    """
    coverage = get_immunization_coverage()
    doses = get_dose_coverage()

    return {
        "clinic_date": today(),
        "immunization_coverage": coverage,
        "dose_coverage": doses,
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "grace_period_days": GRACE_PERIOD_DAYS,
        # The reason texts only; this screen needs none of Screen 10's figures,
        # so UNTRACKED is read directly rather than by running the whole report.
        "untracked": {**UNTRACKED, **LOCAL_UNTRACKED},
    }

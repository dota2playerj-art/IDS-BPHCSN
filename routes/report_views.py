"""Shared context builder for Reports & Analytics (Screen 10).

Screen 10 is rendered by two blueprints -- once for the Administrator and once
for the Barangay Official -- from the same template with the same data. The
queries live here so the two role variants cannot drift apart; the routes stay
thin and each keeps its own role_required guard.

This mirrors routes/patient_views.py, routes/inventory_views.py and
routes/appointment_views.py exactly.

Both roles receive an identical context. That is deliberate: the Barangay
Official's access to this screen is read-only by virtue of there being nothing
to write -- every route reaching it is GET, and no action on the page posts
anywhere -- rather than by handing that role a reduced set of numbers. A
statistics screen that showed the two roles different totals would be two
reports wearing one name.


WHAT THIS SCREEN CANNOT REPORT
------------------------------
Four of its panels ask for things the database has no record of, and each is
surfaced as "not yet tracked" rather than filled with a plausible number. They
are listed in UNTRACKED below with the reason, and the template renders that
list rather than hard-coding the same sentences into each panel.

The rule being followed is the one Screen 03's Prenatal card already set: a
figure with no data source reports its own absence. An invented one is worse
than a blank, because it will be read into a DOH submission and believed.
"""
from models.appointments import get_appointment_report
from models.consultations import get_consultation_stats
from models.immunizations import get_immunization_coverage
from models.inventory import get_inventory_report
from models.patients import get_patient_report
from utils.dates import today

# How many months the three trend charts cover. One constant, so the
# registration, consultation and appointment trends plot the same window and
# their x axes line up when read side by side.
TREND_MONTHS = 6

# The panels whose data does not exist anywhere in the schema, with the reason
# stated in the terms a reader of the screen would ask it in. Keyed by the slot
# on the page, so the template can look one up beside the panel it belongs to.
#
# Adding a real source for any of these means deleting its entry here and
# filling the panel -- the "not yet tracked" note disappears on its own.
UNTRACKED = {
    # Sends and failures stopped being untracked when sms_broadcasts landed.
    # Delivery did not: nothing receives Semaphore's receipts, so this entry now
    # names only the half that is still missing, and points at the screen that
    # holds the other half.
    "sms": (
        "Delivery is not recorded. sms_broadcasts stores what was handed to the "
        "Semaphore gateway -- SMS Notifications counts sends and failures from "
        "it -- but nothing reports back that a handset received a message, so "
        "there is no delivered figure to chart here."
    ),
    "dispensing": (
        "Medicine dispensing is not recorded. inventory_items holds the current "
        "stock level only, with no per-issue history, so units dispensed in a "
        "month cannot be recovered from it."
    ),
    "prenatal": (
        "Prenatal enrolment is not recorded. Nothing in the schema marks a "
        "patient as pregnant or stores an expected delivery date, so active "
        "cases, check-ups due and expected deliveries cannot be counted. "
        "Prenatal Check-up appointments are counted under Health Services "
        "Availed, which is a record of visits, not of who is enrolled."
    ),
    "programs": (
        "Programme enrolment is not recorded. There is no table linking a "
        "patient to a barangay health programme, so Family Planning, Nutrition "
        "and TB DOTS have no source at all. The two figures shown beside this "
        "note are the only programme memberships the data can actually "
        "establish."
    ),
    "generated_reports": (
        "Report exports are not recorded. Nothing writes a row when a report is "
        "printed or exported, so there is no history of generated reports to "
        "list. The audit_logs table records consultation edits only."
    ),
}


def reports_analytics_context(report_type="all"):
    """Everything Screen 10 renders, for whichever role is asking.

    Every figure comes from a function another screen already reads:
    get_patient_stats() behind Screen 03's cards, get_low_stock_alert() behind
    the sidebar badge and both dashboards, get_immunization_alert() behind the
    immunisation panels. Screen 10 issues no counting query of its own, so a
    number here that disagreed with the screen it came from would be a bug in
    that screen rather than a second opinion formed on this one.
    """
    patients = get_patient_report(months=TREND_MONTHS)
    consultations = get_consultation_stats(months=TREND_MONTHS)
    appointments = get_appointment_report(months=TREND_MONTHS)
    immunization = get_immunization_coverage()

    return {
        # Kept for the toolbar's Report Type control, which is still decorative;
        # passing it preserves the existing route signature rather than quietly
        # dropping a parameter both blueprints already send.
        "report_type": report_type,
        "report_date": today(),
        "trend_months": TREND_MONTHS,
        "patient_report": patients,
        "consultation_report_stats": consultations,
        "appointment_report": appointments,
        "immunization_coverage": immunization,
        "inventory_report": get_inventory_report(),
        # The programme memberships that can be established from stored data.
        # Deliberately only two: see UNTRACKED["programs"].
        "programs": [
            {
                "name": "Immunization",
                "count": immunization["enrolled"],
                "basis": "Patients with at least one dose recorded",
            },
            {
                "name": f"Senior Citizen ({patients['senior_age']}+)",
                "count": patients["senior_count"],
                "basis": f"Patients aged {patients['senior_age']} and above, by birthdate",
            },
        ],
        "untracked": UNTRACKED,
    }

"""Shared context builder for Reports & Analytics (Screen 10).

Screen 10 is rendered by three blueprints -- once for the Administrator, once
for the Barangay Official and once for the Doctor -- from the same template with
the same data. The queries live here so the role variants cannot drift apart;
the routes stay thin and each keeps its own role_required guard.

This mirrors routes/patient_views.py, routes/inventory_views.py and
routes/appointment_views.py exactly.

Every role receives an identical context. That is deliberate: the Barangay
Official's access to this screen is read-only by virtue of there being nothing
to write -- every route reaching it is GET, and no action on the page posts
anywhere -- rather than by handing that role a reduced set of numbers. A
statistics screen that showed two roles different totals would be two reports
wearing one name. The Doctor is given no view of their own for the same reason:
a sealed diagnosis is left out of the ranking for every viewer, the Doctor
included, and is read on the patient's record rather than here.


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
from datetime import datetime

from models.appointments import get_appointment_report
from models.broadcasts import get_broadcast_stats
from models.consultations import get_consultation_stats
from models.immunizations import get_immunization_coverage
from models.dispensing import get_dispensing_stats
from models.inventory import get_inventory_report
from models.patients import get_patient_report
from utils.dates import resolve_range, today

# How many months the three trend charts cover. One constant, so the
# registration, consultation and appointment trends plot the same window and
# their x axes line up when read side by side.
TREND_MONTHS = 6

# The longest span a generated report may cover. Not a storage limit -- the
# queries would answer a decade quite happily -- but a legibility one: the trend
# charts are 260px tall and put one bar per month on a shared axis, and past
# roughly three years the labels collide into a grey stripe. A report that has to
# be read at a glance by a health worker is the point of the feature.
MAX_REPORT_MONTHS = 36

# WHAT A DATE RANGE CAN AND CANNOT NARROW
# ---------------------------------------
# Three of this screen's panels answer questions about *now*, not about a
# period, and are left alone by the range on purpose. Stated here so the
# templates can print the reason beside the panel rather than each inventing
# its own wording, and so the decision is written down once:
#
#   inventory     inventory_items holds the current stock level only. Dispensing
#                 is now recorded per issue and IS reported over the range -- see
#                 the Dispensing section -- but that is a record of what moved,
#                 not of what the shelf held. Nothing snapshots a stock level, so
#                 "stock in March" is still not recoverable and the stock panels
#                 still report today. The two sit next to each other on the
#                 screen and answer different questions on purpose.
#   demographics  the age, sex and condition breakdowns describe who is on the
#                 register today. Narrowed to a range they would silently become
#                 "the age profile of people who registered in June", which is a
#                 real figure but not the one the panel is headed with.
#   programs      both memberships are derived from the roster and the whole
#                 dose history, for the same reason.
# Printed under eight panels across the two report screens and carried into
# both exports, so this one string is the highest-leverage sentence in the set.
# What went was the reason -- that a position on a day is not something that
# happened across a period -- which is true, and is the kind of thing a reader
# works out from the first sentence anyway.
SNAPSHOT_NOTE = (
    "Not narrowed by the selected range. This panel reports the position as it "
    "stands today, so a date range has nothing to filter here."
)

# The report types this screen offers, and which of its panels each one keeps.
# `ranged` says whether the type's figures actually move when the dates change --
# a type made only of snapshot panels would otherwise look broken when an
# operator generated it over two different ranges and got the same numbers.
ANALYTICS_REPORT_TYPES = {
    "all": {
        "label": "All Reports",
        "sections": {"registrations", "appointments", "inventory", "dispensing",
                     "sms", "programs", "demographics", "seniors", "services",
                     "consultations", "diagnoses"},
        "ranged": True,
    },
    "patients": {
        "label": "Patient Statistics",
        "sections": {"registrations", "demographics", "seniors"},
        "ranged": True,
    },
    "appointments": {
        "label": "Appointment Statistics",
        "sections": {"appointments", "services"},
        "ranged": True,
    },
    "consultations": {
        "label": "Consultation Summary",
        "sections": {"consultations", "diagnoses"},
        "ranged": True,
    },
    "inventory": {
        "label": "Medicine Inventory Status",
        "sections": {"inventory", "dispensing"},
        # This flipped from False when dispensing became real, and the reason it
        # was False is worth keeping alongside the reason it no longer is.
        #
        # It said: stock has no history, so generating this type over any range
        # returns the same figures, and the screen should say so rather than let
        # an operator conclude the range control is broken. The first half of
        # that is still exactly true -- inventory_items holds one number per item
        # and no snapshot of what it held in March -- which is why the stock
        # panels still carry SNAPSHOT_NOTE.
        #
        # What changed is that this report type is no longer made only of those
        # panels. medicine_dispensing is a movement record with a date on every
        # row, so "how much left the shelf between these two days" is now a real
        # question with a real answer, and the figures under this type *do* move
        # when the dates do. Leaving ranged False would now be the misleading
        # setting: it would tell an operator the range does nothing here while
        # half the sheet responded to it.
        "ranged": True,
    },
    "sms": {
        "label": "SMS Notification Activity",
        "sections": {"sms"},
        "ranged": True,
    },
}


def parse_report_range(args, types=None, default_type="all", months=TREND_MONTHS):
    """Turn a report screen's query string into a window, a type, and any errors.

    Both report screens read their range from the URL rather than from a POST.
    That is deliberate and buys three things:

      * Print prints what was generated. The printed sheet is this page, and this
        page is whatever the URL says, so the letterhead's range and the figures
        under it cannot come apart.
      * A generated report can be bookmarked, re-opened and handed to somebody as
        a link -- which is what "produce a report for the RHU" actually needs.
      * No new endpoint and no POST handler, so the route x role matrix is
        untouched by this feature.

    Anything unusable falls back to the default window and is reported in
    `errors` for the screen to show. A report that quietly covered a different
    range from the one typed would be worse than one that refuses.
    """
    types = types or ANALYTICS_REPORT_TYPES
    errors = []

    requested_type = (args.get("type") or "").strip() or default_type
    if requested_type not in types:
        errors.append(
            f'"{requested_type}" is not a report type this screen offers, so the '
            f'full report is shown instead.'
        )
        requested_type = default_type

    raw_from = (args.get("from") or "").strip()
    raw_to = (args.get("to") or "").strip()
    start = end = None

    if raw_from or raw_to:
        start = _parse_iso(raw_from)
        end = _parse_iso(raw_to)
        if raw_from and start is None:
            errors.append(f'"{raw_from}" is not a date this screen can read.')
        if raw_to and end is None:
            errors.append(f'"{raw_to}" is not a date this screen can read.')
        if start and not end:
            errors.append("A report needs both a start and an end date.")
        if end and not start:
            errors.append("A report needs both a start and an end date.")
        if start and end and start > end:
            errors.append(
                "The start date is after the end date, so the range covers no days."
            )
        if start and end and start <= end:
            span = (end.year - start.year) * 12 + (end.month - start.month) + 1
            if span > MAX_REPORT_MONTHS:
                errors.append(
                    f"That range covers {span} months. Reports are limited to "
                    f"{MAX_REPORT_MONTHS} so the trend charts stay readable."
                )
        if errors:
            start = end = None

    window = resolve_range(start=start, end=end, months=months)
    return {
        "window": window,
        "start": window["start"] if window["custom"] else None,
        "end": window["end"] if window["custom"] else None,
        "type": requested_type,
        "type_label": types[requested_type]["label"],
        "sections": types[requested_type]["sections"],
        "type_is_ranged": types[requested_type]["ranged"],
        "types": types,
        "errors": errors,
    }


def _parse_iso(text):
    """'2026-03-01' -> date, or None. The <input type="date"> wire format."""
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

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
        "Delivery is not recorded. What is stored is what was handed to the SMS "
        "gateway, and SMS Notifications counts sends and failures from it. "
        "Nothing reports back that a handset received a message, so there is no "
        "delivered figure to chart here."
    ),
    # THERE IS NO "dispensing" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said medicine dispensing is not recorded, that inventory_items holds a
    # stock level with no per-issue history, and that units dispensed in a month
    # could not be recovered. Every clause of that was true when it was written
    # and none of it is true now: medicine_dispensing records one row per issue,
    # with the medicine, the amount, the patient, the visit, the staff member and
    # the date, and models/dispensing.py get_dispensing_stats() answers exactly
    # the question the reason said could not be answered.
    #
    # So it goes, the way "export_pdf" and "print" went before it -- deleted once
    # true of nothing, rather than left here describing a state the application
    # has left. The panels that quoted it are filled with the real series: the
    # Dispensing section below, the Administrator dashboard's Medicine Units
    # Dispensed chart, and that dashboard's Medicine column on Recent
    # Consultations.
    #
    # What is NOT claimed by its removal, and is worth stating so nobody has to
    # re-derive it: supplies and equipment leaving the store are still not
    # recorded. models/dispensing.py dispenses items of category 'Medicine' only,
    # for the reason its header gives -- a dose issued to a patient for
    # consumption is a different event from a consumable used during a procedure.
    # That is a real remaining gap in stock movement, it is a smaller and
    # different one, and nothing on these screens claims otherwise.
    "prenatal": (
        "Prenatal enrolment is not recorded. Nothing marks a patient as pregnant "
        "or stores an expected delivery date, so active cases, check-ups due and "
        "expected deliveries cannot be counted. Prenatal Check-up appointments "
        "are counted under Health Services Availed, which is a record of visits, "
        "not of who is enrolled."
    ),
    "programs": (
        "Programme enrolment is not recorded. There is no table linking a "
        "patient to a barangay health programme, so Family Planning, Nutrition "
        "and TB DOTS have no source at all. The two figures shown beside this "
        "note are the only programme memberships the data can actually "
        "establish."
    ),
    # The last sentence has been corrected twice, and both times for the same
    # reason: it enumerates what audit_logs holds, so every new writer makes it
    # stale. It first read "records consultation edits only", which stopped being
    # true when SMS broadcast logging landed; it then read "records two things",
    # which stopped being true when routes/auth.py started recording sign-ins.
    # A list is the honest shape here -- the point of the sentence is that this
    # screen's subject is not on it -- so it is kept, and kept current.
    "generated_reports": (
        "Report exports are not recorded. Nothing is written down when a report "
        "is printed or exported, so there is no history of generated reports to "
        "list. Audit Logs records three things, and none of them is this one: "
        "consultation edits, SMS broadcasts, and sign-ins."
    ),
}


def reports_analytics_context(report_type="all", args=None):
    """Everything Screen 10 renders, for whichever role is asking.

    Every figure comes from a function another screen already reads:
    get_patient_stats() behind Screen 03's cards, get_low_stock_alert() behind
    the sidebar badge and both dashboards, get_immunization_alert() behind the
    immunisation panels. Screen 10 issues no counting query of its own, so a
    number here that disagreed with the screen it came from would be a bug in
    that screen rather than a second opinion formed on this one.

    GENERATING OVER A RANGE
    -----------------------
    `args` is the request's query string. When it names a range, the same model
    functions are called with it -- extended to take `start`/`end`, not
    duplicated into range-aware twins -- so a generated report and the default
    view are the identical code path with different dates. With no `args` this
    returns exactly what it always returned, which is what keeps the Barangay
    Official dashboard (which calls this with none) unchanged.
    """
    selection = parse_report_range(args if args is not None else {})
    window = selection["window"]
    start = selection["start"]
    end = selection["end"]

    patients = get_patient_report(months=TREND_MONTHS, start=start, end=end)
    consultations = get_consultation_stats(months=TREND_MONTHS, start=start, end=end)
    appointments = get_appointment_report(months=TREND_MONTHS, start=start, end=end)
    # Coverage is judged as of the range's closing date; the doses inside it are
    # counted between the two. See get_immunization_coverage() for why only one
    # of those two can honestly be ranged.
    immunization = get_immunization_coverage(
        on_date=end, start=start, end=end
    )

    return {
        # The type actually in force, resolved from the query string. It was a
        # decorative passthrough before; the toolbar's Report Type control now
        # selects which panels the screen renders.
        "report_type": selection["type"],
        "selection": selection,
        "report_window": window,
        "snapshot_note": SNAPSHOT_NOTE,
        "report_date": today(),
        "trend_months": TREND_MONTHS,
        "patient_report": patients,
        "consultation_report_stats": consultations,
        "appointment_report": appointments,
        "immunization_coverage": immunization,
        "inventory_report": get_inventory_report(),
        # The other half of the inventory story, and the half that has a date on
        # it. Ranged through the same start/end every other figure here uses, so
        # the dispensing chart covers exactly the window the letterhead prints.
        # Shaped like get_consultation_stats() -- all-time totals at the top,
        # the range's own answers in a `window` block -- so the template reads
        # the two the same way.
        "dispensing_stats": get_dispensing_stats(
            months=TREND_MONTHS, start=start, end=end
        ),
        # Screen 09's figures. The SMS panel here used to report only its own
        # gap; sends and failures are stored and are now counted over the range,
        # with delivery -- the half that genuinely is not recorded -- still
        # stated beside them. Screen 18 reads this rather than calling again, so
        # the two screens cannot count one barangay's broadcasts differently.
        "broadcast_stats": get_broadcast_stats(start=start, end=end),
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

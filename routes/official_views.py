"""Context for the Barangay Official screens: 15, 16, 17 and 18.

The dashboard (15) is what this module was written for; Health Programs (16),
Vaccination Campaigns (17) and Community Reports (18) joined it as each was
taken off its static markup, and all four are built the same way.
"""
from models.appointments import get_calendar_month
from models.broadcasts import audience_options, get_broadcast_history, get_broadcast_stats
from models.consultations import PEDIATRIC_AGE_YEARS
from models.immunizations import (
    GRACE_PERIOD_DAYS,
    get_dose_coverage,
    get_immunization_coverage,
)
from routes.report_views import (
    SNAPSHOT_NOTE,
    UNTRACKED,
    parse_report_range,
    reports_analytics_context,
)
from utils.dates import today

# How many rows the announcement feed shows before it stops.
ANNOUNCEMENT_ROWS = 5

# The gaps specific to this screen. Everything else it cannot show is already
# named by report_views.UNTRACKED and is merged in below rather than restated.
LOCAL_UNTRACKED = {
    # The specification reference went: a document number is not something a
    # barangay official can act on. The gap it named is unchanged -- there is no
    # residents table and no census import.
    "population": (
        "Barangay population is not recorded. Coverage figures are counted "
        "against registered patients only."
    ),
    "events": (
        "Community health events are not recorded. Nothing here stores an "
        "event, its date or its venue."
    ),
    "campaigns": (
        "Vaccination campaigns are not recorded. Individual doses are, but "
        "nothing groups them into a named campaign."
    ),
    # The retired Community Announcements screen is project history: it had no
    # store and wrote nothing, which is why broadcasts are the answer. The reader
    # of this feed never saw that screen.
    "announcements": (
        "Announcements are SMS broadcasts. This feed lists the same messages "
        "as SMS Notifications."
    ),
    "delivery": (
        "Delivery is never confirmed. Sent and Failed count what was handed to "
        "the gateway, not what a phone received."
    ),
    "notifications": (
        "Per-user notifications are not recorded. There is no notifications "
        "table and nothing writes one, so this panel would have to invent its "
        "own alerts."
    ),
    "program_schedule": (
        "Programme dates are not recorded. The two memberships below are "
        "counted from the patient roster and the dose records."
    ),
    # The source file went; the rule it enforced is the sentence. Note this is
    # about the EPI section of the consultation form only -- Other Vaccinations
    # records any vaccine by name, but not against a schedule, so there is still
    # no coverage figure to report here.
    "non_epi_vaccines": (
        "Only the DOH EPI infant schedule is counted here. Other vaccines have "
        "no coverage figure."
    ),
}


# Screen 18's Report Type menu, which was five option elements inside a disabled
# fieldset. The five labels are the ones that were already there; what is new is
# that each now names the panels it keeps and says whether its figures actually
# move when the dates change.
#
# "concerns" is the one worth reading twice. The panel it keeps is headed "Top
# Community Health Concerns", and the honest answer to that over a date range is
# in two halves: the diagnoses written up during the range, which are ranged, and
# the chronic conditions recorded against the roster, which are not -- those
# describe who is registered today. Both are shown, each labelled with which it
# is, rather than silently ranging one or silently freezing the other.
COMMUNITY_REPORT_TYPES = {
    "all": {
        "label": "Full Community Report",
        "sections": {"consultations", "registrations", "vaccination", "concerns",
                     "notifications", "appointments"},
        "ranged": True,
    },
    "consultations": {
        "label": "Monthly Consultation Summary",
        "sections": {"consultations"},
        "ranged": True,
    },
    "registrations": {
        "label": "Patient Registration Trend",
        "sections": {"registrations"},
        "ranged": True,
    },
    "vaccination": {
        "label": "Community Vaccination Summary",
        "sections": {"vaccination"},
        "ranged": True,
    },
    "concerns": {
        "label": "Top Community Health Concerns",
        "sections": {"concerns"},
        "ranged": True,
    },
    "notifications": {
        "label": "Community Notification Report",
        "sections": {"notifications"},
        "ranged": True,
    },
}


def _month_over_month(trend):
    """This month against last, read off a trend the report already built.

    Every "vs last month" figure on Screen 18 comes from here rather than from a
    second query with its own month boundary. The trend the card is compared
    against is the one plotted directly beneath it, so a card and its chart
    cannot disagree about how many consultations August holds.

    `change_pct` is None when the previous month is zero: a percentage change
    from nothing is undefined, and rendering "+1100%" -- or, worse, "+100%" --
    for the first month of a system's life is an invented figure. The template
    prints the absolute change in that case and names the month it is against.
    """
    if not trend:
        return None

    current = trend[-1]
    previous = trend[-2] if len(trend) > 1 else None
    change = current["count"] - previous["count"] if previous else None
    change_pct = (
        round(change * 100 / previous["count"])
        if previous and previous["count"] else None
    )
    return {
        "count": current["count"],
        "label": current["label"],
        "previous_count": previous["count"] if previous else None,
        "previous_label": previous["label"] if previous else None,
        "change": change,
        "change_pct": change_pct,
    }


def _ranked_conditions(conditions):
    """get_condition_counts()' rows, most common first.

    The model returns them in CONDITION_OPTIONS order because Screen 10 plots
    them against a fixed axis; a panel headed "Top Community Health Concerns"
    has to lead with the top one. This reorders that list, it does not recount
    it -- ties break alphabetically, so equal counts do not reshuffle between
    page loads. The Other row of the small-count rule (Task 5d) stays last: it
    is the remainder, not a condition to rank.
    """
    rows = conditions["counts"]
    ranked = sorted(
        (row for row in rows if not row.get("other")),
        key=lambda item: (-item["count"], item["condition"].lower()),
    )
    return ranked + [row for row in rows if row.get("other")]


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


def community_reports_context(args=None):
    """Everything Screen 18 renders.

    Built exactly as the three above are: reports_analytics_context() is called
    and nothing here counts anything itself. That matters more on this screen
    than on the others, because Community Reports is the screen a barangay
    official would read a figure off and put in front of somebody -- a number
    here that disagreed with Reports & Analytics would be two reports of one
    barangay wearing one name.

    WHAT WAS ON IT BEFORE
    ---------------------
    Nothing. The route rendered the template with no context at all, so every
    figure on it was markup: 318 consultations this month "+22 vs last month",
    63 registrations "+12%", an 83% vaccination coverage rate "across all active
    campaigns", 12 reports generated year-to-date, a six-month consultation line
    running 275-318, and a seven-bar chart of community health concerns topped by
    209 cases of the common cold. None of the seven conditions on that chart was
    read from anything, and three of them -- influenza, dengue, the common cold
    -- are not in the vocabulary this system records at all.

    WHAT IT CAN REPORT, AND WHAT IT CANNOT
    --------------------------------------
    Consultations, registrations, immunisation coverage, appointment outcomes and
    broadcast activity are all stored and are all reported here from the function
    that already owns each one.

    Two things on it are still not tracked, and both reuse a reason already
    written elsewhere rather than getting new wording:

      * how many reports have been generated, and which -- UNTRACKED
        ["generated_reports"], the same gap Screen 10's own "Recent Generated
        Reports" panel names;
      * a coverage rate against the whole barangay -- LOCAL_UNTRACKED
        ["population"]. The coverage figure this screen does show is against the
        registered children the DOH schedule applies to, and says so.

    The "all active campaigns" the old coverage card claimed to average over are
    covered by LOCAL_UNTRACKED["campaigns"], which Screen 17 already carries.
    """
    selection = parse_report_range(
        args if args is not None else {},
        types=COMMUNITY_REPORT_TYPES,
    )
    start, end = selection["start"], selection["end"]

    # The whole report is built from the one selection, so every panel on the
    # sheet covers the range the letterhead prints -- there is no second window
    # anywhere on this screen for a figure to be counted over by accident.
    reports = reports_analytics_context(args=args)
    patients = reports["patient_report"]
    consultations = reports["consultation_report_stats"]

    # No "clinic_date" and no "trend_months" here, unlike the three builders
    # above. The template prints today through inject_role_context()'s
    # clinic_today, which is what every screen in the project renders its page
    # date from, and it names its own window off the trend it is plotting rather
    # than off a separate month count -- so both keys would arrive unread.
    return {
        "selection": selection,
        "report_window": selection["window"],
        "snapshot_note": SNAPSHOT_NOTE,
        # --- Screen 10's figures, unchanged.
        "patient_report": patients,
        "consultation_report_stats": consultations,
        "appointment_report": reports["appointment_report"],
        "immunization_coverage": reports["immunization_coverage"],
        # --- The same figures asked the way this screen's cards ask them. Both
        # are read off the trends above, not counted again; see _month_over_month.
        "consultation_month": _month_over_month(consultations["trend"]),
        "registration_month": _month_over_month(patients["registration_trend"]),
        # --- get_condition_counts()' rows reordered, not recounted.
        "conditions": patients["conditions"],
        "top_conditions": _ranked_conditions(patients["conditions"]),
        # --- Screen 09's figures, over the same range, read from the report
        # rather than queried again here. This role composes and sends
        # broadcasts, so the Community Notification Report its own Report Type
        # menu offers is a real report with a real source behind it.
        "broadcast_stats": reports["broadcast_stats"],
        "untracked": {**reports["untracked"], **LOCAL_UNTRACKED},
    }

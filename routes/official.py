"""Barangay Official screens. Mounted at /official.

/official/announcements (Community Announcements) used to live here. It was
retired: it had no model, no query and no create/edit/delete endpoint -- a
static template and an unread table -- while SMS Notifications below already
covers notifying the community and keeps a real record of every send. The route
and its template are gone, so the URL now 404s. See migrate_drop_schedule_logs.py.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from routes.broadcast_views import process_send_broadcast, sms_notifications_context
from routes.official_views import (
    community_reports_context,
    health_programs_context,
    official_dashboard_context,
    vaccination_campaigns_context,
)
from routes.report_views import reports_analytics_context
from utils.security import login_required, role_required

official_bp = Blueprint("official", __name__, url_prefix="/official")


@official_bp.route('/dashboard')
@login_required
@role_required("Barangay Official")
def official_dashboard():
    """Screen 15. See routes/official_views.py for where each figure comes from
    and why this role may see it."""
    return render_template('official_dashboard.html',
                           **official_dashboard_context())


@official_bp.route('/reports_analytics')
@login_required
@role_required("Barangay Official")
def official_reports_analytics():
    """Screen 10, read-only view. 09_UI_Architecture §1 grants the Barangay Official
    community/statistical reports; every control on this screen is read or export.

    Reads the identical context the Administrator's route builds -- see
    routes/report_views.py for why the two roles are not given different numbers.
    Read-only here is a property of the route, not of the data: this is a GET,
    there is no POST counterpart anywhere in this blueprint, and nothing on the
    page submits."""
    return render_template(
        'reports_analytics.html',
        **reports_analytics_context(args=request.args),
    )


@official_bp.route('/sms_notifications')
@login_required
@role_required("Barangay Official")
def official_sms_notifications():
    return render_template('sms_notifications.html', **sms_notifications_context())


# Composing and sending a community broadcast. POST only: it sends messages and
# writes history, so there is no URL to navigate to. The guard is this role
# alone; the Administrator's identical endpoint lives in its own blueprint, and
# Health Center Staff has no such endpoint at all -- see the header of
# routes/broadcast_views.py for why that is the enforcement rather than the
# template's hidden buttons.
@official_bp.route('/sms_notifications/send', methods=["POST"])
@login_required
@role_required("Barangay Official")
def official_send_sms_broadcast():
    broadcast, context, message = process_send_broadcast(
        request.form, session.get("user_id"), ip_address=request.remote_addr
    )
    if broadcast:
        flash(message)
        return redirect(url_for("official.official_sms_notifications"))
    # Field errors are shown inside the reopened dialog, next to what they refer
    # to, rather than as a flash above the page.
    return render_template('sms_notifications.html', **context)


@official_bp.route('/health-programs')
@login_required
@role_required("Barangay Official")
def health_programs():
    """Screen 16. Both screens below used to render with no context at all --
    every figure on them was written into the template. See
    routes/official_views.py for where each one now comes from, and for what
    these two screens cannot show."""
    return render_template('health_programs.html', **health_programs_context())


@official_bp.route('/vaccination-campaigns')
@login_required
@role_required("Barangay Official")
def vaccination_campaigns():
    """Screen 17. Reports scheduled doses, not campaigns; see
    official_views.vaccination_campaigns_context() for why."""
    return render_template('vaccination_campaigns.html',
                           **vaccination_campaigns_context())


@official_bp.route('/community-reports')
@login_required
@role_required("Barangay Official")
def community_reports():
    """Screen 18. Rendered with no context at all until now -- every figure and
    both charts on it were written into the template. See
    official_views.community_reports_context() for where each one comes from and
    for the two the barangay's records cannot answer.

    Same guard as the three screens above it: this role and no other. Generate
    submits the report type and the two dates back to this same GET, so there is
    still no POST counterpart in this blueprint and no new guard surface."""
    return render_template('community_reports.html',
                           **community_reports_context(args=request.args))


@official_bp.route('/notifications')
@login_required
@role_required("Barangay Official")
def notifications():
    return render_template('notifications.html')

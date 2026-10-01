"""Administrator screens. Mounted at /admin."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.inventory import get_inventory_item_by_id
from routes.appointment_views import appointment_scheduling_context
from routes.audit_export import (
    audit_document,
    audit_workbook,
    excel_response as audit_excel_response,
    exported_by as audit_exported_by,
    pdf_response as audit_pdf_response,
)
from routes.audit_views import audit_export_context, audit_logs_context
from routes.dashboard_views import dashboard_context
from routes.broadcast_views import process_send_broadcast, sms_notifications_context
from routes.inventory_views import (
    add_edit_medicine_context,
    medicine_inventory_context,
    process_add_edit_medicine,
    process_archive_medicine,
)
from routes.patient_views import (
    patient_demographics_context,
    patient_records_context,
    patient_selection_context,
)
from routes.schedule_views import (
    process_add_entry,
    process_delete_entry,
    process_edit_entry,
    service_schedule_request,
)
from routes.settings_views import (
    TAB_GENERAL,
    TAB_MAINTENANCE,
    backup_download_response,
    process_general_settings,
    process_maintenance_mode,
    settings_context,
)
from routes.report_export import (
    analytics_pdf,
    analytics_workbook,
    excel_response,
    exported_by,
    pdf_response,
)
from routes.report_views import reports_analytics_context
from routes.roster_export import (
    appointment_document,
    appointment_workbook,
    inventory_document,
    inventory_workbook,
    patient_roster_document,
    patient_roster_workbook,
    patient_selection_document,
    patient_selection_workbook,
    user_roster_document,
    user_roster_workbook,
)
from routes.user_views import (
    process_account_status,
    process_create_user,
    process_edit_user,
    process_reset_password,
    user_management_context,
)
from utils.security import (
    end_session_after_self_deactivation, login_required, role_required,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route('/dashboard')
@login_required
@role_required("Admin")
def admin_dashboard():
    # Every list on this screen has room for a handful of rows; the counts
    # alongside them are the true totals, not the length of those lists. The
    # context is built in routes/dashboard_views.py and is the same one the
    # Health Staff dashboard renders, so the figures the two share cannot drift.
    return render_template('admin_dashboard.html', **dashboard_context())


@admin_bp.route('/patient_records')
@login_required
@role_required("Admin")
def patient_records():
    """Screen 03. `?search=` is the header's global search box arriving here --
    it is the only thing that box does, and this route is where it lands for
    this role. The term is not matched here; see patient_records_context() for
    why the screen's own toolbar filter is what runs it."""
    return render_template(
        'patient_records.html',
        **patient_records_context(search=request.args.get('search', '')),
    )


# Export Excel and Export PDF for the roster above. Both carry the same guard as
# the screen they export -- this role and no other -- because the file is the
# screen's contents, and a download that widened who could read them would be a
# hole the render route does not have. A Barangay Official has no access to
# Patient Records at all and bounces off these two exactly as they bounce off the
# screen.
#
# Both read the same patient_records_context() the screen rendered from, so the
# file cannot disagree with the page it was taken off; routes/roster_export.py
# assembles it once and renders it as either format. Neither reads the query
# string, because this screen has no server-side filter to read -- its five
# controls narrow rows in the browser, and the file says so on its cover rather
# than pretending otherwise.
@admin_bp.route('/patient_records/export.xlsx')
@login_required
@role_required("Admin")
def export_patient_records_excel():
    return excel_response(patient_roster_workbook(
        patient_records_context(),
        produced_by=exported_by(),
    ))


@admin_bp.route('/patient_records/export.pdf')
@login_required
@role_required("Admin")
def export_patient_records_pdf():
    return pdf_response(patient_roster_document(
        patient_records_context(),
        produced_by=exported_by(),
    ))


# Export Excel and Export PDF for the *selection*, from the bulk bar under the
# toolbar. POST, and the only two exports in this project that are: the two GET
# routes above answer "the whole register", which is a question with a stable
# answer and therefore a bookmarkable URL, and these answer "these eleven records
# somebody ticked", which is not. The ids arrive as the same patient_ids
# checkboxes the archive endpoint below already reads, from the same form on the
# same page -- see routes/patient_views.selected_patient_ids() for the one rule
# that reads them.
#
# Same guard as the roster exports, for the same reason: the file is the screen's
# contents, and a download that widened who could read them would be a hole the
# render route does not have. Nothing is written, so there is no CSRF-shaped
# hazard here beyond the one every POST on this screen already carries; the guard
# is what keeps the rows in.
#
# An empty or unusable selection redirects back with a flash rather than serving
# a workbook with no rows in it. A file that says "0 records" is a file somebody
# has to open to discover was pointless.
@admin_bp.route('/patient_records/export-selection.xlsx', methods=["POST"])
@login_required
@role_required("Admin")
def export_patient_selection_excel():
    context = patient_selection_context(request.form)
    if context is None:
        flash("Select at least one patient record to export.")
        return redirect(url_for("admin.patient_records"))
    return excel_response(patient_selection_workbook(
        context,
        produced_by=exported_by(),
    ))


@admin_bp.route('/patient_records/export-selection.pdf', methods=["POST"])
@login_required
@role_required("Admin")
def export_patient_selection_pdf():
    context = patient_selection_context(request.form)
    if context is None:
        flash("Select at least one patient record to export.")
        return redirect(url_for("admin.patient_records"))
    return pdf_response(patient_selection_document(
        context,
        produced_by=exported_by(),
    ))


@admin_bp.route('/patient_profile/<int:patient_id>')
@login_required
@role_required("Admin")
def patient_profile(patient_id):
    # Demographics only (Task 5c). The full record, with its clinical tabs, is
    # the care team's and is built by patient_profile_context(), which refuses
    # this role.
    context = patient_demographics_context(patient_id)
    if context is None:
        flash("That patient record could not be found.")
        return redirect(url_for("admin.patient_records"))
    return render_template('patient_profile_demographics.html', **context)


# NO ROUTE HERE WRITES A PATIENT OR A CLINICAL RECORD (Task 5c).
# Registering and editing patients, changing their status, correcting a dose,
# the queue's check-in, start and complete, and recording or editing a
# consultation are the care team's: the Doctor and Health Center Staff, through
# routes/staff.py. The Administrator runs the system and is not part of anyone's
# care (RA 11166; RA 10173's "not excessive"; the minimum-necessary standard).
# There is no /admin/... URL for any of them, so a request from this role has
# nothing to reach, and the /staff/... ones send him back to his dashboard.


@admin_bp.route('/medicine_inventory')
@login_required
@role_required("Admin")
def medicine_inventory():
    return render_template('medicine_inventory.html', **medicine_inventory_context())


# Export Excel and Export PDF for the item list above. Same guard as the screen,
# same context, for the same reasons the roster's two carry them.
@admin_bp.route('/medicine_inventory/export.xlsx')
@login_required
@role_required("Admin")
def export_medicine_inventory_excel():
    return excel_response(inventory_workbook(
        medicine_inventory_context(),
        produced_by=exported_by(),
    ))


@admin_bp.route('/medicine_inventory/export.pdf')
@login_required
@role_required("Admin")
def export_medicine_inventory_pdf():
    return pdf_response(inventory_document(
        medicine_inventory_context(),
        produced_by=exported_by(),
    ))


# POST only: this changes a
# record, so there is no URL anyone can navigate to. A Barangay Official is
# stopped by role_required and lands on their own dashboard.
@admin_bp.route('/medicine_inventory/archive', methods=["POST"])
@login_required
@role_required("Admin")
def archive_medicine():
    flash(process_archive_medicine(request.form, session.get("user_id"), request.remote_addr))
    return redirect(url_for("admin.medicine_inventory"))


# Add mode carries no id; edit mode carries the medicine's id. Same shape as
# the Register Patient screen -- one view, one template, distinguished by the path.
#
# There is no per-item detail screen for inventory the way patient_profile is one
# for a patient, so a successful save redirects back to the list rather than to a
# record of its own. Reading a stock item in full does not need one: the View
# icon on a Medicine Inventory row expands a read-only panel in place, which is
# why that button is no longer disabled and why no route was added for it.
@admin_bp.route('/add_edit_medicine', methods=["GET", "POST"])
@admin_bp.route('/add_edit_medicine/<int:medicine_id>', methods=["GET", "POST"])
@login_required
@role_required("Admin")
def add_edit_medicine(medicine_id=None):
    item = None
    if medicine_id is not None:
        item = get_inventory_item_by_id(medicine_id)
        if item is None:
            flash("That inventory item could not be found.")
            return redirect(url_for("admin.medicine_inventory"))

    if request.method == "POST":
        saved_id, context, message = process_add_edit_medicine(
            request.form, item=item, user_id=session.get("user_id"),
            ip_address=request.remote_addr,
        )
        if saved_id:
            # The message names the fields that actually changed, so a save that
            # wrote back the stored values says so instead of claiming success.
            flash(message)
            return redirect(url_for("admin.medicine_inventory"))
        return render_template('add_edit_medicine.html', **context)

    return render_template(
        'add_edit_medicine.html', **add_edit_medicine_context(item=item)
    )


# ?month=YYYY-MM moves the calendar panel; anything unusable falls back to the
# current month. The queue below it is always today's and is unaffected.
@admin_bp.route('/appointment_scheduling')
@login_required
@role_required("Admin")
def appointment_scheduling():
    return render_template(
        'appointment_scheduling.html',
        **appointment_scheduling_context(month=request.args.get("month")),
    )


# Export Excel and Export PDF for Screen 08. Same guard as the screen, and the
# only one of this task's eight exports that reads the query string: ?month= is a
# real server-side parameter -- the calendar panel's own arrows submit it -- so the
# button exports the month the operator is looking at, exactly as Audit Logs'
# export carries its ?module=. The queue's own search and
# filter controls narrow rows in the browser and cannot come with it; the file's
# cover sheet says which of the two it is for every control on the screen.
@admin_bp.route('/appointment_scheduling/export.xlsx')
@login_required
@role_required("Admin")
def export_appointment_scheduling_excel():
    return excel_response(appointment_workbook(
        appointment_scheduling_context(month=request.args.get("month")),
        produced_by=exported_by(),
    ))


@admin_bp.route('/appointment_scheduling/export.pdf')
@login_required
@role_required("Admin")
def export_appointment_scheduling_pdf():
    return pdf_response(appointment_document(
        appointment_scheduling_context(month=request.args.get("month")),
        produced_by=exported_by(),
    ))


# NO ROUTE HERE SEALS A CONSULTATION, AND THAT ABSENCE IS THE ENFORCEMENT.
# One did, while the Administrator was taken to be the health center's doctor.
# The RHU's field data showed the Administrator is a barangay Kagawad who runs
# the system and the RHU physician is the clinician, so deciding that a
# diagnosis is privileged -- and reading one that is -- moved to the Doctor.
# The route is routes/staff.py restrict_consultation, guarded to the Doctor
# alone, and process_consultation_restriction() asks the role again itself.
# There is no /admin/... URL for a request from this role to be aimed at.


@admin_bp.route('/sms_notifications')
@login_required
@role_required("Admin")
def sms_notifications():
    return render_template('sms_notifications.html', **sms_notifications_context())


# Composing and sending a community broadcast. POST only: it sends messages and
# writes history, so there is no URL to navigate to. The Barangay Official holds
# the same authority through the identical endpoint in its own blueprint; Health
# Center Staff has no such endpoint at all -- see the header of
# routes/broadcast_views.py.
@admin_bp.route('/sms_notifications/send', methods=["POST"])
@login_required
@role_required("Admin")
def send_sms_broadcast():
    broadcast, context, message = process_send_broadcast(
        request.form, session.get("user_id"), ip_address=request.remote_addr
    )
    if broadcast:
        flash(message)
        return redirect(url_for("admin.sms_notifications"))
    # Field errors are shown inside the reopened dialog, next to what they refer
    # to, rather than as a flash above the page.
    return render_template('sms_notifications.html', **context)


# Screen 10. The context is built in routes/report_views.py and is byte-for-byte
# the same one the Barangay Official's route renders -- same reason every other
# shared screen in this project has one context builder and two thin routes.
@admin_bp.route('/reports_analytics')
@login_required
@role_required("Admin")
def reports_analytics():
    # The whole query string, not just `type`: the toolbar's Generate now submits
    # `from` and `to` alongside it as a GET, so the report a URL describes is the
    # report the page renders and the one Print puts on paper.
    return render_template(
        'reports_analytics.html',
        **reports_analytics_context(args=request.args),
    )


# Export Excel, for the screen above. A GET reading the same query string the
# screen does, through the same reports_analytics_context() -- so the workbook
# covers the report type and range the operator was looking at, and no figure in
# it was counted a second time. The toolbar links here with the *resolved*
# window rather than with whatever is typed in the date boxes, which is what
# makes Export and Print produce the same report.
#
# A new endpoint, so a new row in the route x role matrix, and it carries the
# same guard as the screen it exports: this role and no other. The Barangay
# Official's identical export lives in its own blueprint for exactly the reason
# the two render routes do.
@admin_bp.route('/reports_analytics/export.xlsx')
@login_required
@role_required("Admin")
def export_reports_analytics_excel():
    return excel_response(analytics_workbook(
        reports_analytics_context(args=request.args),
        produced_by=exported_by(),
    ))


# Export PDF, for the same screen. The twin of the route above: same context, same
# resolved window, same assembled report -- routes/report_export.py renders it as a
# PDF instead of a workbook, so the two files cannot disagree about a figure. Its
# own endpoint and its own guard, this role and no other, for the same reason the
# Excel route has them.
@admin_bp.route('/reports_analytics/export.pdf')
@login_required
@role_required("Admin")
def export_reports_analytics_pdf():
    return pdf_response(analytics_pdf(
        reports_analytics_context(args=request.args),
        produced_by=exported_by(),
    ))


# Screen 11. Admin only, unchanged: the roster names every account that can
# sign in, so it stays with the role that oversees the others. The context is
# built in routes/user_views.py.
@admin_bp.route('/user_management')
@login_required
@role_required("Admin")
def user_management():
    return render_template('user_management.html', **user_management_context())


# ADD USER, DEACTIVATE AND REACTIVATE. POST only, and Admin only.
#
# THE GUARD ON THESE TWO IS THE MOST LOAD-BEARING ONE IN THE PROJECT, AND IT IS
# THE SAME GUARD THE SCREEN CARRIES.
# Every other write in this system changes a record. These change who can reach
# every record: the first creates a way into a database of patient histories and
# chooses what that account may open, and the second takes an existing way in
# away. role_required("Admin") is therefore not a copy of the screen's guard for
# tidiness -- it is the enforcement, because a POST needs no page. An endpoint
# that let Health Center Staff through would let them create themselves an
# Administrator account, which is every access rule in the application at once.
#
# There is no GET on either. Both change records, so there is no URL to navigate
# to and none that could be reached by a link, a bookmark or a prefetch.
@admin_bp.route('/user_management/add', methods=["POST"])
@login_required
@role_required("Admin")
def add_user():
    new_id, context, message = process_create_user(
        request.form, session.get("user_id"), request.remote_addr
    )
    if new_id:
        flash(message)
        return redirect(url_for("admin.user_management"))
    # Field errors are shown inside the reopened dialog, next to what they refer
    # to, rather than as a flash above the page -- the same treatment Register
    # Patient and the booking dialog give theirs.
    return render_template('user_management.html', **context)


# EDIT USER AND RESET PASSWORD. POST only, and Admin only, for exactly the
# reasons written over add_user() and set_user_status() above -- and one more
# that belongs to these two in particular.
#
# EDITING A ROLE IS THE SAME POWER AS CREATING AN ACCOUNT, REACHED FROM THE OTHER
# END. add_user() is guarded because an endpoint any other role could reach would
# let that role create itself an Administrator account; edit_user() is guarded
# because an endpoint any other role could reach would let that role PROMOTE
# itself to one, which needs no new account and leaves no new row in the roster
# for anybody to notice. reset_user_password() is guarded because an endpoint any
# other role could reach would let that role set a password of its choosing on
# the Administrator account and then simply sign in as it. Each of those is every
# access rule in the application at once, and the decorator is the enforcement
# rather than a copy of the screen's.
#
# Both return a rendered page rather than a redirect when the submission was
# refused, because both carry typing that must survive: the account's dialog
# reopens with the error beside the field and the values still in it. That is the
# same treatment add_user() gives its dialog, and the reason process_edit_user()
# and process_reset_password() return a context instead of a message.
#
# No GET on either, for the reason neither of the two above has one: both change
# records, so there is no URL to navigate to and none a link, a bookmark or a
# prefetch could reach.
@admin_bp.route('/user_management/edit', methods=["POST"])
@login_required
@role_required("Admin")
def edit_user():
    user_id, context, message = process_edit_user(
        request.form, session.get("user_id"), request.remote_addr
    )
    if user_id:
        flash(message)
        return redirect(url_for("admin.user_management"))
    if context is None:
        # The form did not name an account this system holds -- a POST that did
        # not come from this page. There is no dialog to reopen it on, so it is
        # a sentence above the roster like the status route's refusals.
        flash(message)
        return redirect(url_for("admin.user_management"))
    return render_template('user_management.html', **context)


@admin_bp.route('/user_management/reset_password', methods=["POST"])
@login_required
@role_required("Admin")
def reset_user_password():
    user_id, context, message = process_reset_password(
        request.form, session.get("user_id"), request.remote_addr
    )
    if user_id:
        flash(message)
        return redirect(url_for("admin.user_management"))
    if context is None:
        flash(message)
        return redirect(url_for("admin.user_management"))
    return render_template('user_management.html', **context)


@admin_bp.route('/user_management/status', methods=["POST"])
@login_required
@role_required("Admin")
def set_user_status():
    """Revoke or restore one account's access.

    Every outcome is a flash and a redirect, including the refusals: the
    last-administrator refusal and the two "nothing to do" answers are all
    sentences about an account rather than corrections to something typed, so
    there is no form state to preserve and nothing to reopen a dialog on.

    Except one: an Administrator who has just deactivated their own account is
    signed out here, in this request, and sent to the login form with a notice
    saying they did it. Redirecting them to User Management instead -- as this
    route once did -- meant the guard found the account deactivated on that GET,
    cleared the session and the flash with it, and told them "Invalid security
    credentials."
    """
    message, deactivated_self = process_account_status(
        request.form, session.get("user_id"), request.remote_addr
    )
    if deactivated_self:
        return end_session_after_self_deactivation(message)
    flash(message)
    return redirect(url_for("admin.user_management"))


# Export Excel and Export PDF for the account roster above. Admin and no other
# role, the same guard as the screen -- and the guard matters more here than on
# any other export in the project, because this file names every account on the
# system, its role and the screens that role can open. It holds no password and
# no hash: get_all_users() does not select the column, so there is none in the
# context to write.
@admin_bp.route('/user_management/export.xlsx')
@login_required
@role_required("Admin")
def export_user_management_excel():
    return excel_response(user_roster_workbook(
        user_management_context(),
        produced_by=exported_by(),
    ))


@admin_bp.route('/user_management/export.pdf')
@login_required
@role_required("Admin")
def export_user_management_pdf():
    return pdf_response(user_roster_document(
        user_management_context(),
        produced_by=exported_by(),
    ))


# Screen 12. Admin only, unchanged: the trail says who changed what, so the role
# that oversees the others is the one that reads it. The context is built in
# routes/audit_views.py; `module` is the only filter the stored query supports.
@admin_bp.route('/audit_logs')
@login_required
@role_required("Admin")
def audit_logs():
    return render_template(
        'audit_logs.html',
        **audit_logs_context(module=request.args.get("module")),
    )


# Export Excel and Export PDF for the trail above. Both carry the same guard as
# the screen -- Admin and no other role -- because the file is the screen's
# contents and a download that widened who could read them would be a hole the
# render route does not have. Each reads the same ?module= the screen does, so the
# button exports the trail in front of the operator; routes/audit_export.py
# assembles it once and renders it as either file.
@admin_bp.route('/audit_logs/export.xlsx')
@login_required
@role_required("Admin")
def export_audit_logs_excel():
    return audit_excel_response(audit_workbook(
        audit_export_context(module=request.args.get("module")),
        produced_by=audit_exported_by(),
    ))


@admin_bp.route('/audit_logs/export.pdf')
@login_required
@role_required("Admin")
def export_audit_logs_pdf():
    return audit_pdf_response(audit_document(
        audit_export_context(module=request.args.get("module")),
        produced_by=audit_exported_by(),
    ))


@admin_bp.route('/settings')
@login_required
@role_required("Admin")
def settings():
    # See routes/settings_views.py for what each pane on this screen now is:
    # one stored form, four panes read live from what the system actually does,
    # and the rest disabled with a reason.
    #
    # `?tab=` decides which of the eight opens. It is what the two POST routes
    # below redirect back with, so an administrator lands on the pane they acted
    # from rather than on whichever one the template happened to hardcode. Any
    # unrecognised value resolves to General rather than to no pane at all --
    # settings_context() validates it, so nothing here has to.
    return render_template(
        'settings.html',
        **settings_context(active_tab=request.args.get("tab")),
    )


# SAVING GENERAL SETTINGS. POST only, and Admin only.
#
# THE GUARD IS THE ENFORCEMENT, NOT A COPY OF THE SCREEN'S, and the reach of
# these six values is why it matters as much here as on add_user(). They are not
# display text. The health center's name is the first thing in every appointment
# SMS this system sends, so an endpoint another role could reach would let that
# role change what is texted to every patient in the barangay, over the health
# center's own name. The opening and closing times are what the bookable slots
# are generated from and what validate_booking() accepts, so the same endpoint
# would let that role close the clinic's booking day, or open it to hours nobody
# is working.
#
# No GET. It changes stored values, so there is no URL to navigate to and none a
# link, a bookmark or a prefetch could reach.
#
# A refused submit returns a rendered page rather than a redirect, because it
# carries typing that must survive: the form comes back with the messages beside
# the fields and every value still in it. That is the same treatment add_user()
# and edit_user() give theirs, and the reason process_general_settings() returns
# a context instead of a message.
@admin_bp.route('/settings/general', methods=["POST"])
@login_required
@role_required("Admin")
def save_general_settings():
    context, message = process_general_settings(
        request.form, session.get("user_id"), request.remote_addr
    )
    if context is not None:
        return render_template('settings.html', **context)
    flash(message)
    # Named rather than left to the default. General is the pane this submit came
    # from AND the pane the screen opens on when nothing is asked for, so
    # omitting it would work today by coincidence -- which is exactly how the
    # maintenance toggle below came to land on the wrong pane. The destination is
    # stated so it stays correct if the default ever moves.
    return redirect(url_for("admin.settings", tab=TAB_GENERAL))


# DOWNLOADING A BACKUP. Admin only, and a GET, unlike every other route in this
# block.
#
# WHY A GET WHEN IT IS GUARDED THIS HEAVILY. It changes nothing. Every other
# guarded endpoint here writes, and a GET on one of those would be reachable by a
# link or a prefetch that could alter a record; this one reads the database and
# hands back a copy, exactly like the eleven export routes above it, and it is a
# GET for the same reason they are -- a download is an anchor with `download` on
# it, not a form.
#
# THAT IT CHANGES NOTHING IS NOT WHY IT IS GUARDED. What leaves is every patient
# record, every consultation, every immunisation and every account row in one
# file, which makes this the single most consequential read the application
# offers. role_required("Admin") is the enforcement: an endpoint another role
# could reach would hand the whole register to anyone who could sign in.
#
# The download is recorded in the audit trail even though no record changed --
# see ACTION_BACKUP_DOWNLOADED in models/audit.py for why that is the one read in
# this system worth an entry.
# MAINTENANCE MODE. POST only, and Admin only.
#
# THIS IS THE MOST CONSEQUENTIAL WRITE ON THE SCREEN AND THE SMALLEST PAYLOAD.
# One field with two possible values, and one of them closes the system to every
# Health Center Staff and Barangay Official account in the barangay. The guard is
# the enforcement rather than a copy of the screen's: an endpoint another role
# could reach would let a health worker close the health center out of its own
# patient records, or -- worse and quieter -- reopen a system an administrator
# had deliberately shut.
#
# It redirects on every outcome, including refusal, because there is nothing
# typed here to preserve. That is the one way this route differs from
# save_general_settings() above, and the reason process_maintenance_mode()
# returns a message where process_general_settings() can return a context.
#
# No GET. It changes who may use the system, so there is no URL to navigate to
# and none a link, a bookmark or a prefetch could reach -- which matters more
# here than anywhere else in this file, because a GET that closed the system
# could be triggered by a browser preloading a link.
@admin_bp.route('/settings/maintenance', methods=["POST"])
@login_required
@role_required("Admin")
def set_maintenance_mode():
    flash(process_maintenance_mode(
        request.form, session.get("user_id"), request.remote_addr
    ))
    # Back to System Maintenance, which is where the switch is. This redirected
    # to a bare url_for("admin.settings") and dropped the administrator on
    # General Settings -- six panes from the control they had just thrown, with
    # the flash claiming success and nothing on screen showing it. The tab is
    # carried for every outcome, including the refusal of an unrecognised action,
    # because a refusal has to be read beside the control it refused.
    return redirect(url_for("admin.settings", tab=TAB_MAINTENANCE))


@admin_bp.route('/settings/backup.db')
@login_required
@role_required("Admin")
def download_backup():
    return backup_download_response(
        session.get("user_id"), request.remote_addr
    )


# THE SERVICE SCHEDULE -- the Administrator's copy, and the only one that writes.
#
# The screen is read by all four roles, each through its own blueprint (the
# other three are /staff/service_schedule and /official/service_schedule), from
# the one builder in routes/schedule_views.py. What only this copy has is the
# side panel and the three POST routes under it.
#
# ?edit=<id> and ?delete=<id> open the panel on one entry. An id that is not on
# the schedule any more is said above the screen rather than silently ignored.
@admin_bp.route('/service_schedule')
@login_required
@role_required("Admin")
def service_schedule():
    context, message = service_schedule_request(request.args)
    if context is None:
        flash(message)
        return redirect(url_for("admin.service_schedule"))
    return render_template('service_schedule.html', **context)


# ADD, EDIT AND DELETE A SCHEDULE ENTRY. POST only, and Admin only.
#
# THE GUARD IS THE ENFORCEMENT. These three are the only way the schedule
# changes, and there is no copy of them in /staff or /official: a Health Center
# Staff, Doctor or Barangay Official account posting a forged form here is
# redirected by role_required() before the view runs, and nothing is written.
# Hiding the form from those roles (schedule_views._can_edit) is presentation.
#
# No GET on any of them. They change stored values, so there is no URL a link,
# a bookmark or a prefetch could reach.
#
# Add and Edit return a rendered page rather than a redirect when the submit was
# refused, because they carry typing that must survive: the panel comes back
# with the messages beside the fields and every value still in it -- the same
# treatment add_user(), edit_user() and save_general_settings() give theirs.
# Delete carries nothing typed, so every outcome of it is a flash and a redirect.
@admin_bp.route('/service_schedule/add', methods=["POST"])
@login_required
@role_required("Admin")
def add_service_schedule_entry():
    entry, context, message = process_add_entry(
        request.form, session.get("user_id"), request.remote_addr
    )
    if entry is None:
        return render_template('service_schedule.html', **context)
    flash(message)
    return redirect(url_for("admin.service_schedule"))


@admin_bp.route('/service_schedule/<int:entry_id>/edit', methods=["POST"])
@login_required
@role_required("Admin")
def edit_service_schedule_entry(entry_id):
    entry, context, message = process_edit_entry(
        entry_id, request.form, session.get("user_id"), request.remote_addr
    )
    if context is not None:
        return render_template('service_schedule.html', **context)
    flash(message)
    return redirect(url_for("admin.service_schedule"))


@admin_bp.route('/service_schedule/<int:entry_id>/delete', methods=["POST"])
@login_required
@role_required("Admin")
def delete_service_schedule_entry(entry_id):
    flash(process_delete_entry(
        entry_id, session.get("user_id"), request.remote_addr
    ))
    return redirect(url_for("admin.service_schedule"))

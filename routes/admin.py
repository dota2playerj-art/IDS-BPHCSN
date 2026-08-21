"""Administrator screens. Mounted at /admin."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.consultations import PEDIATRIC_AGE_YEARS
from models.immunizations import get_immunization_alert
from models.inventory import get_inventory_item_by_id, get_low_stock_alert
from models.patients import get_patient_by_id
from routes.appointment_views import (
    NEW_PATIENT_MODE,
    appointment_return_url,
    appointment_scheduling_context,
    booking_mode,
    process_book_appointment,
    process_cancel_appointment,
    process_check_in,
    process_complete_consultation,
    process_new_patient_booking,
    process_new_patient_booking_request,
    process_new_patient_check_in,
    process_reschedule_appointment,
    process_start_consultation,
)
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
from routes.consultation_views import (
    edit_consultation_context,
    process_edit_consultation,
    process_record_consultation,
    record_consultation_context,
)
from routes.inventory_views import (
    add_edit_medicine_context,
    medicine_inventory_context,
    process_add_edit_medicine,
)
from routes.patient_views import (
    booking_details,
    booking_query_args,
    booking_requested,
    check_in_reason,
    check_in_requested,
    patient_profile_context,
    patient_records_context,
    process_archive_patients,
    process_register_patient,
    register_patient_context,
)
from routes.settings_views import settings_context
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
    user_roster_document,
    user_roster_workbook,
)
from routes.user_views import user_management_context
from utils.security import login_required, role_required

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
    return render_template('patient_records.html', **patient_records_context())


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


# POST only: this changes records, so there is no URL anyone can navigate to.
# A Barangay Official is stopped by role_required and lands on their own
# dashboard, the same bounce every other Admin-only view gives them.
@admin_bp.route('/patient_records/archive', methods=["POST"])
@login_required
@role_required("Admin")
def archive_patients():
    flash(process_archive_patients(request.form))
    return redirect(url_for("admin.patient_records"))


@admin_bp.route('/patient_profile/<int:patient_id>')
@login_required
@role_required("Admin")
def patient_profile(patient_id):
    context = patient_profile_context(patient_id)
    if context is None:
        flash("That patient record could not be found.")
        return redirect(url_for("admin.patient_records"))
    return render_template('patient_profile.html', **context)


# Audit item 7: Register Patient was reachable only by Health Center Staff even
# though the Administrator holds every Staff permission.
#
# No id in the URL means add mode; an id means edit that patient. Same shape as
# add_edit_medicine above -- one view, one template, distinguished by the path.
@admin_bp.route('/register_patient', methods=["GET", "POST"])
@admin_bp.route('/register_patient/<int:patient_id>', methods=["GET", "POST"])
@login_required
@role_required("Admin")
def register_patient(patient_id=None):
    patient = None
    if patient_id is not None:
        patient = get_patient_by_id(patient_id)
        if patient is None:
            flash("That patient record could not be found.")
            return redirect(url_for("admin.patient_records"))

    if request.method == "POST":
        saved_id, context = process_register_patient(request.form, patient=patient)
        if saved_id:
            # Opened from the Check In dialog's "New Patient (first visit)" path:
            # the record now exists, so put that same person into today's queue
            # and land the operator back on the queue they were working from.
            # One save, both outcomes -- no second check-in step.
            if patient is None and check_in_requested(request.form):
                flash(
                    process_new_patient_check_in(
                        saved_id,
                        check_in_reason(request.form),
                        session.get("user_id"),
                    )
                )
                return redirect(url_for("admin.appointment_scheduling"))
            # The same handoff for the New Appointment dialog's new-patient
            # path: the record now exists, so book the visit it was opened for
            # and land back on the screen the operator started from.
            if patient is None and booking_requested(request.form):
                flash(
                    process_new_patient_booking(
                        saved_id,
                        booking_details(request.form),
                        session.get("user_id"),
                    )
                )
                return redirect(url_for("admin.appointment_scheduling"))
            flash("Patient details updated." if patient else "Patient registered successfully.")
            return redirect(url_for("admin.patient_profile", patient_id=saved_id))
        return render_template('register_patient.html', **context)

    return render_template(
        'register_patient.html',
        **register_patient_context(
            patient=patient,
            check_in=check_in_requested(request.args),
            check_in_reason_text=check_in_reason(request.args),
            booking=booking_details(request.args) if booking_requested(request.args) else None,
        ),
    )


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


# Add mode carries no id; edit mode carries the medicine's id. Same shape as
# register_patient above -- one view, one template, distinguished by the path.
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
        saved_id, context, message = process_add_edit_medicine(request.form, item=item)
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
        **appointment_scheduling_context(
            month=request.args.get("month"),
            # ?reschedule=<id> and ?cancel=<id> open one of this screen's
            # dialogs on a named appointment, and ?back= says where to land
            # afterwards. That is how the Patient Profile's Appointment History
            # offers both actions without a second copy of either dialog.
            reschedule_id=request.args.get("reschedule"),
            cancel_id=request.args.get("cancel"),
            return_to=request.args.get("back"),
            # ?book=<patient_id> is the same arrangement for the other
            # direction: the profile's Schedule Appointment action opens the New
            # Appointment dialog here, on that patient.
            book_patient_id=request.args.get("book"),
        ),
    )


# Export Excel and Export PDF for Screen 08. Same guard as the screen, and the
# only one of this task's eight exports that reads the query string: ?month= is a
# real server-side parameter -- the calendar panel's own arrows submit it -- so the
# button exports the month the operator is looking at, exactly as Audit Logs'
# export carries its ?module=. The queue's and the upcoming list's own search and
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


# New Appointment: book a future visit. Two paths through one endpoint, because
# they are one decision made in one dialog -- pick an existing patient, or
# register a new one first. The second validates the booking here and then hands
# off to Register Patient carrying it, so an unsound date is caught before a
# permanent patient record is created against it.
@admin_bp.route('/appointment_scheduling/book', methods=["POST"])
@login_required
@role_required("Admin")
def book_appointment():
    if booking_mode(request.form) == NEW_PATIENT_MODE:
        details, context = process_new_patient_booking_request(request.form)
        if details is None:
            return render_template('appointment_scheduling.html', **context)
        return redirect(
            url_for("admin.register_patient", **booking_query_args(details))
        )

    appointment_id, context, message = process_book_appointment(
        request.form, session.get("user_id")
    )
    if appointment_id:
        flash(message)
        return redirect(url_for("admin.appointment_scheduling"))
    # Field errors and unacknowledged conflicts are shown inside the reopened
    # dialog, next to what they refer to, rather than as a flash above the page.
    return render_template('appointment_scheduling.html', **context)


# Calling a booking off, and moving one. POST only, like every other action on
# this screen: they change records, so there is no URL to navigate to.
#
# Both accept ?return_to=profile:<patient_id> so the Patient Profile's
# Appointment History can use the same two endpoints and land back where the
# operator was working, rather than needing endpoints of its own.
@admin_bp.route('/appointment_scheduling/cancel', methods=["POST"])
@login_required
@role_required("Admin")
def cancel_appointment():
    flash(process_cancel_appointment(request.form))
    return redirect(appointment_return_url(
        request.form, "admin.appointment_scheduling", "admin.patient_profile",
    ))


@admin_bp.route('/appointment_scheduling/reschedule', methods=["POST"])
@login_required
@role_required("Admin")
def reschedule_appointment():
    appointment_id, context, message = process_reschedule_appointment(request.form)
    if context is None:
        flash(message)
        return redirect(appointment_return_url(
            request.form, "admin.appointment_scheduling", "admin.patient_profile",
        ))
    return render_template('appointment_scheduling.html', **context)


# POST only: both of these change records, so there is no URL to navigate to.
# A Barangay Official is stopped by role_required and lands on their own
# dashboard, the same bounce every other Admin-only view gives them.
@admin_bp.route('/appointment_scheduling/check-in', methods=["POST"])
@login_required
@role_required("Admin")
def check_in_patient():
    flash(process_check_in(request.form, session.get("user_id")))
    return redirect(url_for("admin.appointment_scheduling"))


@admin_bp.route('/appointment_scheduling/start-consultation', methods=["POST"])
@login_required
@role_required("Admin")
def start_consultation():
    flash(process_start_consultation(request.form))
    return redirect(url_for("admin.appointment_scheduling"))


# Completing is what frees the clinician for the next patient, so it is part of
# the queue rather than of the consultation record itself -- recording what
# happened during the visit is a separate screen and is not wired here.
@admin_bp.route('/appointment_scheduling/complete-consultation', methods=["POST"])
@login_required
@role_required("Admin")
def complete_consultation():
    flash(process_complete_consultation(request.form))
    return redirect(url_for("admin.appointment_scheduling"))


# The consultation write-up itself. Anchored to the queue entry rather than to
# the patient: the record documents one specific visit, and the appointment id is
# what says which. A successful save completes that queue entry and lands on the
# patient's profile, where the new record is already the top row of Consultation
# History.
@admin_bp.route('/consultation/record/<int:appointment_id>', methods=["GET", "POST"])
@login_required
@role_required("Admin")
def record_consultation(appointment_id):
    if request.method == "POST":
        patient_id, context, message = process_record_consultation(
            appointment_id, request.form, session.get("user_id")
        )
        flash(message)
        if patient_id:
            return redirect(url_for("admin.patient_profile", patient_id=patient_id))
        if context is None:
            return redirect(url_for("admin.appointment_scheduling"))
        return render_template('record_consultation.html', **context)

    context, message = record_consultation_context(appointment_id)
    if context is None:
        flash(message)
        return redirect(url_for("admin.appointment_scheduling"))
    return render_template('record_consultation.html', **context)


# Editing a saved consultation. Same template, same validation; the difference is
# that this writes an audit_logs entry naming what changed, and refuses to move
# the patient or the visit date.
@admin_bp.route('/consultation/edit/<int:consultation_id>', methods=["GET", "POST"])
@login_required
@role_required("Admin")
def edit_consultation(consultation_id):
    if request.method == "POST":
        patient_id, context, message = process_edit_consultation(
            consultation_id, request.form, session.get("user_id"),
            ip_address=request.remote_addr,
        )
        flash(message)
        if patient_id:
            return redirect(url_for("admin.patient_profile", patient_id=patient_id))
        if context is None:
            return redirect(url_for("admin.patient_records"))
        return render_template('record_consultation.html', **context)

    context, message = edit_consultation_context(consultation_id)
    if context is None:
        flash(message)
        return redirect(url_for("admin.patient_records"))
    return render_template('record_consultation.html', **context)


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
    # A context at last, and a deliberately small one -- see
    # routes/settings_views.py for why only the Security pane gets real figures
    # while every other pane on this screen stays a disabled control.
    return render_template('settings.html', **settings_context())

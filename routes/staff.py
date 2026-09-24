"""The clinical floor: Health Center Staff and the Doctor. Mounted at /staff.

Several of these render the same templates as the Admin blueprint; they exist
separately so each role's URL space and role_required guard stay explicit.

WHY THE DOCTOR IS HERE RATHER THAN IN A BLUEPRINT OF THEIR OWN
--------------------------------------------------------------
The Doctor role was added when the RHU's field data showed that clinical
authority belongs to the RHU physician, not to the Administrator (a barangay
Kagawad). The Doctor works the same screens Health Center Staff do -- Patient
Records, Patient Profile, Register Patient, the Patient Queue, Record
Consultation, Medicine Inventory, and SMS Notifications read-only -- and every
one of them is already built here from a context builder shared with the
Administrator's copy. A /doctor/* blueprint would have been these same 24
views a third time, each able to drift from the other two.

So every screen in this file admits CLINICAL_FLOOR_ROLES, and what separates
the Doctor from Health Center Staff is not which screen they reach but what the
screen lets them do: whether the diagnosis and treatment plan are drawn and
accepted, whether a sealed consultation is readable, whether a patient may be
marked deceased or brought back from it. Those are decided per request from the
signed-in account's stored role (utils.security.current_role()), inside the
shared builders, and are enforced there whichever blueprint the request came
through -- see models/consultations.py can_diagnose().

The one route that is not a screen both roles share is restrict_consultation,
which seals a consultation. Only the Doctor may, so it is guarded to the Doctor
alone -- the one guard in this file that differs from its neighbours.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.consultations import PEDIATRIC_AGE_YEARS
from models.immunizations import get_immunization_alert
from models.inventory import get_inventory_item_by_id, get_low_stock_alert
from models.patients import get_patient_by_id
from routes.appointment_views import (
    appointment_scheduling_context,
    process_check_in,
    process_complete_consultation,
    process_new_patient_check_in,
    process_start_consultation,
)
from routes.broadcast_views import sms_notifications_context
from routes.consultation_views import (
    edit_consultation_context,
    process_consultation_restriction,
    process_edit_consultation,
    process_record_consultation,
    record_consultation_context,
)
from routes.dashboard_views import dashboard_context
from routes.inventory_views import (
    add_edit_medicine_context,
    medicine_inventory_context,
    process_add_edit_medicine,
    process_archive_medicine,
)
from routes.roster_export import (
    appointment_document,
    appointment_workbook,
    excel_response,
    exported_by,
    inventory_document,
    inventory_workbook,
    patient_roster_document,
    patient_roster_workbook,
    patient_selection_document,
    patient_selection_workbook,
    pdf_response,
)
from routes.patient_views import (
    check_in_reason,
    check_in_requested,
    patient_profile_context,
    patient_records_context,
    patient_selection_context,
    process_archive_patients,
    address_prefill_args,
    address_prefill_form,
    process_register_patient,
    register_patient_context,
    registered_patient_name,
    save_and_register_another_requested,
)
from routes.vaccination_correction_views import process_vaccination_correction
from utils.security import login_required, role_required

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")

# Who works the clinical floor. Every screen in this file admits exactly these
# two roles; the permissions that differ between them are asked inside the views.
# The Barangay Official is not here, and neither is the Administrator, who has
# their own copies of these screens under /admin.
CLINICAL_FLOOR_ROLES = ("Health Staff", "Doctor")


@staff_bp.route('/dashboard')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_dashboard():
    # Every panel has room for a handful of rows; the counts above them are the
    # true totals, not the length of those lists. Same builder as the
    # Administrator dashboard -- see routes/dashboard_views.py.
    return render_template('staff_dashboard.html', **dashboard_context())


@staff_bp.route('/patient_records')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_patient_records():
    """Screen 03. `?search=` is the header's global search box arriving here --
    it is the only thing that box does, and this route is where it lands for
    this role. The term is not matched here; see patient_records_context() for
    why the screen's own toolbar filter is what runs it."""
    return render_template(
        'patient_records.html',
        **patient_records_context(search=request.args.get('search', '')),
    )


# Export Excel and Export PDF for the roster above. The Administrator's identical
# exports live in their own blueprint for exactly the reason the two render routes
# do: each role's URL space and guard stay explicit, and neither role is handed a
# URL the other's guard admits. Same context, same assembly, same two files --
# routes/roster_export.py -- so the roster this role downloads and the one the
# Administrator downloads are the same roster.
@staff_bp.route('/patient_records/export.xlsx')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_patient_records_excel():
    return excel_response(patient_roster_workbook(
        patient_records_context(),
        produced_by=exported_by(),
    ))


@staff_bp.route('/patient_records/export.pdf')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_patient_records_pdf():
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
@staff_bp.route('/patient_records/export-selection.xlsx', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_patient_selection_excel():
    context = patient_selection_context(request.form)
    if context is None:
        flash("Select at least one patient record to export.")
        return redirect(url_for("staff.staff_patient_records"))
    return excel_response(patient_selection_workbook(
        context,
        produced_by=exported_by(),
    ))


@staff_bp.route('/patient_records/export-selection.pdf', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_patient_selection_pdf():
    context = patient_selection_context(request.form)
    if context is None:
        flash("Select at least one patient record to export.")
        return redirect(url_for("staff.staff_patient_records"))
    return pdf_response(patient_selection_document(
        context,
        produced_by=exported_by(),
    ))


# POST only, and named apart from the Admin equivalent so the flat endpoint
# namespace in utils/endpoints.py stays unambiguous. Same guard shape as every
# other Staff view: a Barangay Official never reaches it.
@staff_bp.route('/patient_records/archive', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_archive_patients():
    flash(process_archive_patients(request.form))
    return redirect(url_for("staff.staff_patient_records"))


# The Health Center Staff copy of the correction endpoint. Named apart from the
# Admin one so the flat endpoint namespace in utils/endpoints.py stays
# unambiguous, and guarded the same way every other Staff view is.
#
# Both roles hold this because both record vaccinations: the health worker who
# ticked the wrong box is the person who will notice, and making them fetch an
# administrator to fix a typed date is how a wrong clinical record stays wrong.
# One shared process_vaccination_correction() serves both, so neither role's
# copy can validate or audit a correction differently from the other's.
@staff_bp.route('/patient_profile/<int:patient_id>/correct-vaccination', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_correct_vaccination(patient_id):
    corrected_for, reopen, message = process_vaccination_correction(
        request.form, session.get("user_id"), ip_address=request.remote_addr
    )
    # The same redisplay the Administrator's route does, for the same reason --
    # see the note there. Both roles reach one correction path, so both keep the
    # edit when it does not save.
    if reopen:
        context = patient_profile_context(corrected_for or patient_id)
        if context is not None:
            context["correction_state"] = reopen
            return render_template('patient_profile.html', **context)

    flash(message)
    return redirect(url_for(
        "staff.staff_patient_profile",
        patient_id=corrected_for or patient_id,
        tab="vaccine",
    ))


# Sealing one consultation as Restricted, or lifting a seal. POST only, like
# the correction route above and for the same reason: it changes who may read a
# clinical record, so there is no URL anyone can navigate to.
#
# THE DOCTOR'S ALONE, AND GUARDED DIFFERENTLY FROM EVERY ROUTE AROUND IT.
# Deciding that a diagnosis is privileged belongs to the role licensed to write
# one, and a role that cannot write a diagnosis has no business deciding whether
# one is sealed. This lived under /admin while the Administrator was taken to be
# the doctor; the Administrator is a barangay Kagawad, so there is now no
# /admin/... copy and this guard names the Doctor and nobody else. Health Center
# Staff reach this blueprint's other routes and are refused this one, and
# process_consultation_restriction() asks the stored role a second time in case
# this decorator is ever copied from a neighbour. Hiding the control in
# patient_profile.html is presentation; this is the permission.
#
# Named restrict_consultation, unprefixed, because it has no counterpart in any
# other blueprint for the flat endpoint namespace to confuse it with.
@staff_bp.route('/patient_profile/<int:patient_id>/restrict-consultation',
                methods=["POST"])
@login_required
@role_required("Doctor")
def restrict_consultation(patient_id):
    sealed_for, message = process_consultation_restriction(
        request.form, session.get("user_id"), ip_address=request.remote_addr
    )
    flash(message)
    # The record's own patient wins over the one in the URL, exactly as it does
    # in staff_correct_vaccination above: the id in the path is what the page
    # was rendered for, the id resolved here is read from the stored row.
    return redirect(url_for(
        "staff.staff_patient_profile",
        patient_id=sealed_for or patient_id,
        tab="consult",
    ))


@staff_bp.route('/patient_profile/<int:patient_id>')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_patient_profile(patient_id):
    context = patient_profile_context(patient_id)
    if context is None:
        flash("That patient record could not be found.")
        return redirect(url_for("staff.staff_patient_records"))
    return render_template('patient_profile.html', **context)


@staff_bp.route('/medicine_inventory')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_medicine_inventory():
    return render_template('medicine_inventory.html', **medicine_inventory_context())


# Export Excel and Export PDF for the item list above. Same guard as the screen,
# same context, and named apart from the Admin equivalents so the flat endpoint
# namespace in utils/endpoints.py stays unambiguous.
@staff_bp.route('/medicine_inventory/export.xlsx')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_medicine_inventory_excel():
    return excel_response(inventory_workbook(
        medicine_inventory_context(),
        produced_by=exported_by(),
    ))


@staff_bp.route('/medicine_inventory/export.pdf')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_medicine_inventory_pdf():
    return pdf_response(inventory_document(
        medicine_inventory_context(),
        produced_by=exported_by(),
    ))


# POST only, and named apart from the Admin equivalent so the flat endpoint
# namespace in utils/endpoints.py stays unambiguous -- the same arrangement
# staff_archive_patients above has.
@staff_bp.route('/medicine_inventory/archive', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_archive_medicine():
    flash(process_archive_medicine(request.form))
    return redirect(url_for("staff.staff_medicine_inventory"))


# No id in the URL means add mode; an id means edit that item. A successful save
# redirects to the list -- inventory has no per-item detail screen the way a
# patient has patient_profile. It does not need one to be read: the View icon on
# a Medicine Inventory row expands a read-only panel in place, route-free.
@staff_bp.route('/add_edit_medicine', methods=["GET", "POST"])
@staff_bp.route('/add_edit_medicine/<int:medicine_id>', methods=["GET", "POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_add_edit_medicine(medicine_id=None):
    item = None
    if medicine_id is not None:
        item = get_inventory_item_by_id(medicine_id)
        if item is None:
            flash("That inventory item could not be found.")
            return redirect(url_for("staff.staff_medicine_inventory"))

    if request.method == "POST":
        saved_id, context, message = process_add_edit_medicine(request.form, item=item)
        if saved_id:
            # The message names the fields that actually changed, so a save that
            # wrote back the stored values says so instead of claiming success.
            flash(message)
            return redirect(url_for("staff.staff_medicine_inventory"))
        return render_template('add_edit_medicine.html', **context)

    return render_template(
        'add_edit_medicine.html', **add_edit_medicine_context(item=item)
    )


# ?month=YYYY-MM moves the calendar panel; anything unusable falls back to the
# current month. The queue below it is always today's and is unaffected.
@staff_bp.route('/appointment_scheduling')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_appointment_scheduling():
    return render_template(
        'appointment_scheduling.html',
        **appointment_scheduling_context(month=request.args.get("month")),
    )


# Export Excel and Export PDF for Screen 08, this role's copies. ?month= is read
# for the same reason the Administrator's are: it is a real server-side parameter
# the calendar's arrows submit, so the file holds the month on screen.
@staff_bp.route('/appointment_scheduling/export.xlsx')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_appointment_scheduling_excel():
    return excel_response(appointment_workbook(
        appointment_scheduling_context(month=request.args.get("month")),
        produced_by=exported_by(),
    ))


@staff_bp.route('/appointment_scheduling/export.pdf')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_export_appointment_scheduling_pdf():
    return pdf_response(appointment_document(
        appointment_scheduling_context(month=request.args.get("month")),
        produced_by=exported_by(),
    ))


# POST only, and named apart from the Admin equivalents so the flat endpoint
# namespace in utils/endpoints.py stays unambiguous. Same guard shape as every
# other Staff view: a Barangay Official never reaches them.
@staff_bp.route('/appointment_scheduling/check-in', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_check_in_patient():
    flash(process_check_in(request.form, session.get("user_id")))
    return redirect(url_for("staff.staff_appointment_scheduling"))


@staff_bp.route('/appointment_scheduling/start-consultation', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_start_consultation():
    flash(process_start_consultation(request.form))
    return redirect(url_for("staff.staff_appointment_scheduling"))


# Completing is what frees the clinician for the next patient, so it is part of
# the queue rather than of the consultation record itself -- recording what
# happened during the visit is a separate screen and is not wired here.
@staff_bp.route('/appointment_scheduling/complete-consultation', methods=["POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_complete_consultation():
    flash(process_complete_consultation(request.form))
    return redirect(url_for("staff.staff_appointment_scheduling"))


# The consultation write-up itself. Anchored to the queue entry rather than to
# the patient: the record documents one specific visit, and the appointment id is
# what says which. A successful save completes that queue entry and lands on the
# patient's profile, where the new record is already the top row of Consultation
# History.
@staff_bp.route('/consultation/record/<int:appointment_id>', methods=["GET", "POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_record_consultation(appointment_id):
    if request.method == "POST":
        # ip_address is passed for the same reason the edit route below passes
        # it: a submission from this role carrying a diagnosis or a treatment
        # plan is refused server-side and the refusal is audited, and an entry
        # about a request that did not come from the form as it is drawn is worth
        # very little without the address it came from.
        patient_id, context, message = process_record_consultation(
            appointment_id, request.form, session.get("user_id"),
            ip_address=request.remote_addr,
        )
        flash(message)
        if patient_id:
            return redirect(url_for("staff.staff_patient_profile", patient_id=patient_id))
        if context is None:
            return redirect(url_for("staff.staff_appointment_scheduling"))
        return render_template('record_consultation.html', **context)

    context, message = record_consultation_context(appointment_id)
    if context is None:
        flash(message)
        return redirect(url_for("staff.staff_appointment_scheduling"))
    return render_template('record_consultation.html', **context)


# Editing a saved consultation. Same template, same validation; the difference is
# that this writes an audit_logs entry naming what changed, and refuses to move
# the patient or the visit date.
@staff_bp.route('/consultation/edit/<int:consultation_id>', methods=["GET", "POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_edit_consultation(consultation_id):
    if request.method == "POST":
        patient_id, context, message = process_edit_consultation(
            consultation_id, request.form, session.get("user_id"),
            ip_address=request.remote_addr,
        )
        flash(message)
        if patient_id:
            return redirect(url_for("staff.staff_patient_profile", patient_id=patient_id))
        if context is None:
            return redirect(url_for("staff.staff_patient_records"))
        return render_template('record_consultation.html', **context)

    context, message = edit_consultation_context(consultation_id)
    if context is None:
        flash(message)
        return redirect(url_for("staff.staff_patient_records"))
    return render_template('record_consultation.html', **context)


# View-only, per the confirmed team ruling: this role reads the broadcast history
# and sends nothing. That is enforced by absence -- there is deliberately no
# /staff/sms_notifications/send endpoint to post to, so hiding the compose button
# via can_broadcast is presentation, not the permission. See the header of
# routes/broadcast_views.py.
@staff_bp.route('/sms_notifications')
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_sms_notifications():
    return render_template('sms_notifications.html', **sms_notifications_context())


# Renamed from register_patient to staff_register_patient so the Administrator's
# equivalent can take the unprefixed name, matching how every other shared screen
# is paired (patient_records / staff_patient_records). The URL is unchanged.
# No id in the URL means add mode; an id means edit that patient.
@staff_bp.route('/register-patient', methods=["GET", "POST"])
@staff_bp.route('/register-patient/<int:patient_id>', methods=["GET", "POST"])
@login_required
@role_required(*CLINICAL_FLOOR_ROLES)
def staff_register_patient(patient_id=None):
    patient = None
    if patient_id is not None:
        patient = get_patient_by_id(patient_id)
        if patient is None:
            flash("That patient record could not be found.")
            return redirect(url_for("staff.staff_patient_records"))

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
                return redirect(url_for("staff.staff_appointment_scheduling"))
            # Save & Register Another. The record is saved -- the branch above
            # only runs on a row id returned by the very same
            # process_register_patient() the ordinary Save calls -- so what is
            # left is where to put the operator. At a community health drive the
            # answer is a fresh form, because the next person is already waiting.
            #
            # The address rides along on the query string and nothing else does.
            # Everyone registered in one sitting is from the same purok, so that
            # is the retyping worth removing; a name, a birth date or a blood
            # type carried into the next registration would be a wrong value
            # sitting in a field that looks filled in, which is the one failure
            # this must not have.
            if patient is None and save_and_register_another_requested(request.form):
                name = registered_patient_name(request.form)
                flash(
                    f"{name} registered successfully. The form below is ready for "
                    "the next patient, with the address kept."
                )
                return redirect(url_for(
                    "staff.staff_register_patient", **address_prefill_args(request.form)
                ))
            flash("Patient details updated." if patient else "Patient registered successfully.")
            return redirect(url_for("staff.staff_patient_profile", patient_id=saved_id))
        return render_template('register_patient.html', **context)

    return render_template(
        'register_patient.html',
        **register_patient_context(
            patient=patient,
            # Blank on an ordinary open. Set only when Save & Register Another
            # has just redirected here, and then it holds the address fields and
            # nothing else, so every other field renders exactly as blank.
            form=address_prefill_form(request.args) if patient is None else None,
            check_in=check_in_requested(request.args),
            check_in_reason_text=check_in_reason(request.args),
        ),
    )

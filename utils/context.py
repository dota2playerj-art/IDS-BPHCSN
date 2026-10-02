"""Template context shared by every render_template call."""
from flask import session

from models.inventory import get_low_stock_alert
from models.settings import (
    KEY_BARANGAY,
    KEY_CLOSING,
    KEY_MUNICIPALITY,
    KEY_NAME,
    KEY_OPENING,
    KEY_PROVINCE,
    address_line,
    display_time,
    get_settings,
)
from utils.dates import now, today
from utils.names import initials
from utils.roles import normalize_role
from utils.security import get_current_user
from utils.unavailable import UNAVAILABLE


# Longest search term the header box accepts and Patient Records will honour.
# It exists so a hand-typed URL cannot put a kilobyte of query string into the
# screen's search input; nothing in the register is anywhere near this long.
HEADER_SEARCH_MAX = 100


# The sidebar and the profile chip render an EMPTY circle when there is no name
# -- a signed-out visitor has no person to abbreviate, and a "?" there would read
# as a failure to look one up. The audit trail and the roster pass "?" instead,
# for the opposite reason; see utils/names.py.
def _initials(name):
    return initials(name)


def inject_system_name():
    """The system's name for every template (config.SYSTEM_NAME)."""
    import config

    return {"system_name": config.SYSTEM_NAME, "system_short_name": config.SYSTEM_SHORT_NAME}


def inject_role_context():
    user = get_current_user()
    if user:
        normalized_role = normalize_role(user["role"])
    else:
        normalized_role = normalize_role(session.get("role"))

    # Only the endpoints a role may actually reach are exposed. 09_UI_Architecture §2
    # restricts Barangay Official from Patient Records, Medicine Inventory and
    # the Patient Queue, so those names are simply absent for that role — a shared
    # template that reuses them then fails loudly instead of quietly emitting an Admin
    # URL the role would bounce straight off.
    #
    # These stay unqualified ("admin_dashboard", not "admin.admin_dashboard"): the
    # templates pass them straight to url_for(), and utils/endpoints.py maps the flat
    # names onto their blueprint-qualified endpoints.
    # The Doctor is on the clinical floor with Health Center Staff: the same
    # /staff/* screens, so the same endpoint names (routes/staff.py says why the
    # two share a blueprint). What the Doctor may do on those screens that staff
    # may not is not an endpoint question and is not decided here -- see
    # models/consultations.py can_diagnose().
    if normalized_role in {"health staff", "doctor"}:
        context = {
            "sidebar_role_label": "Health Staff",
            "sidebar_user_name": "Health Center Staff",
            "sidebar_user_initials": "HS",
            "dashboard_endpoint": "staff_dashboard",
            "patient_records_endpoint": "staff_patient_records",
            "patient_profile_endpoint": "staff_patient_profile",
            # Correcting one recorded vaccination from the profile's Immunization
            # Record tab. Present for exactly the roles that record
            # vaccinations in the first place -- the Barangay Official has no
            # Patient Profile at all, so the name is simply absent for them and
            # a shared template reusing it would fail loudly rather than emit a
            # URL they bounce off.
            "correct_vaccination_endpoint": "staff_correct_vaccination",
            # Recording a dose given elsewhere (a card seen, or a parent's word), and
            # changing or removing such a record, from the Immunization Record tab
            # (Task 9). Staff and the Doctor only: the other roles get no name, so a
            # template reusing one of these fails loudly rather than emit a URL they
            # would bounce off.
            "record_elsewhere_endpoint": "staff_record_dose_elsewhere",
            "change_elsewhere_endpoint": "staff_change_dose_elsewhere",
            "remove_elsewhere_endpoint": "staff_remove_dose_elsewhere",
            "register_patient_endpoint": "staff_register_patient",
            "archive_patients_endpoint": "staff_archive_patients",
            "medicine_inventory_endpoint": "staff_medicine_inventory",
            "add_edit_medicine_endpoint": "staff_add_edit_medicine",
            "archive_medicine_endpoint": "staff_archive_medicine",
            "appointment_scheduling_endpoint": "staff_appointment_scheduling",
            "check_in_patient_endpoint": "staff_check_in_patient",
            "start_consultation_endpoint": "staff_start_consultation",
            "complete_consultation_endpoint": "staff_complete_consultation",
            "change_service_endpoint": "staff_change_service",
            "send_to_doctor_endpoint": "staff_send_to_doctor",
            "see_patient_endpoint": "staff_see_patient",
            "mark_left_endpoint": "staff_mark_left",
            "undo_left_endpoint": "staff_undo_left",
            "record_consultation_endpoint": "staff_record_consultation",
            "edit_consultation_endpoint": "staff_edit_consultation",
            "sms_notifications_endpoint": "staff_sms_notifications",
            # The Service Schedule, read-only. There is no add/edit/delete
            # endpoint in this branch, and none in the Barangay Official's:
            # the only routes that write to the schedule are under /admin, so a
            # template reusing one of those names for these roles fails loudly
            # rather than emitting a URL they would bounce off.
            "service_schedule_endpoint": "staff_service_schedule",
            # Export Excel and Export PDF on Screens 03, 06 and 08. Named per
            # role for the same reason every endpoint above is: these three
            # templates are each rendered by two blueprints, and each role must
            # be handed the download route its own guard admits. A shared literal
            # would send one of the two roles to a URL it bounces straight off.
            "patient_records_excel_endpoint": "staff_export_patient_records_excel",
            "patient_records_pdf_endpoint": "staff_export_patient_records_pdf",
            # The bulk bar's pair on Screen 03, which post the ticked ids rather
            # than fetching the register. Named per role like every endpoint
            # above, and for the same reason.
            "patient_selection_excel_endpoint": "staff_export_patient_selection_excel",
            "patient_selection_pdf_endpoint": "staff_export_patient_selection_pdf",
            "medicine_inventory_excel_endpoint": "staff_export_medicine_inventory_excel",
            "medicine_inventory_pdf_endpoint": "staff_export_medicine_inventory_pdf",
            "appointments_excel_endpoint": "staff_export_appointment_scheduling_excel",
            "appointments_pdf_endpoint": "staff_export_appointment_scheduling_pdf",
        }
        if normalized_role == "doctor":
            # Defaults only, as for every role: the account's own full name
            # replaces the name and initials further down. The label under it
            # names the role, because the demo account's name is a placeholder
            # until the RHU physician's real name is confirmed.
            context.update({
                "sidebar_role_label": "Doctor",
                "sidebar_user_name": "Doctor",
                "sidebar_user_initials": "DR",
                # Sealing one consultation as Restricted, from the profile's
                # Consultation History tab. Present for THIS ROLE ONLY: the
                # route behind it is guarded to the Doctor, because deciding
                # that a diagnosis is privileged belongs to the role licensed to
                # write one. patient_profile.html guards on `is defined`, so
                # every other role gets no control rather than a URL it would
                # bounce off.
                "restrict_consultation_endpoint": "restrict_consultation",
                # Reports & Analytics and its two exports, the same screen the
                # Administrator and the Barangay Official read, through the
                # Doctor's own three routes on /staff (routes/staff.py says why
                # this role and not Health Center Staff). Named per role for the
                # reason given on the Administrator's copies below.
                "reports_analytics_endpoint": "staff_reports_analytics",
                "reports_excel_endpoint": "staff_export_reports_analytics_excel",
                "reports_pdf_endpoint": "staff_export_reports_analytics_pdf",
            })
    elif normalized_role == "admin":
        context = {
            # The line under the name in the profile chip. It names the person
            # holding the role, not the role itself: the Administrator of this
            # system is a Kagawad chairing the barangay's Health
            # Committee. The SYSTEM role is still "Admin"/"Administrator" --
            # that spelling lives in models/users.py ROLE_CHOICES, is what
            # role_required() and every guard compare against, and is what User
            # Management shows in the Role column. Only the chip's subtitle
            # describes the person, so only it says Kagawad.
            "sidebar_role_label": "Kagawad, Health Committee",
            "sidebar_user_name": "Administrator",
            "sidebar_user_initials": "AD",
            "dashboard_endpoint": "admin_dashboard",
            "patient_records_endpoint": "patient_records",
            "patient_profile_endpoint": "patient_profile",
            # No restrict_consultation_endpoint. The Administrator held it while
            # taken to be the doctor; sealing is the Doctor's now, and there is
            # no /admin/... route behind the name to hand over.
            "medicine_inventory_endpoint": "medicine_inventory",
            "add_edit_medicine_endpoint": "add_edit_medicine",
            "archive_medicine_endpoint": "archive_medicine",
            "appointment_scheduling_endpoint": "appointment_scheduling",
            "sms_notifications_endpoint": "sms_notifications",
            # The Service Schedule, and the three writes only this role has.
            # schedule_views._can_edit() decides whether the form is drawn; these
            # names are what it posts to, and they exist for no other role.
            "service_schedule_endpoint": "service_schedule",
            "add_schedule_entry_endpoint": "add_service_schedule_entry",
            "edit_schedule_entry_endpoint": "edit_service_schedule_entry",
            "delete_schedule_entry_endpoint": "delete_service_schedule_entry",
            # Only the two broadcast-holding roles get a send endpoint at all. The
            # Health Staff branch above has none, which is what makes that role
            # view-only -- there is no URL for a forged POST to reach.
            "send_broadcast_endpoint": "send_sms_broadcast",
            "reports_analytics_endpoint": "reports_analytics",
            # Export Excel and Export PDF on Screen 10. Named per role for the same
            # reason every endpoint above is: reports_analytics.html is one template
            # rendered by three blueprints, and each role must be handed the download
            # route its own guard admits. A shared literal would send two of the
            # three roles to a URL they bounce straight off.
            "reports_excel_endpoint": "export_reports_analytics_excel",
            "reports_pdf_endpoint": "export_reports_analytics_pdf",
            # The Administrator's copies of the three shared screens' exports,
            # plus User Management's, which only this role has at all -- Screen 11
            # is Admin-only, so the names are absent for the other two and
            # user_management.html would fail loudly rather than quietly emitting
            # a URL they cannot open. Same arrangement as community_excel_endpoint
            # below.
            "patient_records_excel_endpoint": "export_patient_records_excel",
            "patient_records_pdf_endpoint": "export_patient_records_pdf",
            "patient_selection_excel_endpoint": "export_patient_selection_excel",
            "patient_selection_pdf_endpoint": "export_patient_selection_pdf",
            "medicine_inventory_excel_endpoint": "export_medicine_inventory_excel",
            "medicine_inventory_pdf_endpoint": "export_medicine_inventory_pdf",
            "appointments_excel_endpoint": "export_appointment_scheduling_excel",
            "appointments_pdf_endpoint": "export_appointment_scheduling_pdf",
            "users_excel_endpoint": "export_user_management_excel",
            "users_pdf_endpoint": "export_user_management_pdf",
        }
    elif normalized_role == "barangay official":
        context = {
            "sidebar_role_label": "Barangay Official",
            "sidebar_user_name": "Barangay Official",
            "sidebar_user_initials": "BO",
            "dashboard_endpoint": "official_dashboard",
            "sms_notifications_endpoint": "official_sms_notifications",
            "send_broadcast_endpoint": "official_send_sms_broadcast",
            # Read-only, like the clinical floor's copy; see the note there.
            "service_schedule_endpoint": "official_service_schedule",
            "reports_analytics_endpoint": "official_reports_analytics",
            "reports_excel_endpoint": "official_export_reports_analytics_excel",
            "reports_pdf_endpoint": "official_export_reports_analytics_pdf",
            # Screen 18's own exports. Only this role reaches Community Reports at
            # all, so the names are absent for the other two -- and community_reports.html
            # would fail loudly rather than quietly emitting a URL they cannot open.
            "community_excel_endpoint": "export_community_reports_excel",
            "community_pdf_endpoint": "export_community_reports_pdf",
        }
    else:
        context = {
            "sidebar_role_label": "",
            "sidebar_user_name": "",
            "sidebar_user_initials": "",
            "dashboard_endpoint": "dashboard",
        }

    context["current_role"] = normalized_role
    # The care team: the Doctor and Health Center Staff (Task 5c). Only they see
    # clinical fields, contact numbers and the controls that write a patient or a
    # clinical record. The Administrator runs the system and sees demographics,
    # counts and read-only views. The data builders enforce this on the server;
    # templates read this flag only to leave out what was never fetched.
    context["care_team_view"] = normalized_role in {"doctor", "health staff"}

    # Today, at the health center, for every template that prints it. The page
    # subtitles on the dashboards and the Barangay Official screens each used to
    # carry their own frozen "Tuesday, July 7, 2026"; they now render this
    # through the full_date filter, so there is one date and one place it comes
    # from -- utils.dates.today(), the same clock expiry, ages and the queue use.
    context["clinic_today"] = today()

    # When this page was built, for the header pill that used to read "Synced
    # just now". Taken here rather than in each route because the pill lives in
    # base.html and every screen extends it, and taken from utils.dates.now() --
    # the one source of "now" in the application -- so the pill and the dates the
    # screen prints beside it are read off the same clock. See base.html for why
    # the render moment is the honest answer to what the old pill was claiming.
    context["rendered_at"] = now()

    # The header search box's own cap, matched to what Patient Records will do
    # with the term. Kept next to the box's other constants rather than in the
    # template so the form's maxlength and the server's truncation are one number.
    context["header_search_max"] = HEADER_SEARCH_MAX

    # The signed-in account's own name, when there is one. The sidebar labels
    # above are per-role defaults from before authentication carried a real user;
    # preferring the session's actual account is what stops one screen greeting
    # "Melissa" while the sidebar says "Angela Cruz" and the database says
    # "Health Center Staff" -- three names for one login.
    # get_current_user() hands back a sqlite3.Row, which indexes but has no .get().
    account_name = ""
    if user is not None and "full_name" in user.keys():
        account_name = (user["full_name"] or "").strip()
    if account_name:
        context["sidebar_user_name"] = account_name
        context["sidebar_user_initials"] = _initials(account_name)
    context["current_user_name"] = context.get("sidebar_user_name", "")

    # The sidebar's Medicine Inventory badge lives in base.html, which every screen
    # extends, so the count has to come from here rather than from each route. Only
    # the roles that hold inventory access get it: 09_UI_Architecture §2 keeps
    # the Barangay Official out of inventory entirely, and their sidebar has no
    # Medicine Inventory item to badge in the first place.
    #
    # Read from models.inventory.get_low_stock_alert() -- the same call the two
    # dashboards use -- so the badge cannot drift from the figure the dashboards
    # and Medicine Inventory itself report.
    if normalized_role in {"admin", "doctor", "health staff"}:
        context["low_stock_count"] = get_low_stock_alert()["low_stock_count"]

    # Broadcast authority per the confirmed team ruling: Administrator and Barangay
    # Official compose/send/schedule community announcements and SMS; Health Center
    # Staff is view-only (individual patient scheduling is their scope, not broadcast),
    # and so is the Doctor, who sees SMS Notifications exactly as staff do.
    context["can_broadcast"] = normalized_role in {"admin", "barangay official"}


    # THE HEALTH CENTER'S OWN IDENTITY, ON EVERY RENDER.
    #
    # Here rather than in each route for the reason low_stock_count and
    # clinic_today are here: the facility's name is drawn by base.html and by the
    # eyebrow line on every screen that extends it, so a per-route context could
    # not reach all of them, and thirteen templates would each need it passed in.
    #
    # Before this it was not passed in at all -- it was the literal string
    # "Barangay Poblacion Health Center", typed into fourteen templates and five
    # Python modules. Correcting the facility's name meant finding all nineteen.
    # It is now one stored value (models/settings.py), read once per request and
    # handed to every template, and it is the SAME value models/appointment_sms.py
    # puts at the front of a text message and the three export modules print on a
    # letterhead -- so a printed record, a downloaded workbook, a screen header
    # and a patient's phone cannot name the facility differently.
    #
    # `hours` is a rendered label rather than the stored 24-hour strings, because
    # nothing on a page shows a time as "17:00"; the stored pair is what
    # models/appointments.py builds the bookable slots from.
    settings_values = get_settings()
    context["health_center"] = {
        "name": settings_values[KEY_NAME],
        "barangay": settings_values[KEY_BARANGAY],
        "municipality": settings_values[KEY_MUNICIPALITY],
        "province": settings_values[KEY_PROVINCE],
        "address": address_line(),
        "opening": display_time(settings_values[KEY_OPENING]),
        "closing": display_time(settings_values[KEY_CLOSING]),
    }

    # Why each deliberately disabled control is disabled. On every render rather
    # than per route, because the same reasons are quoted by screens built from
    # different blueprints -- see utils/unavailable.py for why they are shared.
    context["unavailable"] = UNAVAILABLE
    return context

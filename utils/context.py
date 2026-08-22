"""Template context shared by every render_template call."""
from flask import session

from models.inventory import get_low_stock_alert
from utils.dates import now, today
from utils.roles import normalize_role
from utils.security import get_current_user
from utils.unavailable import UNAVAILABLE


# Longest search term the header box accepts and Patient Records will honour.
# It exists so a hand-typed URL cannot put a kilobyte of query string into the
# screen's search input; nothing in the register is anywhere near this long.
HEADER_SEARCH_MAX = 100


def _initials(name):
    """'Dr. Joshua Reyes' -> 'JR'. Titles skipped so the avatar reads as a person."""
    skip = {"dr.", "dr", "mr.", "mrs.", "ms.", "engr."}
    parts = [p for p in str(name or "").split() if p.lower() not in skip]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def inject_role_context():
    user = get_current_user()
    if user:
        normalized_role = normalize_role(user["role"])
    else:
        normalized_role = normalize_role(session.get("role"))

    # Only the endpoints a role may actually reach are exposed. 09_UI_Architecture §2
    # restricts Barangay Official from Patient Records, Medicine Inventory and
    # Appointment Scheduling, so those names are simply absent for that role — a shared
    # template that reuses them then fails loudly instead of quietly emitting an Admin
    # URL the role would bounce straight off.
    #
    # These stay unqualified ("admin_dashboard", not "admin.admin_dashboard"): the
    # templates pass them straight to url_for(), and utils/endpoints.py maps the flat
    # names onto their blueprint-qualified endpoints.
    if normalized_role == "health staff":
        context = {
            "sidebar_role_label": "Health Staff",
            "sidebar_user_name": "Angela Cruz",
            "sidebar_user_initials": "AC",
            "dashboard_endpoint": "staff_dashboard",
            "patient_records_endpoint": "staff_patient_records",
            "patient_profile_endpoint": "staff_patient_profile",
            "register_patient_endpoint": "staff_register_patient",
            "archive_patients_endpoint": "staff_archive_patients",
            "medicine_inventory_endpoint": "staff_medicine_inventory",
            "add_edit_medicine_endpoint": "staff_add_edit_medicine",
            "archive_medicine_endpoint": "staff_archive_medicine",
            "appointment_scheduling_endpoint": "staff_appointment_scheduling",
            "check_in_patient_endpoint": "staff_check_in_patient",
            "book_appointment_endpoint": "staff_book_appointment",
            "cancel_appointment_endpoint": "staff_cancel_appointment",
            "reschedule_appointment_endpoint": "staff_reschedule_appointment",
            "start_consultation_endpoint": "staff_start_consultation",
            "complete_consultation_endpoint": "staff_complete_consultation",
            "record_consultation_endpoint": "staff_record_consultation",
            "edit_consultation_endpoint": "staff_edit_consultation",
            "sms_notifications_endpoint": "staff_sms_notifications",
            # Export Excel and Export PDF on Screens 03, 06 and 08. Named per
            # role for the same reason every endpoint above is: these three
            # templates are each rendered by two blueprints, and each role must
            # be handed the download route its own guard admits. A shared literal
            # would send one of the two roles to a URL it bounces straight off.
            "patient_records_excel_endpoint": "staff_export_patient_records_excel",
            "patient_records_pdf_endpoint": "staff_export_patient_records_pdf",
            "medicine_inventory_excel_endpoint": "staff_export_medicine_inventory_excel",
            "medicine_inventory_pdf_endpoint": "staff_export_medicine_inventory_pdf",
            "appointments_excel_endpoint": "staff_export_appointment_scheduling_excel",
            "appointments_pdf_endpoint": "staff_export_appointment_scheduling_pdf",
        }
    elif normalized_role == "admin":
        context = {
            "sidebar_role_label": "Administrator",
            "sidebar_user_name": "Dr. Joshua Reyes",
            "sidebar_user_initials": "JR",
            "dashboard_endpoint": "admin_dashboard",
            "patient_records_endpoint": "patient_records",
            "patient_profile_endpoint": "patient_profile",
            "register_patient_endpoint": "register_patient",
            "archive_patients_endpoint": "archive_patients",
            "medicine_inventory_endpoint": "medicine_inventory",
            "add_edit_medicine_endpoint": "add_edit_medicine",
            "archive_medicine_endpoint": "archive_medicine",
            "appointment_scheduling_endpoint": "appointment_scheduling",
            "check_in_patient_endpoint": "check_in_patient",
            "book_appointment_endpoint": "book_appointment",
            "cancel_appointment_endpoint": "cancel_appointment",
            "reschedule_appointment_endpoint": "reschedule_appointment",
            "start_consultation_endpoint": "start_consultation",
            "complete_consultation_endpoint": "complete_consultation",
            "record_consultation_endpoint": "record_consultation",
            "edit_consultation_endpoint": "edit_consultation",
            "sms_notifications_endpoint": "sms_notifications",
            # Only the two broadcast-holding roles get a send endpoint at all. The
            # Health Staff branch above has none, which is what makes that role
            # view-only -- there is no URL for a forged POST to reach.
            "send_broadcast_endpoint": "send_sms_broadcast",
            "reports_analytics_endpoint": "reports_analytics",
            # Export Excel and Export PDF on Screen 10. Named per role for the same
            # reason every endpoint above is: reports_analytics.html is one template
            # rendered by two blueprints, and each role must be handed the download
            # route its own guard admits. A shared literal would send one of the two
            # roles to a URL it bounces straight off.
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
            "sidebar_user_name": "Hon. Roberto Villanueva",
            "sidebar_user_initials": "RV",
            "dashboard_endpoint": "official_dashboard",
            "sms_notifications_endpoint": "official_sms_notifications",
            "send_broadcast_endpoint": "official_send_sms_broadcast",
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
    # the two roles that hold inventory access get it: 09_UI_Architecture §2 keeps
    # the Barangay Official out of inventory entirely, and their sidebar has no
    # Medicine Inventory item to badge in the first place.
    #
    # Read from models.inventory.get_low_stock_alert() -- the same call the two
    # dashboards use -- so the badge cannot drift from the figure the dashboards
    # and Medicine Inventory itself report.
    if normalized_role in {"admin", "health staff"}:
        context["low_stock_count"] = get_low_stock_alert()["low_stock_count"]

    # Broadcast authority per the confirmed team ruling: Administrator and Barangay
    # Official compose/send/schedule community announcements and SMS; Health Center
    # Staff is view-only (individual patient scheduling is their scope, not broadcast).
    context["can_broadcast"] = normalized_role in {"admin", "barangay official"}

    # Why each deliberately disabled control is disabled. On every render rather
    # than per route, because the same reasons are quoted by screens built from
    # different blueprints -- see utils/unavailable.py for why they are shared.
    context["unavailable"] = UNAVAILABLE
    return context

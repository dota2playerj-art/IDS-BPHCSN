"""Protection against requests sent from other websites (CSRF).

Every POST must carry the token from a page this app served. A form carries it
as a hidden field: put {{ csrf_field() }} first inside the <form>. A script
request carries it in the X-CSRFToken header: static/js/csrf.js reads it from
the meta tag in base.html. Flask-WTF checks it before any view runs.

The check is on for every POST, so a form that forgets the field fails at once
instead of working without protection. tests/verify_csrf.py fails on any POST
form in templates/ without the field.

The token lives in the session, so signing out, or a session ending, makes the
old pages' tokens stop working. A refused request gets the "Your session
expired" page (a script gets JSON), and nothing it asked for is done.
"""
from flask import jsonify, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from markupsafe import Markup

from models.audit import ACTION_REQUEST_REFUSED, MODULE_AUTH, log_action
from models.users import get_user_by_id
from utils.security import FETCH_HEADER, FETCH_HEADER_VALUE

csrf = CSRFProtect()

# The screen each URL belongs to, by its first part after /admin, /staff or
# /official. Used only to say in the audit trail where a refused request went.
SCREEN_NAMES = {
    "login": "Sign In",
    "logout": "Sign Out",
    "account": "My Account",
    "session": "the session check",
    "patient_records": "Patient Records",
    "patient_profile": "Patient Profile",
    "register_patient": "Register Patient",
    "register-patient": "Register Patient",
    "medicine_inventory": "Medicine Inventory",
    "add_edit_medicine": "Medicine Inventory",
    "appointment_scheduling": "Patient Queue",
    "consultation": "Record Consultation",
    "sms_notifications": "SMS Notifications",
    "user_management": "User Management",
    "settings": "Settings",
    "service_schedule": "Service Schedule",
}
ROLE_PREFIXES = ("admin", "staff", "official")


def csrf_field():
    """The hidden input every POST form carries. Use {{ csrf_field() }}."""
    return Markup('<input type="hidden" name="csrf_token" value="%s">') % generate_csrf()


def screen_name(path):
    """The screen a URL path belongs to, for the audit trail."""
    parts = [part for part in path.split("/") if part]
    if parts and parts[0] in ROLE_PREFIXES:
        parts = parts[1:]
    if parts and parts[0] in SCREEN_NAMES:
        return SCREEN_NAMES[parts[0]]
    return path


def _log_refusal():
    """One audit entry, when the request came from a known account.

    audit_logs needs an account, so a request with no one signed in (the login
    form, or a session that already ended) is not recorded.
    """
    user_id = session.get("user_id")
    if not user_id or get_user_by_id(user_id) is None:
        return
    log_action(
        user_id,
        ACTION_REQUEST_REFUSED,
        MODULE_AUTH,
        f"The request was sent to {screen_name(request.path)}.",
        request.remote_addr,
    )


def refuse_request(error):
    """The answer to a POST without a valid token. Nothing it asked for is done."""
    _log_refusal()
    login_url = url_for("auth.login")
    if request.headers.get(FETCH_HEADER) == FETCH_HEADER_VALUE:
        return jsonify({"refused": True, "login_url": login_url}), 400
    return render_template("session_expired.html", login_url=login_url), 400


def init_csrf(app):
    """Turn the check on for every POST, and give templates csrf_field()."""
    csrf.init_app(app)
    app.jinja_env.globals["csrf_field"] = csrf_field
    app.register_error_handler(CSRFError, refuse_request)

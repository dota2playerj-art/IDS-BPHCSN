"""Authentication and the role-dispatch entry points.

Mounted at the site root, so these keep their original URLs: /, /login,
/logout, /dashboard.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from models.users import get_user_by_username
from utils.roles import normalize_role
from utils.security import get_current_user, login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = request.args.get("error")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_username(username)

        password_verified = False
        if user is not None:
            user_dict = dict(user)
            password_hash = user_dict.get("password_hash")
            if password_hash:
                password_verified = check_password_hash(password_hash, password)
            elif user_dict.get("password"):
                password_verified = user_dict["password"] == password

        if user is not None and password_verified:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]

            normalized_role = normalize_role(user["role"])
            if normalized_role == "admin":
                session["role"] = "Admin"
                return redirect(url_for("admin.admin_dashboard"))
            elif normalized_role == "health staff":
                session["role"] = "Health Staff"
                return redirect(url_for("staff.staff_dashboard"))
            elif normalized_role == "barangay official":
                session["role"] = "Barangay Official"
                return redirect(url_for("official.official_dashboard"))
            else:
                session["role"] = user["role"]
                return redirect(url_for("auth.dashboard"))

        flash("Invalid security credentials.")
        return redirect(url_for("auth.login", error="Invalid security credentials."))

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    normalized_role = normalize_role(user["role"])
    if normalized_role == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    if normalized_role == "health staff":
        return redirect(url_for("staff.staff_dashboard"))
    return redirect(url_for("official.official_dashboard"))

"""Session lookup and the RBAC decorators."""
from functools import wraps

from flask import redirect, session, url_for

from models.users import get_user_by_id
from utils.roles import normalize_role


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for("auth.login"))
            normalized_user_role = normalize_role(user["role"])
            allowed = {normalize_role(item) for item in allowed_roles}
            if normalized_user_role not in allowed:
                return redirect(url_for("auth.dashboard"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator

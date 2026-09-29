"""Protection against requests sent from other websites (CSRF).

Every POST must carry the token from a page this app served. A form carries it
as a hidden field: put {{ csrf_field() }} first inside the <form>. A script
request carries it in the X-CSRFToken header: static/js/csrf.js reads it from
the meta tag in base.html. Flask-WTF checks it before any view runs.

The check is on for every POST, so a form that forgets the field fails at once
instead of working without protection. tests/verify_csrf.py fails on any POST
form in templates/ without the field.
"""
from flask_wtf.csrf import CSRFProtect, generate_csrf
from markupsafe import Markup

csrf = CSRFProtect()


def csrf_field():
    """The hidden input every POST form carries. Use {{ csrf_field() }}."""
    return Markup('<input type="hidden" name="csrf_token" value="%s">') % generate_csrf()


def init_csrf(app):
    """Turn the check on for every POST, and give templates csrf_field()."""
    csrf.init_app(app)
    app.jinja_env.globals["csrf_field"] = csrf_field

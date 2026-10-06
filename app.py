"""IDS-BPHCSN — application entry point.

04_DEVELOPMENT_GUIDE.md §Flask Guidelines: "Do not place all code inside app.py.
Keep responsibilities separated." Responsibilities now live in:

    config.py    configuration (secret key, database and schema paths)
    database/    connection handling and schema initialisation
    models/      data access, one module per entity
    routes/      HTTP endpoints, one blueprint per role surface
    utils/       cross-cutting helpers (RBAC, role/phone formatting, SMS,
                 template context, endpoint aliasing, form tokens)

This module creates the app, wires those pieces together, and nothing else.
"""
import os

from flask import Flask, request

import config
from database import init_db
from routes import register_blueprints
from utils.context import inject_role_context, inject_system_name
from utils.csrf import init_csrf
from utils.dates import register_date_filters
from utils.errors import init_error_pages
from utils.small_counts import register_small_count_helpers
from utils.endpoints import register_flat_endpoint_aliases
from utils.sealed_crypto import key_problem as sealed_key_problem


def ensure_db_ready():
    init_db()


def no_store(response):
    """Stop the browser caching signed-in pages.

    Two reasons. A saved edit redirects back to a list the browser has already
    fetched; with no cache directive it may reuse that copy and show the old
    figure, which reads as the save having been dropped. And every one of these
    pages carries patient or inventory records, which should not sit in the disk
    cache for the Back button to surface after a logout.

    Static assets are left alone -- there is nothing user-specific in them.
    """
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    # No other site may put a page of this system inside a frame.
    response.headers["X-Frame-Options"] = "DENY"
    return response


def create_app():
    # Refuse to start without a proper secret key. The key signs every session
    # cookie, so a missing or public key would let anyone sign in as anyone.
    problem = config.secret_key_problem(config.SECRET_KEY)
    if problem:
        raise SystemExit(f"{config.SYSTEM_SHORT_NAME} cannot start. " + problem)
    # Refuse to start without the key for sealed records, too. Without it the
    # Doctor could seal a record that nobody can ever open again.
    problem = sealed_key_problem(os.environ.get("SEALED_DATA_KEY", ""))
    if problem:
        raise SystemExit(f"{config.SYSTEM_SHORT_NAME} cannot start. " + problem)

    app = Flask(__name__)
    app.config.from_object(config)

    register_blueprints(app)
    # Must follow blueprint registration: it reads the registered view functions
    # so templates can keep addressing endpoints by their unqualified names.
    register_flat_endpoint_aliases(app)

    app.context_processor(inject_role_context)
    app.context_processor(inject_system_name)
    register_date_filters(app)
    register_small_count_helpers(app)
    app.before_request(ensure_db_ready)
    # Every POST must carry the form token (utils/csrf.py). Registered after
    # ensure_db_ready, so the database exists before the check runs.
    init_csrf(app)
    app.after_request(no_store)
    init_error_pages(app)

    return app


app = create_app()


def main():
    """Serve the app. Local mode, or network mode (HTTPS) when IDS_NETWORK=1: utils/server.py."""
    from utils.server import run

    run(app)


if __name__ == "__main__":
    main()

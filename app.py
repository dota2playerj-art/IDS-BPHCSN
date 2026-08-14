"""IDS-BPHCSN — application entry point.

04_DEVELOPMENT_GUIDE.md §Flask Guidelines: "Do not place all code inside app.py.
Keep responsibilities separated." Responsibilities now live in:

    config.py    configuration (secret key, database and schema paths)
    database/    connection handling and schema initialisation
    models/      data access, one module per entity
    routes/      HTTP endpoints, one blueprint per role surface
    utils/       cross-cutting helpers (RBAC, role/phone formatting, SMS,
                 template context, endpoint aliasing)

This module creates the app, wires those pieces together, and nothing else.
"""
from flask import Flask, request

import config
from database import init_db
from routes import register_blueprints
from utils.context import inject_role_context
from utils.dates import register_date_filters
from utils.endpoints import register_flat_endpoint_aliases


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
    return response


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    register_blueprints(app)
    # Must follow blueprint registration: it reads the registered view functions
    # so templates can keep addressing endpoints by their unqualified names.
    register_flat_endpoint_aliases(app)

    app.context_processor(inject_role_context)
    register_date_filters(app)
    app.before_request(ensure_db_ready)
    app.after_request(no_store)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5001)

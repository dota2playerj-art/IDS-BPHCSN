"""HTTP endpoints, split into one blueprint per role surface.

The grouping follows the URL space, which in this app is already the RBAC
boundary: every /admin/* route is role_required("Admin"), every /staff/* route
admits the clinical floor -- Health Center Staff and the Doctor -- and
/official/* is the Barangay Official's. So a blueprint's url_prefix and its
guard say the same thing, and adding a route to the wrong file is immediately
visible in its URL.
"""
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.official import official_bp
from routes.staff import staff_bp

BLUEPRINTS = (auth_bp, admin_bp, staff_bp, official_bp)


def register_blueprints(app):
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

"""User accounts and authentication lookups."""
import sqlite3

from werkzeug.security import generate_password_hash

from database.connection import get_db

# The single source of truth for the three login accounts (audit item 21 --
# seed_users.py was removed so these are the only credentials in the project).
# full_name matches the personas rendered in the sidebar by inject_role_context().
DEMO_USERS = [
    ("admin", "(retired demo password)", "Dr. Joshua Reyes", "Admin"),
    ("staff", "(retired demo password)", "Health Center Staff", "Health Center Staff"),
    ("official", "(retired demo password)", "Barangay Official", "Barangay Official"),
]


def seed_demo_users():
    conn = get_db()
    user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count == 0:
        for username, password, full_name, role in DEMO_USERS:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), full_name, role),
            )
        conn.commit()
    conn.close()


# Whose names may appear in "Assign to" on a booking. The Barangay Official is
# excluded for the same reason they cannot open Appointment Scheduling at all --
# they hold no clinical role, so a visit cannot be assigned to them.
CLINICAL_ROLES = ("Admin", "Health Center Staff")


def get_clinical_staff():
    """Active users a future appointment can be assigned to, by name.

    Read from the users table rather than hardcoded in the form, so the dropdown
    cannot offer somebody the assigned_staff_id foreign key would reject -- and
    so a deactivated account stops being offered without a template edit.
    """
    placeholders = ", ".join("?" for _ in CLINICAL_ROLES)
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT id, full_name, role
        FROM users
        WHERE is_active = 1 AND role IN ({placeholders})
        ORDER BY full_name COLLATE NOCASE
        """,
        CLINICAL_ROLES,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_users():
    """Every account on the system, for the User Management roster.

    Deliberately not get_clinical_staff(): that one answers a different
    question -- who a visit may be assigned to -- so it drops the Barangay
    Official and hides deactivated accounts. A roster that did either would be
    an incomplete list of who can sign in, which is the one thing this screen
    exists to show. password_hash is the only column left out.

    Ordered by role then name so the three accounts always read in the same
    order, rather than in whatever order the rows happen to come back in.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, username, full_name, role, email, phone, is_active, created_at
        FROM users
        ORDER BY
            CASE role
                WHEN 'Admin' THEN 0
                WHEN 'Health Center Staff' THEN 1
                WHEN 'Barangay Official' THEN 2
                ELSE 3
            END,
            full_name COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def get_user_by_username(username):
    """Fetch the row the login form needs.

    Swallows OperationalError so a request that arrives before the schema exists
    is treated as a failed login rather than a 500.
    """
    conn = get_db()
    user = None

    try:
        user = conn.execute(
            "SELECT id, username, role, full_name, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    except sqlite3.OperationalError:
        user = None
    finally:
        conn.close()

    return user

# -*- coding: utf-8 -*-
"""Add User / Deactivate / Reactivate — end-to-end verification.

Runs on a fresh test database built by tests/_support.py, so the live
database gains no test accounts and no test audit rows.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import app as appmod  # noqa: E402
from werkzeug.security import check_password_hash  # noqa: E402

SCRATCH = _support.DB_PATH

app = appmod.app
app.config["DATABASE"] = SCRATCH
app.config["TESTING"] = True
app.config["SECRET_KEY"] = "verification-run"
_support.attach(app)

PASSED, FAILED = [], []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
    else:
        FAILED.append(f"{label} :: {detail}")


def db():
    conn = sqlite3.connect(SCRATCH)
    conn.row_factory = sqlite3.Row
    return conn


def sign_in(client, username, password):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=False)


def text_of(response):
    return response.get_data(as_text=True)


NEW_PW = "Ang-Bagong-Klinika-2026"
ADMIN2_PW = "Malamig-na-Umaga-2026"


# ---------------------------------------------------------------------------
# 0. Baseline
# ---------------------------------------------------------------------------
# STALE-FIX (2026-09-25): this asserted `BASE_USERS == 3`. The database has
# since gained real accounts (a second staff account, then doctor with the Doctor role), so a
# literal count tests the day the suite was written. What the suite relies on is
# that the three seeded accounts it signs in as exist with their roles; every
# later count is taken relative to the baseline recorded here.
conn = db()
BASE_USERS = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
BASE_AUDIT = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
BASE_UM_AUDIT = conn.execute(
    "SELECT COUNT(*) FROM audit_logs WHERE module = 'User Management'").fetchone()[0]
BASE_DEACT_AUDIT = conn.execute(
    "SELECT COUNT(*) FROM audit_logs WHERE action='Deactivated user account'").fetchone()[0]
SEEDED = dict(conn.execute(
    "SELECT username, role FROM users WHERE username IN ('admin','staff','official')"))
ADMIN_NAME = conn.execute("SELECT full_name FROM users WHERE id = 1").fetchone()[0]
conn.close()
check("baseline: the three seeded accounts exist with their roles",
      SEEDED == {"admin": "Admin", "staff": "Health Center Staff",
                 "official": "Barangay Official"}, SEEDED)
# The live app.db, read only (mode=ro), or None when there is none.
REAL_BEFORE = _support.live_db_counts() or (None, None)
REAL_USERS_BEFORE, REAL_UM_AUDIT_BEFORE = REAL_BEFORE


# ---------------------------------------------------------------------------
# 1. Admin signs in, opens User Management
# ---------------------------------------------------------------------------
with app.test_client() as admin:
    r = sign_in(admin, "admin", _support.PASSWORDS["admin"])
    check("admin sign-in redirects to the admin dashboard",
          r.status_code == 302 and "/admin/dashboard" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

    r = admin.get("/admin/user_management")
    body = text_of(r)
    check("User Management renders", r.status_code == 200, r.status_code)
    check("Add User button is no longer disabled",
          'data-bs-target="#addUserModal"' in body, "modal trigger missing")
    check("the retired 'write' reason is gone from the page",
          "Creating, editing and deactivating accounts is not built" not in body)
    check("the retired scope note is gone from the page",
          "Accounts are set up once, not created here" not in body)
    check("the password rule is stated on the form",
          "at least 12 characters" in body and "commonly-guessed password" in body)
    check("the last-Administrator rule is stated on the screen",
          "cannot be deactivated while it is the only one" in body
          or "last Administrator account that can still sign in" in body)

    # -----------------------------------------------------------------------
    # 2. Validation: every rule, each on its own submit
    # -----------------------------------------------------------------------
    def add(**over):
        data = {
            "full_name": "Marivic Dela Cruz",
            "username": "mdelacruz",
            "role": "Health Center Staff",
            "password": NEW_PW,
            "confirm_password": NEW_PW,
        }
        data.update(over)
        return admin.post("/admin/user_management/add", data=data)

    cases = [
        ("blank name", {"full_name": ""}, "Enter the person&#39;s full name."),
        ("blank username", {"username": ""}, "Enter a username for this account."),
        ("blank role", {"role": ""}, "Choose the role this account holds."),
        ("blank password", {"password": "", "confirm_password": ""},
         "Set a password for this account."),
        ("role not in the schema's CHECK list", {"role": "Nurse"},
         "Choose a role from the list."),
        ("username with a space", {"username": "m delacruz"},
         "may use letters, numbers, a dot"),
        ("username starting with a digit", {"username": "1delacruz"},
         "must start with a letter"),
        ("username too short", {"username": "md"},
         "at least 3 characters"),
        ("password too short", {"password": "Short1!", "confirm_password": "Short1!"},
         "at least 12 characters; this one is 7"),
        ("password with too few character kinds",
         {"password": "allsmallletters", "confirm_password": "allsmallletters"},
         # STALE-FIX: was "at least 3 of these four"; 65e0d7c now builds the
         # sentence from PASSWORD_CHARACTER_KINDS and says "3 of these 4".
         "Use at least 3 of these 4:"),
        ("password containing the username",
         {"password": "mdelacruz-Klinika-2026", "confirm_password": "mdelacruz-Klinika-2026"},
         "must not contain the username"),
        ("password containing the person's name",
         {"password": "Marivic-Klinika-2026", "confirm_password": "Marivic-Klinika-2026"},
         "part of the person&#39;s own name"),
        ("common password with digits stuck on",
         {"password": "Password2026!!", "confirm_password": "Password2026!!"},
         "most commonly guessed passwords"),
        ("confirmation does not match",
         {"confirm_password": "Ang-Bagong-Klinika-2027"},
         "do not match"),
        ("duplicate username, exact",
         {"username": "staff"}, "is already taken by another account"),
        ("duplicate username, different capitals",
         {"username": "STAFF"}, "is already taken by another account"),
    ]
    for label, over, expected in cases:
        r = add(**over)
        page = text_of(r)
        check(f"rejected: {label}", r.status_code == 200 and expected in page,
              f"status {r.status_code}; expected text absent")

    conn = db()
    check("no account was created by any rejected submit",
          conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == BASE_USERS)
    # STALE-FIX: was `== 0`, which assumed no User Management entry had ever been
    # written. The database now holds real ones, so count only new entries.
    check("no audit row was written by any rejected submit",
          conn.execute(
              "SELECT COUNT(*) FROM audit_logs WHERE module = 'User Management'"
          ).fetchone()[0] == BASE_UM_AUDIT)
    conn.close()

    r = add(username="STAFF")
    page = text_of(r)
    check("a rejected submit keeps the name, username and role",
          'value="Marivic Dela Cruz"' in page and 'value="STAFF"' in page
          and '<option value="Health Center Staff" selected>' in page)
    check("a rejected submit does NOT write either password back into the page",
          NEW_PW not in page, "the submitted password was rendered into the HTML")
    check("a rejected submit reopens the dialog",
          "new bootstrap.Modal(dialog).show()" in page)

    # -----------------------------------------------------------------------
    # 3. A real account is created
    # -----------------------------------------------------------------------
    r = add()
    check("a valid submit redirects back to User Management",
          r.status_code == 302 and "/admin/user_management" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

    conn = db()
    row = conn.execute("SELECT * FROM users WHERE username = 'mdelacruz'").fetchone()
    conn.close()
    check("the account exists in the database", row is not None)
    check("its full name is stored", row and row["full_name"] == "Marivic Dela Cruz")
    check("its role is the schema's own spelling",
          row and row["role"] == "Health Center Staff", row and row["role"])
    check("it is active", row and row["is_active"] == 1)
    check("email and phone were left NULL",
          row and row["email"] is None and row["phone"] is None)
    check("the password is NOT stored in plaintext anywhere in the row",
          row and NEW_PW not in " ".join(str(v) for v in tuple(row)))
    check("the stored hash verifies the password",
          row and check_password_hash(row["password_hash"], NEW_PW))
    check("the hash uses the same scheme as the seeded accounts",
          row and row["password_hash"].split(":")[0] ==
          db().execute("SELECT password_hash FROM users WHERE username='admin'"
                       ).fetchone()[0].split(":")[0],
          row and row["password_hash"][:12])

    NEW_ID = row["id"]

    conn = db()
    entry = conn.execute(
        "SELECT * FROM audit_logs WHERE module='User Management' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    check("an audit entry was written for the creation", entry is not None)
    check("its action is the account-created phrase",
          entry and entry["action"] == "Created user account", entry and entry["action"])
    check("it is attributed to the acting administrator",
          entry and entry["user_id"] == 1, entry and entry["user_id"])
    check("its details name the new account, its holder and its role",
          entry and '"mdelacruz"' in entry["details"]
          and "Marivic Dela Cruz" in entry["details"]
          and "Health Center Staff" in entry["details"])
    # STALE-FIX: was the literal "Dr. Joshua Reyes"; f7e2607 corrected the
    # Administrator's persona. The property is that the acting account's own
    # name is recorded, so read that name from the database.
    check("its details name the administrator who created it",
          entry and ADMIN_NAME in entry["details"], ADMIN_NAME)
    check("its details say the password was stored hashed",
          entry and "salted hash" in entry["details"])
    check("THE PASSWORD IS NOWHERE IN THE AUDIT ENTRY",
          entry and NEW_PW not in entry["details"],
          "the plaintext password reached the audit trail")

    conn = db()
    check("the password appears nowhere in audit_logs at all",
          conn.execute("SELECT COUNT(*) FROM audit_logs WHERE details LIKE ?",
                       (f"%{NEW_PW}%",)).fetchone()[0] == 0)
    conn.close()

    r = admin.get("/admin/user_management")
    body = text_of(r)
    check("the new account appears on the roster",
          "Marivic Dela Cruz" in body and "mdelacruz" in body)
    # STALE-FIX: was the literal ">4</div>" (three seeded accounts plus one).
    check("the roster now counts one more account than the baseline",
          f">{BASE_USERS + 1}</div>" in body and "Total Accounts" in body, BASE_USERS + 1)


# ---------------------------------------------------------------------------
# 4. The new account signs in and has exactly its role's access
# ---------------------------------------------------------------------------
# SETUP (Task 2): a new account must set its own password first. That rule is
# tested in verify_security_basics.py; here it is cleared so this section keeps
# testing the account's access.
_support.clear_password_change("mdelacruz")
with app.test_client() as staffer:
    r = sign_in(staffer, "mdelacruz", NEW_PW)
    check("the new account signs in",
          r.status_code == 302 and "/staff/dashboard" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

    r = staffer.get("/staff/patient_records")
    check("the new account reaches a Health Staff screen", r.status_code == 200, r.status_code)

    r = staffer.get("/admin/user_management")
    check("the new account is refused User Management",
          r.status_code == 302 and "/dashboard" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

    # A POST to the account-creation endpoint, from a role that is not Admin.
    before = db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    r = staffer.post("/admin/user_management/add", data={
        "full_name": "Forged Admin", "username": "forged", "role": "Admin",
        "password": ADMIN2_PW, "confirm_password": ADMIN2_PW,
    })
    after = db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    check("Health Staff cannot POST to the account-creation endpoint",
          r.status_code == 302 and after == before, f"{r.status_code}, {before}->{after}")

    r = staffer.post("/admin/user_management/status",
                     data={"user_id": "1", "action": "deactivate"})
    still_active = db().execute(
        "SELECT is_active FROM users WHERE id = 1").fetchone()[0]
    check("Health Staff cannot POST to the account-status endpoint",
          r.status_code == 302 and still_active == 1, f"{r.status_code}, active={still_active}")

    conn = db()
    logins = conn.execute(
        "SELECT * FROM audit_logs WHERE action='Signed in' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    check("the new account's sign-in was audited",
          logins and logins["user_id"] == NEW_ID and "mdelacruz" in logins["details"])


# ---------------------------------------------------------------------------
# 5. The last-Administrator guard, attempted for real
# ---------------------------------------------------------------------------
with app.test_client() as admin:
    sign_in(admin, "admin", _support.PASSWORDS["admin"])

    conn = db()
    admins = conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_active=1 AND role='Admin'").fetchone()[0]
    conn.close()
    check("there is exactly one active Administrator before the attempt", admins == 1, admins)

    r = admin.post("/admin/user_management/status",
                   data={"user_id": "1", "action": "deactivate"},
                   follow_redirects=True)
    page = text_of(r)
    check("THE ATTEMPT TO DEACTIVATE THE LAST ADMINISTRATOR IS REFUSED",
          "cannot be deactivated" in page and "last Administrator account" in page,
          page[:200])
    check("the refusal explains what would break",
          "leave nobody able to create an account" in page)
    check("the refusal says how to get past it",
          "Create or reactivate another Administrator first" in page)

    conn = db()
    check("the Administrator is still active after the refusal",
          conn.execute("SELECT is_active FROM users WHERE id=1").fetchone()[0] == 1)
    # STALE-FIX: was `== 0`; the database now holds a real earlier deactivation.
    check("the refusal wrote no deactivation audit entry",
          conn.execute(
              "SELECT COUNT(*) FROM audit_logs WHERE action='Deactivated user account'"
          ).fetchone()[0] == BASE_DEACT_AUDIT)
    conn.close()

    r = admin.get("/admin/user_management")
    check("the Administrator's Deactivate button is disabled on the screen",
          "last Administrator account that can still sign in" in text_of(r))

    # -----------------------------------------------------------------------
    # 6. Deactivating a NON-administrator succeeds
    # -----------------------------------------------------------------------
    r = admin.post("/admin/user_management/status",
                   data={"user_id": str(NEW_ID), "action": "deactivate"},
                   follow_redirects=True)
    page = text_of(r)
    check("a non-Administrator account is deactivated",
          "account is deactivated" in page, page[:200])
    check("the message says nothing was deleted", "Nothing was deleted" in page)

    conn = db()
    check("the flag is set in the database",
          conn.execute("SELECT is_active FROM users WHERE id=?",
                       (NEW_ID,)).fetchone()[0] == 0)
    entry = conn.execute(
        "SELECT * FROM audit_logs WHERE action='Deactivated user account' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    check("the deactivation was audited", entry is not None)
    check("its module is User Management", entry and entry["module"] == "User Management")
    check("it is attributed to the acting administrator", entry and entry["user_id"] == 1)
    check("its details name the account and the administrator",
          entry and '"mdelacruz"' in entry["details"]
          and ADMIN_NAME in entry["details"])  # STALE-FIX: persona, see above
    check("its details say the stored password was not touched",
          entry and "restores the same credential" in entry["details"])
    check("its details report how many Administrators remain",
          entry and "Administrator account" in entry["details"]
          and "can still sign in" in entry["details"])

    r = admin.post("/admin/user_management/status",
                   data={"user_id": str(NEW_ID), "action": "deactivate"},
                   follow_redirects=True)
    check("deactivating an already-deactivated account changes nothing",
          "already deactivated" in text_of(r))

    # Forged / malformed posts
    for label, data, expected in [
        ("an unknown action", {"user_id": str(NEW_ID), "action": "delete"},
         "Choose whether to deactivate or reactivate"),
        ("a non-numeric id", {"user_id": "abc", "action": "deactivate"},
         "Select an account to change"),
        ("an id that does not exist", {"user_id": "9999", "action": "deactivate"},
         "could not be found"),
    ]:
        r = admin.post("/admin/user_management/status", data=data, follow_redirects=True)
        check(f"refused cleanly: {label}", expected in text_of(r))


# ---------------------------------------------------------------------------
# 7. The deactivated account is refused at the login form
# ---------------------------------------------------------------------------
with app.test_client() as revoked:
    r = sign_in(revoked, "mdelacruz", NEW_PW)
    check("the deactivated account cannot sign in even with the right password",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

conn = db()
blocked = conn.execute(
    "SELECT * FROM audit_logs WHERE action='Blocked sign-in to deactivated account' "
    "ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
check("the blocked sign-in was audited against the new account",
      blocked and blocked["user_id"] == NEW_ID)
check("the entry records that the password presented was correct",
      blocked and "this credential still works" in blocked["details"])
check("the blocked entry does not carry the password",
      blocked and NEW_PW not in blocked["details"])


# ---------------------------------------------------------------------------
# 8. Reactivation restores the same credential
# ---------------------------------------------------------------------------
with app.test_client() as admin:
    sign_in(admin, "admin", _support.PASSWORDS["admin"])
    r = admin.get("/admin/user_management")
    check("the deactivated account offers Reactivate, not Deactivate",
          "Reactivate Account" in text_of(r))

    r = admin.post("/admin/user_management/status",
                   data={"user_id": str(NEW_ID), "action": "reactivate"},
                   follow_redirects=True)
    page = text_of(r)
    check("the account is reactivated", "account is active again" in page, page[:200])
    check("the message says the old password still works",
          "same password they had before" in page)

    conn = db()
    check("the flag is cleared in the database",
          conn.execute("SELECT is_active FROM users WHERE id=?",
                       (NEW_ID,)).fetchone()[0] == 1)
    entry = conn.execute(
        "SELECT * FROM audit_logs WHERE action='Reactivated user account' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    check("the reactivation was audited", entry is not None)
    check("it is attributed to the acting administrator", entry and entry["user_id"] == 1)
    check("its details say no new password was set",
        entry and "no new password was set" in entry["details"])

    r = admin.post("/admin/user_management/status",
                   data={"user_id": str(NEW_ID), "action": "reactivate"},
                   follow_redirects=True)
    check("reactivating an already-active account changes nothing",
          "already active" in text_of(r))

conn = db()
hash_after = conn.execute("SELECT password_hash FROM users WHERE id=?",
                          (NEW_ID,)).fetchone()[0]
conn.close()
check("the stored hash survived deactivation and reactivation untouched",
      check_password_hash(hash_after, NEW_PW))

with app.test_client() as back:
    r = sign_in(back, "mdelacruz", NEW_PW)
    check("the reactivated account signs in with its original password",
          r.status_code == 302 and "/staff/dashboard" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")


# ---------------------------------------------------------------------------
# 9. With a second Administrator, the first CAN be deactivated
# ---------------------------------------------------------------------------
with app.test_client() as admin:
    sign_in(admin, "admin", _support.PASSWORDS["admin"])
    r = admin.post("/admin/user_management/add", data={
        "full_name": "Rosalinda Bautista", "username": "rbautista", "role": "Admin",
        "password": ADMIN2_PW, "confirm_password": ADMIN2_PW,
    })
    check("a second Administrator can be created", r.status_code == 302, r.status_code)

    conn = db()
    admin2 = conn.execute("SELECT * FROM users WHERE username='rbautista'").fetchone()
    conn.close()
    check("the second Administrator is stored with the Admin role",
          admin2 and admin2["role"] == "Admin")
    # SETUP (Task 2): see section 4. Cleared so rbautista can act as an
    # Administrator in section 9 below.
    _support.clear_password_change("rbautista")

    r = admin.get("/admin/user_management")
    check("with two Administrators, neither shows the last-Administrator notice",
          "last Administrator account that can still sign in" not in text_of(r))

    # Deactivate the FIRST administrator -- allowed now, and it is the acting
    # account's own, so the session ends on the next request.
    #
    # DEFECT-FIX (2026-09-26): these two checks failed from the day they were
    # written (3494e7e). The redirect went to User Management, the guard found the
    # account deactivated on that GET and cleared the session -- and the flash with
    # it -- and the page said "Invalid security credentials." The route now signs
    # the holder out in the same request and sends them to the login form with a
    # notice written for this case. The checks keep their labels and now assert
    # that notice, word for word, on the login form, and that the generic refusal
    # is NOT what they are shown. Three checks were added beside them for the
    # properties the fix must keep: no ?error= on the redirect (anyone can type
    # that), no identity left in the session, and the notice shown once only.
    SELF_NOTICE = (
        "You deactivated your own account, so you have been signed out. You cannot "
        "sign back in until another Administrator reactivates it. Nothing was "
        "deleted — reactivating it restores the same password."
    )
    r = admin.post("/admin/user_management/status",
                   data={"user_id": "1", "action": "deactivate"},
                   follow_redirects=False)
    loc = r.headers.get("Location", "")
    check("self-deactivation redirects straight to the login form, with no ?error=",
          r.status_code == 302 and loc.endswith("/login") and "?" not in loc,
          f"{r.status_code} {loc}")
    with admin.session_transaction() as s:
        check("self-deactivation leaves no identity in the session",
              "user_id" not in s and "role" not in s, dict(s))
    r = admin.get(loc)
    page = text_of(r)
    check("with a second Administrator present, the first can be deactivated",
          r.status_code == 200 and "IDS-BPHCSN | Sign In" in page
          and "Invalid security credentials." not in page, page[:200])
    check("deactivating your own account says your session will end",
          SELF_NOTICE in page, page[page.find("login-alert"):][:400])
    r = admin.get("/login")
    check("the notice is shown once, not on the next visit to the login form",
          SELF_NOTICE not in text_of(r)
          and "Invalid security credentials." not in text_of(r))

    conn = db()
    check("the first Administrator is now inactive",
          conn.execute("SELECT is_active FROM users WHERE id=1").fetchone()[0] == 0)
    entry = conn.execute(
        "SELECT details FROM audit_logs WHERE action='Deactivated user account' "
        "ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    check("the entry notes the administrator deactivated their own account",
          "deactivated their own account" in entry)

    # The session is revoked on the next guarded request. (Since the DEFECT-FIX
    # above it was already cleared by the deactivating request; this still proves
    # the browser cannot reach an Administrator screen afterwards.)
    r = admin.get("/admin/user_management")
    check("the deactivated administrator's live session is revoked on its next request",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")

conn = db()
check("the session revocation was audited",
      conn.execute(
          "SELECT COUNT(*) FROM audit_logs "
          "WHERE action='Ended session on deactivated account' AND user_id=1"
      ).fetchone()[0] >= 1)
conn.close()

# And now rbautista is the last Administrator, so the guard moves to them.
with app.test_client() as admin2c:
    r = sign_in(admin2c, "rbautista", ADMIN2_PW)
    check("the second Administrator signs in",
          r.status_code == 302 and "/admin/dashboard" in r.headers.get("Location", ""),
          f"{r.status_code} {r.headers.get('Location')}")
    r = admin2c.post("/admin/user_management/status",
                     data={"user_id": str(admin2["id"]), "action": "deactivate"},
                     follow_redirects=True)
    check("THE GUARD FOLLOWS THE LAST ADMINISTRATOR, WHICHEVER ACCOUNT THAT IS",
          "cannot be deactivated" in text_of(r) and "last Administrator" in text_of(r))
    conn = db()
    check("the second Administrator is still active after that refusal",
          conn.execute("SELECT is_active FROM users WHERE username='rbautista'"
                       ).fetchone()[0] == 1)
    conn.close()

    # Restore the first administrator so the sweep below runs as before.
    admin2c.post("/admin/user_management/status",
                 data={"user_id": "1", "action": "reactivate"})


# ---------------------------------------------------------------------------
# 10. Model-level guard, called directly (a caller that is not a route)
# ---------------------------------------------------------------------------
from models.users import deactivate_user, LAST_ADMINISTRATOR, count_active_admins  # noqa

with app.app_context():
    # Take the roster down to one active Administrator, then call the model
    # function itself -- no route, no session, no template.
    deactivate_user(1)
    check("model: exactly one active Administrator remains",
          count_active_admins() == 1, count_active_admins())
    changed, code = deactivate_user(admin2["id"])
    check("MODEL-LEVEL: deactivate_user() itself refuses the last Administrator",
          changed is False and code == LAST_ADMINISTRATOR, f"{changed} {code}")
    conn = db()
    check("model: the account is still active after that refusal",
          conn.execute("SELECT is_active FROM users WHERE id=?",
                       (admin2["id"],)).fetchone()[0] == 1)
    conn.close()
    from models.users import reactivate_user
    reactivate_user(1)


# ---------------------------------------------------------------------------
# 11. Existing authentication behaviour is untouched
# ---------------------------------------------------------------------------
with app.test_client() as c:
    r = sign_in(c, "admin", "wrong-password")
    check("a wrong password is still refused",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""))
    r = sign_in(c, "nobody-at-all", "whatever")
    check("an unknown username is still refused",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""))

conn = db()
check("the refusal on a real account was audited",
      conn.execute(
          "SELECT COUNT(*) FROM audit_logs WHERE action='Refused sign-in attempt'"
      ).fetchone()[0] > 0)
check("the unknown username wrote no audit row it could not attribute",
      conn.execute(
          "SELECT COUNT(*) FROM audit_logs WHERE details LIKE '%nobody-at-all%'"
      ).fetchone()[0] == 0)
conn.close()

with app.test_client() as c:
    sign_in(c, "official", _support.PASSWORDS["official"])
    r = c.get("/official/dashboard")
    check("the Barangay Official still reaches its own dashboard", r.status_code == 200)
    r = c.get("/admin/user_management")
    check("the Barangay Official is still refused User Management",
          r.status_code == 302)
    r = c.get("/staff/patient_records")
    check("the Barangay Official is still refused Health Staff screens",
          r.status_code == 302)


# ---------------------------------------------------------------------------
# 12. Full GET sweep across all three roles — no 5xx anywhere
# ---------------------------------------------------------------------------
ROLE_LOGINS = [
    ("Admin", "admin", _support.PASSWORDS["admin"]),
    ("Health Center Staff", "staff", _support.PASSWORDS["staff"]),
    ("Barangay Official", "official", _support.PASSWORDS["official"]),
]

sample_ids = {}
conn = db()
sample_ids["patient_id"] = conn.execute("SELECT id FROM patients LIMIT 1").fetchone()[0]
sample_ids["item_id"] = conn.execute("SELECT id FROM inventory_items LIMIT 1").fetchone()[0]
row = conn.execute("SELECT id FROM consultations LIMIT 1").fetchone()
sample_ids["consultation_id"] = row[0] if row else 1
sample_ids["user_id"] = 1
sample_ids["appointment_id"] = 1
conn.close()

rules = [r for r in app.url_map.iter_rules()
         if r.endpoint != "static" and "GET" in r.methods]
swept = 0
for role, username, password in ROLE_LOGINS:
    with app.test_client() as c:
        sign_in(c, username, password)
        for rule in rules:
            try:
                url = rule.build(
                    {a: sample_ids.get(a, 1) for a in rule.arguments}, append_unknown=False
                )[1]
            except Exception:
                continue
            resp = c.get(url)
            swept += 1
            if resp.status_code >= 500:
                FAILED.append(f"5xx sweep: {role} GET {url} -> {resp.status_code}")
PASSED.append(f"GET sweep: {swept} role x route renders, no 5xx")


# ---------------------------------------------------------------------------
# 13. The audit screen renders the new module and its entries
# ---------------------------------------------------------------------------
with app.test_client() as c:
    sign_in(c, "admin", _support.PASSWORDS["admin"])
    r = c.get("/admin/audit_logs?module=User Management")
    page = text_of(r)
    check("Audit Logs offers the User Management module filter",
          r.status_code == 200 and "User Management" in page, r.status_code)
    check("the account entries appear on the Audit Logs screen",
          "Created user account" in page and "Deactivated user account" in page
          and "Reactivated user account" in page)
    check("no plaintext password appears anywhere on the Audit Logs screen",
          NEW_PW not in page and ADMIN2_PW not in page)

    r = c.get("/admin/user_management/export.xlsx")
    check("the roster Excel export still builds", r.status_code == 200, r.status_code)
    r = c.get("/admin/user_management/export.pdf")
    check("the roster PDF export still builds", r.status_code == 200, r.status_code)
    r = c.get("/admin/audit_logs/export.xlsx")
    check("the audit Excel export still builds", r.status_code == 200, r.status_code)


# ---------------------------------------------------------------------------
# 14. The real database was not touched
# ---------------------------------------------------------------------------
# STALE-FIX: these compared against the literals 3 and 0. The property is "the
# run did not write to the real database", so compare it with itself before the
# run.
REAL_AFTER = _support.live_db_counts() or (None, None)
check("THE REAL DATABASE HOLDS THE SAME ACCOUNTS AS BEFORE THE RUN",
      REAL_AFTER[0] == REAL_USERS_BEFORE)
check("the real database gained no account-management audit rows",
      REAL_AFTER[1] == REAL_UM_AUDIT_BEFORE)


# ---------------------------------------------------------------------------
print()
for f in FAILED:
    print("FAIL:", f)
print()
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
print("scratch database:", SCRATCH)
sys.exit(1 if FAILED else 0)

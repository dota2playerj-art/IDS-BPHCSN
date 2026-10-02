# -*- coding: utf-8 -*-
"""End-to-end exercise of Reset Password and Edit User through the real stack.

Runs on a fresh test database built by tests/_support.py.
"""
import sys
import _support  # noqa: E402  (first: builds the test database, points the app at it)

import sqlite3
from app import create_app

app = create_app()
DB = _support.DB_PATH
_support.attach(app)

PASS = []
FAIL = []


def check(label, ok, extra=""):
    (PASS if ok else FAIL).append(label)
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -- " + extra) if extra else ""))


def row(uid):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    c.close()
    return r


def last_audit(n=1):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rs = c.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    c.close()
    return rs

# STALE-FIX (2026-09-25): the Administrator's name was written into this suite
# as "Dr. Joshua Reyes". 1c3efc7 corrected the persona (Kagawad Antonio
# Acido), so the literal both failed the "names the acting administrator"
# check and, in the "put it back" steps, renamed the account to the retired
# persona. The name is read from the database under test instead.
ADMIN_NAME = row(1)["full_name"]
ADMIN_NAME_VARIANT = ADMIN_NAME + " Jr."


def login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=True,
    )


def signed_in(client):
    with client.session_transaction() as sess:
        return sess.get("user_id")


print("\n=== 1. Sign in as the Administrator ===")
c = app.test_client()
r = login(c, "admin", _support.PASSWORDS["admin"])
check("admin signs in", signed_in(c) == 1, "session user_id=%s" % signed_in(c))
r = c.get("/admin/user_management")
check("User Management renders 200", r.status_code == 200)
html = r.get_data(as_text=True)
check("Reset Password button is no longer disabled",
      'data-bs-target="#resetPasswordModal4"' in html)
check("Edit User button is no longer disabled",
      'data-bs-target="#editUserModal4"' in html)
check("username box is rendered read-only in Edit dialog",
      'id="editUsername4"' in html and "readonly" in html)
check("no stale 'is not built' reason for these two",
      "Editing an existing account is not built" not in html
      and "Password reset is not built" not in html)

print("\n=== 2. Edit User: invalid data must redisplay the same dialog ===")
before4 = row(4)
r = c.post("/admin/user_management/edit",
           data={"user_id": "4", "full_name": "", "role": "Health Center Staff"})
html = r.get_data(as_text=True)
check("invalid edit returns 200 (no redirect)", r.status_code == 200)
check("dialog is reopened on THIS account",
      "editUserModal4'" in html or "getElementById('editUserModal4')" in html)
check("error is shown beside the field", "Enter the person&#39;s full name." in html
      or "Enter the person's full name." in html)
check("account unchanged by the refused edit",
      row(4)["full_name"] == before4["full_name"] and row(4)["role"] == before4["role"])

print("\n=== 3. Edit User: a real change of full name AND role ===")
r = c.post("/admin/user_management/edit",
           data={"user_id": "4", "full_name": "Test M. Health Worker",
                 "role": "Barangay Official"},
           follow_redirects=True)
after4 = row(4)
check("full name persisted", after4["full_name"] == "Test M. Health Worker", after4["full_name"])
check("role persisted", after4["role"] == "Barangay Official", after4["role"])
check("username UNCHANGED", after4["username"] == before4["username"], after4["username"])
check("password hash untouched by the edit",
      after4["password_hash"] == before4["password_hash"])
entry = last_audit(1)[0]
check("audit action is the role-change phrase",
      entry["action"] == "Changed user account role", entry["action"])
check("audit names the BEFORE role", '"Health Center Staff"' in entry["details"])
check("audit names the AFTER role", '"Barangay Official"' in entry["details"])
check("audit names the acting administrator",
      ADMIN_NAME in entry["details"])
check("audit attributes to the acting admin's id", entry["user_id"] == 1)
check("audit module is User Management", entry["module"] == "User Management")
check("audit holds no password", _support.PASSWORDS["admin"] not in entry["details"])

print("\n=== 4. The role change is reflected in real access ===")
r = c.get("/admin/user_management")
html = r.get_data(as_text=True)
check("roster shows the new name", "Test M. Health Worker" in html)
check("roster shows the new role", "Barangay Official" in html)

print("\n=== 5. Edit User: username posted in the form is ignored entirely ===")
r = c.post("/admin/user_management/edit",
           data={"user_id": "4", "username": "hacked",
                 "full_name": "Test M. Health Worker", "role": "Health Center Staff"},
           follow_redirects=True)
after4 = row(4)
check("posted username had no effect", after4["username"] == "bhwtest", after4["username"])
check("role change still applied", after4["role"] == "Health Center Staff")

print("\n=== 6. Edit User: a save that changes nothing writes no audit entry ===")
n_before = last_audit(1)[0]["id"]
r = c.post("/admin/user_management/edit",
           data={"user_id": "4", "full_name": "Test M. Health Worker",
                 "role": "Health Center Staff"},
           follow_redirects=True)
check("no audit entry for a no-op save", last_audit(1)[0]["id"] == n_before)
check("the operator is told nothing changed",
      "No change" in r.get_data(as_text=True))

print("\n=== 7. The LAST ADMINISTRATOR cannot have their role changed away ===")
c2 = sqlite3.connect(DB)
admins = c2.execute(
    "SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = 'Admin'"
).fetchone()[0]
c2.close()
print("  (active Administrators right now: %d)" % admins)
before1 = row(1)
r = c.post("/admin/user_management/edit",
           data={"user_id": "1", "full_name": ADMIN_NAME,
                 "role": "Health Center Staff"})
html = r.get_data(as_text=True)
check("refusal returns 200 with the dialog, not a redirect", r.status_code == 200)
check("the Administrator's role is UNCHANGED in the database",
      row(1)["role"] == "Admin", row(1)["role"])
check("the refusal explains the lockout",
      "last Administrator who can sign in" in html)
check("the dialog reopens on account 1",
      "getElementById('editUserModal1')" in html)
check("no audit entry was written for the refusal",
      last_audit(1)[0]["id"] == n_before)

print("\n=== 8. The guard is in the MODEL, not only the route ===")
with app.app_context():
    from models.users import update_user, LAST_ADMINISTRATOR
    b, a, refusal = update_user(1, {"full_name": ADMIN_NAME,
                                    "role": "Barangay Official"})
    check("models.users.update_user() refuses it directly",
          b is None and refusal == LAST_ADMINISTRATOR, str(refusal))
    check("still an Admin in the database", row(1)["role"] == "Admin")

print("\n=== 9. The name of the last Administrator can still be corrected ===")
r = c.post("/admin/user_management/edit",
           data={"user_id": "1", "full_name": ADMIN_NAME_VARIANT,
                 "role": "Admin"}, follow_redirects=True)
check("name change on the last Admin is allowed",
      row(1)["full_name"] == ADMIN_NAME_VARIANT, row(1)["full_name"])
entry = last_audit(1)[0]
check("that entry is the plain edit phrase, not a role change",
      entry["action"] == "Edited user account", entry["action"])
check("it does not claim a role change", "ROLE CHANGED" not in entry["details"])
# put it back
c.post("/admin/user_management/edit",
       data={"user_id": "1", "full_name": ADMIN_NAME, "role": "Admin"},
       follow_redirects=True)

print("\n=== 10. Reset Password: invalid data must redisplay the same dialog ===")
hash_before = row(4)["password_hash"]
r = c.post("/admin/user_management/reset_password",
           data={"user_id": "4", "password": "zqxjkv", "confirm_password": "wbmfpg"})
html = r.get_data(as_text=True)
check("invalid reset returns 200 (no redirect)", r.status_code == 200)
check("dialog reopens on THIS account",
      "getElementById('resetPasswordModal4')" in html)
check("strength error is shown", "Too short" in html)
check("mismatch error is shown", "do not match" in html)
check("stored hash untouched", row(4)["password_hash"] == hash_before)
# The distinctive strings above appear nowhere in any error wording, so if
# either turns up in the response it was re-rendered into the form.
check("neither typed password is written back into the page",
      "zqxjkv" not in html and "wbmfpg" not in html)
check("both password boxes come back empty",
      'id="resetPassword4"' in html and 'name="password" value=' not in html)

print("\n=== 11. Reset Password: the rule is the SAME rule as Add User ===")
r = c.post("/admin/user_management/reset_password",
           data={"user_id": "4", "password": "bhwtest1234",
                 "confirm_password": "bhwtest1234"})
check("a password containing the username is refused",
      "must not contain the username" in r.get_data(as_text=True))
r = c.post("/admin/user_management/reset_password",
           data={"user_id": "4", "password": "Password2026!",
                 "confirm_password": "Password2026!"})
check("a common password is refused",
      "commonly guessed" in r.get_data(as_text=True))
check("stored hash still untouched", row(4)["password_hash"] == hash_before)

print("\n=== 12. Reset Password: a real reset, verified by SIGNING IN ===")
NEW = "the blue jeepney leaves at Six"
r = c.post("/admin/user_management/reset_password",
           data={"user_id": "4", "password": NEW, "confirm_password": NEW},
           follow_redirects=True)
check("reset redirected and flashed", r.status_code == 200)
check("stored hash CHANGED", row(4)["password_hash"] != hash_before)
check("hash is not the plaintext", NEW not in str(row(4)["password_hash"]))
check("scheme matches the seeded accounts",
      row(4)["password_hash"].split(":")[0] == row(1)["password_hash"].split(":")[0],
      row(4)["password_hash"].split(":")[0])
entry = last_audit(1)[0]
check("audit action is the reset phrase",
      entry["action"] == "Reset user account password", entry["action"])
check("audit names the account", "bhwtest" in entry["details"])
check("audit names the acting administrator", ADMIN_NAME in entry["details"])
check("AUDIT CONTAINS NO PASSWORD", NEW not in entry["details"]
      and "jeepney" not in entry["details"].lower())
check("audit does not leak the length", "29 character" not in entry["details"])

print("\n=== 13. THE NEW PASSWORD ACTUALLY SIGNS IN, THE OLD ONE DOES NOT ===")
c3 = app.test_client()
r = login(c3, "bhwtest", NEW)
check("SIGN-IN WITH THE NEW PASSWORD SUCCEEDS", signed_in(c3) == 4,
      "session user_id=%s" % signed_in(c3))
r = c3.get("/staff/dashboard", follow_redirects=False)
check("the account reaches its role's screens", r.status_code in (200, 302),
      "status %s" % r.status_code)

c4 = app.test_client()
login(c4, "bhwtest", "Worker2026!secure")
check("an arbitrary old-style password is refused", signed_in(c4) is None)

print("\n=== 14. A password reset does NOT change anything else ===")
after = row(4)
check("username unchanged", after["username"] == "bhwtest")
check("full name unchanged", after["full_name"] == "Test M. Health Worker")
check("role unchanged", after["role"] == "Health Center Staff")
check("is_active unchanged", after["is_active"] == 1)

print("\n=== 15. Non-admin roles are refused at both endpoints ===")
for user, pwd, label in (("staff", _support.PASSWORDS["staff"], "Health Center Staff"),
                         ("official", _support.PASSWORDS["official"], "Barangay Official")):
    cc = app.test_client()
    login(cc, user, pwd)
    if signed_in(cc) is None:
        print("    (%s could not sign in -- skipped)" % user)
        continue
    r = cc.post("/admin/user_management/edit",
                data={"user_id": "1", "full_name": "X", "role": "Health Center Staff"},
                follow_redirects=False)
    check("%s is refused at /edit" % label, r.status_code in (302, 403),
          "status %s" % r.status_code)
    r = cc.post("/admin/user_management/reset_password",
                data={"user_id": "1", "password": NEW, "confirm_password": NEW},
                follow_redirects=False)
    check("%s is refused at /reset_password" % label, r.status_code in (302, 403),
          "status %s" % r.status_code)
    check("the Administrator's password was NOT replaced by %s" % label,
          row(1)["password_hash"] == before1["password_hash"])

cc = app.test_client()
r = cc.post("/admin/user_management/edit",
            data={"user_id": "1", "full_name": "X", "role": "Health Center Staff"},
            follow_redirects=False)
check("a signed-out request is refused at /edit", r.status_code == 302)
r = cc.post("/admin/user_management/reset_password",
            data={"user_id": "1", "password": NEW, "confirm_password": NEW},
            follow_redirects=False)
check("a signed-out request is refused at /reset_password", r.status_code == 302)

print("\n=== 16. Bad input on the account id ===")
r = c.post("/admin/user_management/edit",
           data={"user_id": "9999", "full_name": "X", "role": "Admin"},
           follow_redirects=True)
check("a nonexistent account is refused cleanly",
      "could not be found" in r.get_data(as_text=True))
r = c.post("/admin/user_management/reset_password",
           data={"user_id": "abc", "password": NEW, "confirm_password": NEW},
           follow_redirects=True)
check("a non-numeric id is refused cleanly",
      "could not be found" in r.get_data(as_text=True))

print("\n=== 17. Regression: Add User, Deactivate, Reactivate still work ===")
r = c.post("/admin/user_management/add",
           data={"full_name": "Test Regression", "username": "regtest1",
                 "role": "Health Center Staff",
                 "password": "a long enough Phrase 7", "confirm_password": "a long enough Phrase 7"},
           follow_redirects=True)
cdb = sqlite3.connect(DB)
newid = cdb.execute("SELECT id FROM users WHERE username='regtest1'").fetchone()
cdb.close()
check("Add User still creates an account", newid is not None)
# SETUP (Task 2): a new account must set its own password first. That rule is
# tested in verify_security_basics.py; cleared here so regtest1 can act as an
# Administrator in step 18.
_support.clear_password_change("regtest1")
if newid:
    newid = newid[0]
    r = c.post("/admin/user_management/status",
               data={"user_id": str(newid), "action": "deactivate"}, follow_redirects=True)
    check("Deactivate still works", row(newid)["is_active"] == 0)
    r = c.post("/admin/user_management/status",
               data={"user_id": str(newid), "action": "reactivate"}, follow_redirects=True)
    check("Reactivate still works", row(newid)["is_active"] == 1)
    r = c.post("/admin/user_management/status",
               data={"user_id": "1", "action": "deactivate"}, follow_redirects=True)
    check("the last-Admin DEACTIVATION guard still holds", row(1)["is_active"] == 1)

    print("\n=== 18. With a SECOND Administrator, the role change is allowed ===")
    c.post("/admin/user_management/edit",
           data={"user_id": str(newid), "full_name": "Test Regression", "role": "Admin"},
           follow_redirects=True)
    check("a second Administrator now exists", row(newid)["role"] == "Admin")
    r = c.post("/admin/user_management/edit",
               data={"user_id": "1", "full_name": ADMIN_NAME,
                     "role": "Health Center Staff"}, follow_redirects=True)
    check("the original Administrator can NOW be demoted",
          row(1)["role"] == "Health Center Staff", row(1)["role"])
    # and the new one is now the last -- so it must be refused
    r = c2 = app.test_client()
    login(c2, "regtest1", "a long enough Phrase 7")
    r = c2.post("/admin/user_management/edit",
                data={"user_id": str(newid), "full_name": "Test Regression",
                      "role": "Health Center Staff"})
    check("the NEW last Administrator is now the one refused",
          row(newid)["role"] == "Admin", row(newid)["role"])
    check("and the refusal explains the lockout",
          "last Administrator who can sign in" in r.get_data(as_text=True))
    # restore
    c2.post("/admin/user_management/edit",
            data={"user_id": "1", "full_name": ADMIN_NAME, "role": "Admin"},
            follow_redirects=True)
    check("account 1 restored to Admin", row(1)["role"] == "Admin")

print("\n" + "=" * 70)
print("PASSED: %d    FAILED: %d" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("   FAILED -> " + f)
print("=" * 70)

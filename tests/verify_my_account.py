"""My Account verification suite.

Runs on a fresh test database built by tests/_support.py. Every check is asserted
against the rendered response, the database, or both -- never against the code.
"""
import sqlite3
import sys

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from werkzeug.security import check_password_hash

import app as appmodule
from models.audit import (
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_PASSWORD_CHANGED_SELF,
    ACTION_PASSWORD_RESET,
    MODULE_AUTH,
    MODULE_USERS,
)

DB = _support.DB_PATH

flask_app = appmodule.create_app()
flask_app.config["DATABASE"] = DB
_support.attach(flask_app)

PASSED = []
FAILED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
    else:
        FAILED.append(f"{label}  {detail}")
        print(f"FAIL  {label}  {detail}")


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def user_row(username):
    conn = db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    finally:
        conn.close()


def audit_rows(action=None, user_id=None):
    conn = db()
    try:
        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        if action:
            sql += " AND action = ?"
            params.append(action)
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        sql += " ORDER BY id"
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def audit_count():
    conn = db()
    try:
        return conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    finally:
        conn.close()


def sign_in(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password}
    )


def change(client, current, new, confirm=None, extra=None):
    data = {
        "current_password": current,
        "new_password": new,
        "confirm_new_password": new if confirm is None else confirm,
    }
    if extra:
        data.update(extra)
    return client.post("/account/password", data=data)


# ---------------------------------------------------------------------------
# The three roles, their seeded credentials, and one screen each proves access
# ---------------------------------------------------------------------------
ROLES = [
    {
        "username": "admin",
        "old": _support.PASSWORDS["admin"],
        "new": "Tubig#Malinis4Lahat",
        "full_name": "Kagawad Antonio Acido",
        "role": "Admin",
        "role_label": "Administrator",
        "home": "/admin/dashboard",
    },
    {
        "username": "staff",
        "old": _support.PASSWORDS["staff"],
        "new": "Bakuna@Umaga7Ph",
        "full_name": "Health Center Staff",
        "role": "Health Center Staff",
        "role_label": "Health Center Staff",
        "home": "/staff/dashboard",
    },
    {
        "username": "official",
        "old": _support.PASSWORDS["official"],
        "new": "Kalusugan%Buhay31",
        "full_name": "Barangay Official",
        "role": "Barangay Official",
        "role_label": "Barangay Official",
        "home": "/official/dashboard",
    },
]

print("=" * 78)
print("PART 1 -- the panel is reachable and read-only, for all three roles")
print("=" * 78)

for spec in ROLES:
    name = spec["username"]
    with flask_app.test_client() as client:
        sign_in(client, name, spec["old"])

        # It is reachable from the profile chip: the menu item is in the header
        # of an ORDINARY screen, not only of My Account itself.
        home = client.get(spec["home"]).get_data(as_text=True)
        check(
            f"[{name}] profile menu on {spec['home']} links to /account",
            'href="/account"' in home and "My Account" in home,
        )

        response = client.get("/account")
        html = response.get_data(as_text=True)
        check(f"[{name}] GET /account is 200", response.status_code == 200,
              f"got {response.status_code}")
        check(f"[{name}] shows own full name", spec["full_name"] in html)
        check(f"[{name}] shows own role", spec["role_label"] in html)
        check(f"[{name}] shows own username", f">{name}<" in html)
        check(f"[{name}] has the three password boxes",
              all(f'name="{field}"' in html for field in
                  ("current_password", "new_password", "confirm_new_password")))
        check(f"[{name}] posts to /account/password",
              'action="/account/password"' in html)

        # Read-only: no editable name/role/username, no photo upload, nothing
        # beyond the two confirmed sections.
        check(f"[{name}] no editable full_name field", 'name="full_name"' not in html)
        check(f"[{name}] no editable role field", 'name="role"' not in html)
        check(f"[{name}] no editable username field", 'name="username"' not in html)
        check(f"[{name}] no file/photo upload", 'type="file"' not in html)
        check(f"[{name}] no account id posted anywhere", 'name="user_id"' not in html)

        # GET on the write endpoint does not exist.
        check(f"[{name}] GET /account/password is 405",
              client.get("/account/password").status_code == 405)

print("=" * 78)
print("PART 2 -- refusals: wrong current password, weak new one, mismatch, blanks")
print("=" * 78)

for spec in ROLES:
    name = spec["username"]
    before_hash = user_row(name)["password_hash"]
    before_audit = audit_count()

    with flask_app.test_client() as client:
        sign_in(client, name, spec["old"])
        after_login_audit = audit_count()

        cases = [
            (
                "wrong current password",
                {"current": "NotMyPassword#9", "new": spec["new"]},
                "current_password",
                "That is not the password this account signs in with",
            ),
            (
                "weak new password (too short)",
                {"current": spec["old"], "new": "abc"},
                "new_password",
                "Too short. A password must be at least 12 characters",
            ),
            (
                "weak new password (one character kind)",
                {"current": spec["old"], "new": "aaaaaaaaaaaaaaaa"},
                "new_password",
                "Use at least 3 of these 4",
            ),
            (
                "new password contains the username",
                {"current": spec["old"], "new": f"Malusog{name.capitalize()}2026!"},
                "new_password",
                "must not contain the username",
            ),
            (
                "common password",
                {"current": spec["old"], "new": "Password2026!"},
                "new_password",
                "most commonly guessed passwords",
            ),
            (
                "confirmation does not match",
                {"current": spec["old"], "new": spec["new"], "confirm": "Ibang#Password9"},
                "confirm_new_password",
                "The two new passwords do not match",
            ),
        ]

        for label, kwargs, field, message in cases:
            response = change(client, **kwargs)
            html = response.get_data(as_text=True)
            check(f"[{name}] {label}: redisplays at 200 (no redirect)",
                  response.status_code == 200, f"got {response.status_code}")
            check(f"[{name}] {label}: error beside the right field",
                  message in html, "message not in page")
            check(f"[{name}] {label}: field marked is-invalid",
                  f'name="{field}"' in html
                  and 'is-invalid' in html.split(f'name="{field}"')[0].rsplit("<input", 1)[-1],
                  "is-invalid not on that input")
            check(f"[{name}] {label}: banner says nothing was changed",
                  "Your password was not changed" in html)
            check(f"[{name}] {label}: the page is My Account itself",
                  "<title>IDS-BPHCSN | My Account</title>" in html)
            # No password is written back into the page.
            for value in set(kwargs.values()) | {kwargs.get("confirm", "")}:
                if value:
                    check(f"[{name}] {label}: submitted value absent from HTML",
                          value not in html, f"{value!r} leaked into the page")

        # All three boxes blank.
        response = change(client, "", "", "")
        html = response.get_data(as_text=True)
        check(f"[{name}] blank form: three field errors at once",
              all(text in html for text in (
                  "Type the password you sign in with now.",
                  "Set the new password you want to use.",
                  "Type the new password a second time to confirm it.",
              )))
        check(f"[{name}] blank form: banner counts 3 fields",
              "Correct the 3 highlighted fields" in html)

        # Two problems in one submit are both reported.
        response = change(client, "AlsoWrong#7", "abc")
        html = response.get_data(as_text=True)
        check(f"[{name}] wrong current AND weak new: both reported",
              "That is not the password this account signs in with" in html
              and "Too short." in html)

    check(f"[{name}] after every refusal the stored hash is untouched",
          user_row(name)["password_hash"] == before_hash)
    check(f"[{name}] after every refusal the old password still verifies",
          check_password_hash(user_row(name)["password_hash"], spec["old"]))
    # STALE-FIX (2026-09-25): this asserted that NO refusal writes an audit row.
    # 012b65c deliberately made one refusal auditable: a wrong CURRENT password
    # on My Account now writes one "Refused own-password change attempt" row,
    # built from the stored account row and never from the typed text. Two of
    # the submits above carry a wrong current password ("wrong current
    # password" and "wrong current AND weak new"), so exactly two such rows are
    # expected. Every other refusal must still write nothing, and neither row may
    # contain anything that was typed.
    conn = db()
    appended = audit_count() - after_login_audit
    new_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (appended,))] if appended else []
    uid = conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()[0]
    conn.close()
    typed = {"NotMyPassword#9", "AlsoWrong#7", spec["new"], "abc", "aaaaaaaaaaaaaaaa",
             "Password2026!", "Ibang#Password9", spec["old"],
             f"Malusog{name.capitalize()}2026!"}
    check(f"[{name}] refusals write exactly the two wrong-current-password rows, nothing else",
          len(new_rows) == 2
          and all(r["action"] == "Refused own-password change attempt" for r in new_rows),
          [(r["action"]) for r in new_rows])
    check(f"[{name}] both are attributed to this account, under Authentication",
          all(r["user_id"] == uid and r["module"] == "Authentication" for r in new_rows),
          [(r["user_id"], r["module"]) for r in new_rows])
    check(f"[{name}] no submitted value appears in either row",
          not any(v in (r["details"] or "") for r in new_rows for v in typed))
    check(f"[{name}] the only row written was the sign-in",
          after_login_audit == before_audit + 1)

print("=" * 78)
print("PART 3 -- a real change, and the login that proves it")
print("=" * 78)

for spec in ROLES:
    name = spec["username"]
    before = user_row(name)
    before_reset_rows = len(audit_rows(ACTION_PASSWORD_RESET))

    with flask_app.test_client() as client:
        sign_in(client, name, spec["old"])
        response = change(client, spec["old"], spec["new"])
        check(f"[{name}] a valid change redirects", response.status_code == 302,
              f"got {response.status_code}")
        check(f"[{name}] it redirects back to My Account",
              response.headers.get("Location", "").endswith("/account"))

        landed = client.get("/account").get_data(as_text=True)
        check(f"[{name}] the flash reports the change",
              "Your password has been changed." in landed)
        check(f"[{name}] the flash says the session stays open",
              "still signed in on this device" in landed)

        # The session survives the change: the same client reaches its own
        # screens without signing in again.
        check(f"[{name}] still signed in after changing the password",
              client.get(spec["home"]).status_code == 200)

    after = user_row(name)
    check(f"[{name}] the stored hash changed", after["password_hash"] != before["password_hash"])
    check(f"[{name}] the new password verifies against the stored hash",
          check_password_hash(after["password_hash"], spec["new"]))
    check(f"[{name}] the OLD password no longer verifies",
          not check_password_hash(after["password_hash"], spec["old"]))
    check(f"[{name}] neither password is stored in plaintext anywhere on the row",
          not any(
              value in (spec["old"], spec["new"])
              for value in dict(after).values()
              if isinstance(value, str)
          ))
    for column in ("username", "full_name", "role", "is_active", "created_at"):
        check(f"[{name}] {column} unchanged by the password change",
              after[column] == before[column])

    # The login form is the real proof.
    with flask_app.test_client() as client:
        response = sign_in(client, name, spec["new"])
        check(f"[{name}] signs in with the NEW password",
              response.status_code == 302
              and response.headers.get("Location", "") == spec["home"],
              response.headers.get("Location", ""))
        check(f"[{name}] and reaches its own dashboard",
              client.get(spec["home"]).status_code == 200)

    failed_before = len(audit_rows(ACTION_LOGIN_FAILED, before["id"]))
    with flask_app.test_client() as client:
        response = sign_in(client, name, spec["old"])
        check(f"[{name}] the OLD password is refused at the login form",
              response.status_code == 302
              and "/login" in response.headers.get("Location", ""))
        check(f"[{name}] and no session was started",
              client.get(spec["home"]).status_code == 302)
    check(f"[{name}] the refused old password is audited as a refused sign-in",
          len(audit_rows(ACTION_LOGIN_FAILED, before["id"])) == failed_before + 1)

    # The audit entry.
    entries = audit_rows(ACTION_PASSWORD_CHANGED_SELF, before["id"])
    check(f"[{name}] exactly one self-change entry", len(entries) == 1,
          f"{len(entries)} entries")
    entry = entries[-1]
    check(f"[{name}] entry is attributed to the holder, not an administrator",
          entry["user_id"] == before["id"])
    check(f"[{name}] entry action is the self-change phrase",
          entry["action"] == "Changed own account password")
    check(f"[{name}] entry is filed under Authentication",
          entry["module"] == MODULE_AUTH, entry["module"])
    check(f"[{name}] entry is NOT the administrator's reset phrase",
          entry["action"] != ACTION_PASSWORD_RESET)
    details = entry["details"]
    check(f"[{name}] entry names the account", f'"{name}"' in details)
    check(f"[{name}] entry names the person", spec["full_name"] in details)
    check(f"[{name}] entry names the stored role", spec["role"] in details)
    check(f"[{name}] entry says the holder did it themselves",
          "changed the password on their own account" in details
          and "not on their behalf" in details)
    check(f"[{name}] entry says the current password was verified",
          "verified against the stored hash" in details)
    check(f"[{name}] entry distinguishes itself from an administrator's reset",
          "an administrator replacing this account's password is a different entry"
          in details)
    check(f"[{name}] entry carries NEITHER password",
          spec["old"] not in details and spec["new"] not in details)
    check(f"[{name}] no reset entry was written by a self-service change",
          len(audit_rows(ACTION_PASSWORD_RESET)) == before_reset_rows)

# Neither password appears anywhere in the whole audit table.
conn = db()
all_details = " ".join(
    str(row[0] or "") for row in conn.execute("SELECT details FROM audit_logs")
)
conn.close()
for spec in ROLES:
    check(f"[{spec['username']}] no password anywhere in audit_logs",
          spec["old"] not in all_details and spec["new"] not in all_details)

print("=" * 78)
print("PART 4 -- the guard, and forged posts")
print("=" * 78)

with flask_app.test_client() as client:
    response = client.get("/account")
    check("[anonymous] GET /account redirects to the login form",
          response.status_code == 302
          and "/login" in response.headers.get("Location", ""))
    admin_hash = user_row("admin")["password_hash"]
    response = change(client, _support.PASSWORDS["admin"], "Anonymous#Takeover1")
    check("[anonymous] POST /account/password redirects to the login form",
          response.status_code == 302
          and "/login" in response.headers.get("Location", ""))
    check("[anonymous] and changed nothing",
          user_row("admin")["password_hash"] == admin_hash)

# A forged post naming somebody else's account changes only the sender's.
staff_spec = ROLES[1]
admin_spec = ROLES[0]
admin_hash_before = user_row("admin")["password_hash"]
staff_hash_before = user_row("staff")["password_hash"]
forged_new = "Sariling@Bagong5Pass"
with flask_app.test_client() as client:
    sign_in(client, "staff", staff_spec["new"])
    response = change(
        client, staff_spec["new"], forged_new,
        extra={"user_id": str(user_row("admin")["id"]), "username": "admin"},
    )
    check("[forged] a post naming the Administrator's id is accepted as the sender's own",
          response.status_code == 302)
check("[forged] the Administrator's password is untouched",
      user_row("admin")["password_hash"] == admin_hash_before)
check("[forged] the Administrator still signs in with its own password",
      check_password_hash(user_row("admin")["password_hash"], admin_spec["new"]))
check("[forged] only the sender's own password changed",
      user_row("staff")["password_hash"] != staff_hash_before
      and check_password_hash(user_row("staff")["password_hash"], forged_new))
staff_spec["new"] = forged_new

# A deactivated account cannot reach My Account, and a maintenance window keeps
# non-Administrators off it -- both inherited from the shared guard.
conn = db()
conn.execute("UPDATE users SET is_active = 0 WHERE username = 'official'")
conn.commit()
conn.close()
with flask_app.test_client() as client:
    sign_in(client, "official", ROLES[2]["new"])
    response = client.get("/account")
    check("[deactivated] is refused at My Account like every other guarded screen",
          response.status_code == 302 and "/login" in response.headers.get("Location", ""))
conn = db()
conn.execute("UPDATE users SET is_active = 1 WHERE username = 'official'")
conn.commit()
conn.close()

from models.settings import set_maintenance_mode  # noqa: E402

staff_client = flask_app.test_client()
sign_in(staff_client, "staff", staff_spec["new"])
check("[maintenance] the staff session is live before the system closes",
      staff_client.get("/account").status_code == 200)
with flask_app.test_request_context():
    set_maintenance_mode(True, user_row("admin")["id"])
check("[maintenance] that same session cannot reach My Account while closed",
      staff_client.get("/account").status_code == 503,
      f"got {staff_client.get('/account').status_code}")
with flask_app.test_client() as client:
    sign_in(client, "admin", admin_spec["new"])
    check("[maintenance] the Administrator still can",
          client.get("/account").status_code == 200)
with flask_app.test_request_context():
    set_maintenance_mode(False, user_row("admin")["id"])
check("[maintenance] the staff session works again once it reopens",
      staff_client.get("/account").status_code == 200)
staff_client.__exit__(None, None, None) if hasattr(staff_client, "__exit__") else None
check("[maintenance] the system is open again",
      flask_app.test_client().get("/login").status_code == 200)

print("=" * 78)
print("PART 5 -- a password may begin or end with a space, and is not trimmed")
print("=" * 78)

spaced = " Gilid Space 2026! "
with flask_app.test_client() as client:
    sign_in(client, "official", ROLES[2]["new"])
    response = change(client, ROLES[2]["new"], spaced)
    check("[spaces] a space-padded password is accepted", response.status_code == 302)
check("[spaces] it is stored exactly as typed",
      check_password_hash(user_row("official")["password_hash"], spaced))
check("[spaces] the trimmed form does NOT verify",
      not check_password_hash(user_row("official")["password_hash"], spaced.strip()))
with flask_app.test_client() as client:
    response = sign_in(client, "official", spaced)
    check("[spaces] and it signs in at the login form",
          response.status_code == 302
          and response.headers.get("Location", "") == "/official/dashboard")
ROLES[2]["new"] = spaced

print("=" * 78)
print("PART 6 -- re-setting the same password: allowed, and reported honestly")
print("=" * 78)

same = ROLES[1]["new"]
before_entries = len(audit_rows(ACTION_PASSWORD_CHANGED_SELF, user_row("staff")["id"]))
with flask_app.test_client() as client:
    sign_in(client, "staff", same)
    response = change(client, same, same)
    check("[same] re-setting the current password is allowed", response.status_code == 302)
    landed = client.get("/account").get_data(as_text=True)
    check("[same] the flash says the credential is unchanged",
          "it is the same password you were already using" in landed)
check("[same] the password still works", check_password_hash(
    user_row("staff")["password_hash"], same))
entry = audit_rows(ACTION_PASSWORD_CHANGED_SELF, user_row("staff")["id"])[-1]
check("[same] a new entry was written",
      len(audit_rows(ACTION_PASSWORD_CHANGED_SELF, user_row("staff")["id"]))
      == before_entries + 1)
check("[same] the entry does NOT claim the old password stopped working",
      "the previous password stopped working" not in entry["details"])
check("[same] the entry says the credential is unchanged",
      "the credential itself is unchanged" in entry["details"])

print("=" * 78)
print("PART 7 -- no interference with the Administrator's Reset Password")
print("=" * 78)

target = user_row("bhwtest")
target_hash_before = target["password_hash"]
reset_value = "Reset@NgAdmin2026"
before_self = len(audit_rows(ACTION_PASSWORD_CHANGED_SELF))
with flask_app.test_client() as client:
    sign_in(client, "admin", admin_spec["new"])
    response = client.post(
        "/admin/user_management/reset_password",
        data={
            "user_id": str(target["id"]),
            "password": reset_value,
            "confirm_password": reset_value,
        },
    )
    check("[reset] the Administrator's reset still saves", response.status_code == 302)
    landed = client.get("/admin/user_management").get_data(as_text=True)
    check("[reset] and still flashes its own message",
          "password has been reset" in landed)

check("[reset] the target's hash changed",
      user_row("bhwtest")["password_hash"] != target_hash_before)
check("[reset] the target signs in with what the Administrator set",
      check_password_hash(user_row("bhwtest")["password_hash"], reset_value))
reset_entries = audit_rows(ACTION_PASSWORD_RESET, user_row("admin")["id"])
check("[reset] it writes the reset phrase, attributed to the ADMINISTRATOR",
      len(reset_entries) >= 1 and reset_entries[-1]["user_id"] == user_row("admin")["id"])
check("[reset] under User Management, not Authentication",
      reset_entries[-1]["module"] == MODULE_USERS, reset_entries[-1]["module"])
check("[reset] the two phrases are different strings",
      ACTION_PASSWORD_RESET != ACTION_PASSWORD_CHANGED_SELF)
check("[reset] a reset writes no self-change entry",
      len(audit_rows(ACTION_PASSWORD_CHANGED_SELF)) == before_self)

# And the reset target can then change it themselves -- the two paths compose.
own_value = "Akin@NaTalaga2026"
with flask_app.test_client() as client:
    response = sign_in(client, "bhwtest", reset_value)
    check("[reset] the reset account signs in", response.status_code == 302)
    response = change(client, reset_value, own_value)
    check("[reset] and can then change it themselves", response.status_code == 302)
check("[reset] the self-set value is what now works",
      check_password_hash(user_row("bhwtest")["password_hash"], own_value))
check("[reset] the administrator's value no longer works",
      not check_password_hash(user_row("bhwtest")["password_hash"], reset_value))
check("[reset] the account has both entry kinds against it, and they differ",
      len(audit_rows(ACTION_PASSWORD_RESET, user_row("bhwtest")["id"])) == 0
      and len(audit_rows(ACTION_PASSWORD_CHANGED_SELF, user_row("bhwtest")["id"])) == 1)

print("=" * 78)
print("PART 8 -- Add User and the login trail are unregressed")
print("=" * 78)

with flask_app.test_client() as client:
    sign_in(client, "admin", admin_spec["new"])

    # Add User still refuses a weak password and still reopens its dialog.
    response = client.post("/admin/user_management/add", data={
        "full_name": "Test Probe", "username": "tprobe",
        "role": "Health Center Staff",
        "password": "short", "confirm_password": "short",
    })
    html = response.get_data(as_text=True)
    check("[regression] Add User redisplays at 200", response.status_code == 200)
    check("[regression] Add User shows the strength error", "Too short." in html)
    check("[regression] Add User keeps what was typed",
          'value="Test Probe"' in html and 'value="tprobe"' in html)
    check("[regression] Add User reopens its dialog inside DOMContentLoaded",
          "DOMContentLoaded" in html and "addUserModal" in html)
    check("[regression] Add User does not write the password back",
          "short" not in html.split("addUserModal")[0].split('name="password"')[-1][:200])

    # And still creates a real account.
    response = client.post("/admin/user_management/add", data={
        "full_name": "Test Probe", "username": "tprobe",
        "role": "Health Center Staff",
        "password": "Malinis@Tubig2026", "confirm_password": "Malinis@Tubig2026",
    })
    check("[regression] Add User still creates an account", response.status_code == 302)
check("[regression] the new account is in the table",
      user_row("tprobe") is not None)

# The login trail still records both outcomes.
before_success = len(audit_rows(ACTION_LOGIN_SUCCESS, user_row("tprobe")["id"]))
with flask_app.test_client() as client:
    sign_in(client, "tprobe", "Malinis@Tubig2026")
check("[regression] a successful sign-in is still audited",
      len(audit_rows(ACTION_LOGIN_SUCCESS, user_row("tprobe")["id"]))
      == before_success + 1)
before_failed = len(audit_rows(ACTION_LOGIN_FAILED, user_row("tprobe")["id"]))
with flask_app.test_client() as client:
    sign_in(client, "tprobe", "definitely-wrong")
check("[regression] a refused sign-in is still audited",
      len(audit_rows(ACTION_LOGIN_FAILED, user_row("tprobe")["id"]))
      == before_failed + 1)

# The new account -- created after this feature existed -- can use it too.
with flask_app.test_client() as client:
    sign_in(client, "tprobe", "Malinis@Tubig2026")
    check("[regression] a newly created account reaches My Account",
          client.get("/account").status_code == 200)
    response = change(client, "Malinis@Tubig2026", "Sariwa@Hangin2026")
    check("[regression] and can change its own password", response.status_code == 302)
check("[regression] the new value works",
      check_password_hash(user_row("tprobe")["password_hash"], "Sariwa@Hangin2026"))

# Audit Logs renders the new phrase.
with flask_app.test_client() as client:
    sign_in(client, "admin", admin_spec["new"])
    html = client.get("/admin/audit_logs").get_data(as_text=True)
    check("[regression] Audit Logs renders", "Audit Logs" in html)
    check("[regression] the self-change phrase appears in the trail",
          "Changed own account password" in html)

print()
print("=" * 78)
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
print("=" * 78)
for failure in FAILED:
    print("FAILED:", failure)
sys.exit(1 if FAILED else 0)

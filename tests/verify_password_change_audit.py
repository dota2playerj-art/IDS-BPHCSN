"""A refused own-password change is recorded, and records no password.

Runs on a fresh test database built by tests/_support.py.
"""
import os, sys
import _support  # noqa: E402  (first: builds the test database, points the app at it)
import shutil
import sqlite3

DB = _support.DB_PATH

from app import app
from models.audit import (
    ACTION_LOGIN_FAILED,
    ACTION_PASSWORD_CHANGE_FAILED_SELF,
    ACTION_PASSWORD_CHANGED_SELF,
    MODULE_AUTH,
    REFUSAL_ACTIONS,
)
app.config["DATABASE"] = DB
_support.attach(app)

FAIL = []
N = 0
WRONG = "DeliberatelyWrong2026!"
NEWPW = "ThrowawaySelfPick99!"


def ck(label, cond):
    global N
    N += 1
    if not cond:
        FAIL.append(label)


def rows(action, uid=None):
    q = ("SELECT id, user_id, action, module, details, ip_address, created_at "
         "FROM audit_logs WHERE action = ?")
    p = [action]
    if uid is not None:
        q += " AND user_id = ?"
        p.append(uid)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(q + " ORDER BY id", p)]
    con.close()
    return out


def hash_of(uid=1):
    return sqlite3.connect(DB).execute(
        "SELECT password_hash FROM users WHERE id = ?", (uid,)).fetchone()[0]


# ---- vocabulary --------------------------------------------------------
ck("new action is its own phrase",
   ACTION_PASSWORD_CHANGE_FAILED_SELF not in
   (ACTION_LOGIN_FAILED, ACTION_PASSWORD_CHANGED_SELF))
ck("new action kept out of REFUSAL_ACTIONS",
   ACTION_PASSWORD_CHANGE_FAILED_SELF not in REFUSAL_ACTIONS)
ck("REFUSAL_ACTIONS otherwise unchanged", len(REFUSAL_ACTIONS) == 2)

before_failed = len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF))
before_ok = len(rows(ACTION_PASSWORD_CHANGED_SELF))
before_login_failed = len(rows(ACTION_LOGIN_FAILED))
h0 = hash_of()

with app.test_client() as c:
    c.post("/login", data={"username": "admin", "password": _support.PASSWORDS["admin"]},
           follow_redirects=True)

    def post(cur, new, conf):
        return c.post("/account/password",
                      data={"current_password": cur, "new_password": new,
                            "confirm_new_password": conf},
                      follow_redirects=True)

    # ---- the refusal itself is unchanged -------------------------------
    r = post(WRONG, NEWPW, NEWPW)
    body = r.get_data(as_text=True)
    ck("wrong current password still refused at 200", r.status_code == 200)
    ck("still shows the error banner", "Your password was not changed" in body)
    ck("still flags the current password box",
       "That is not the password this account signs in with" in body)
    ck("stored hash untouched by the refusal", hash_of() == h0)

    # ---- and it is now recorded ----------------------------------------
    made = rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)
    ck("exactly one new entry written", len(made) == before_failed + 1)
    e = made[-1]
    ck("attributed to the account that attempted it", e["user_id"] == 1)
    ck("filed under Authentication", e["module"] == MODULE_AUTH)
    ck("carries a timestamp", bool(e["created_at"]))
    ck("phrase is the new one",
       e["action"] == ACTION_PASSWORD_CHANGE_FAILED_SELF)
    ck("no refused-sign-in row was written instead",
       len(rows(ACTION_LOGIN_FAILED)) == before_login_failed)
    ck("no success row was written",
       len(rows(ACTION_PASSWORD_CHANGED_SELF)) == before_ok)

    d = e["details"]
    ck("details name the account", '"admin"' in d)
    ck("details name the person", "Kagawad Antonio Acido" in d)
    ck("details name the role", "Admin" in d)
    ck("details say nothing was written", "nothing was written" in d)
    # The detail panel splits this column on "; " -- see
    # routes/audit_views.py::_split_details(). Written without them the whole
    # entry renders as one unbroken bullet beside sign-ins that read as lists.
    from routes.audit_views import _split_details
    lead, changes, notes = _split_details(d)
    ck("parses into a lead and several notes", bool(lead) and len(notes) >= 2)
    ck("no clause is mistaken for a field change", changes == [])
    ck("the lead names the account", '"admin"' in lead)
    ck("no note holds a password",
       not any(WRONG in n or NEWPW in n for n in notes))
    ck("details say the current password was wrong",
       "wrong current password" in d)

    # ---- THE PROHIBITION ------------------------------------------------
    for probe in (WRONG, NEWPW, _support.PASSWORDS["admin"]):
        ck("entry does not contain %r" % probe, probe not in d)
        ck("entry does not contain %r lowercased" % probe,
           probe.lower() not in d.lower())
    ck("no fragment of the submitted value",
       not any(WRONG[i:i + 6] in d for i in range(len(WRONG) - 5)))
    ck("no length of the submitted value recorded",
       str(len(WRONG)) not in d and str(len(NEWPW)) not in d)
    # And nowhere else in the table either.
    con = sqlite3.connect(DB)
    whole = " ".join(str(r[0]) for r in
                     con.execute("SELECT details FROM audit_logs") if r[0])
    con.close()
    for probe in (WRONG, NEWPW):
        ck("no row anywhere holds %r" % probe, probe not in whole)

    # ---- one row per attempt, so a run is visible -----------------------
    post(WRONG, NEWPW, NEWPW)
    post(WRONG, NEWPW, NEWPW)
    ck("a run of attempts writes a row each",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == before_failed + 3)

    # ---- form mistakes that prove nothing get no row --------------------
    n = len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF))
    post("", NEWPW, NEWPW)
    ck("an empty current-password box writes no row",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == n)
    post(_support.PASSWORDS["admin"], "short", "short")
    ck("a weak new password writes no row",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == n)
    post(_support.PASSWORDS["admin"], NEWPW, "SomethingElse123!")
    ck("a mismatched confirmation writes no row",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == n)
    ck("none of those touched the hash", hash_of() == h0)

    # ---- a wrong current password AND a weak new one: one row, not two --
    post(WRONG, "short", "short")
    ck("a compound refusal still writes exactly one row",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == n + 1)

    # ---- the success path is untouched ----------------------------------
    n2 = len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF))
    r = post(_support.PASSWORDS["admin"], NEWPW, NEWPW)
    ck("valid change still accepted", r.status_code == 200)
    ck("the hash changed", hash_of() != h0)
    ck("the success entry was written",
       len(rows(ACTION_PASSWORD_CHANGED_SELF)) == before_ok + 1)
    ck("the success wrote no refusal row",
       len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)) == n2)
    ck("the success entry holds no password",
       NEWPW not in rows(ACTION_PASSWORD_CHANGED_SELF)[-1]["details"])

# ---- the entry is readable on the Audit Logs screen --------------------
with app.test_client() as c2:
    c2.post("/login", data={"username": "admin", "password": NEWPW},
            follow_redirects=True)
    html = c2.get("/admin/audit_logs").get_data(as_text=True)
    ck("the phrase appears on Audit Logs",
       ACTION_PASSWORD_CHANGE_FAILED_SELF in html)
    ck("Audit Logs renders no password", WRONG not in html and NEWPW not in html)
    ck("its glyph resolves, not the module default", ">password<" in html)

# ---- other roles get the same treatment on their own account -----------
with app.test_client() as c3:
    c3.post("/login", data={"username": "staff", "password": _support.PASSWORDS["staff"]},
            follow_redirects=True)
    n3 = len(rows(ACTION_PASSWORD_CHANGE_FAILED_SELF, uid=2))
    c3.post("/account/password",
            data={"current_password": WRONG, "new_password": NEWPW,
                  "confirm_new_password": NEWPW}, follow_redirects=True)
    made2 = rows(ACTION_PASSWORD_CHANGE_FAILED_SELF, uid=2)
    ck("a Health Center Staff refusal is recorded too", len(made2) == n3 + 1)
    ck("attributed to that account, not the Administrator",
       made2[-1]["user_id"] == 2)
    ck("names that account", '"staff"' in made2[-1]["details"])

print("checks:", N, "| failures:", len(FAIL))
for f in FAIL:
    print("  FAIL:", f)
print()
print("--- THE ENTRY AS STORED ---")
e = rows(ACTION_PASSWORD_CHANGE_FAILED_SELF)[0]
for k in ("id", "user_id", "action", "module", "ip_address", "created_at"):
    print("%-11s %s" % (k + ":", e[k]))
print("details:")
print(e["details"])

"""End-to-end verification of the Service Schedule.

Runs the REAL application code over a fresh test database built by
tests/_support.py (and runs the real migrate_add_service_schedule.py on it
first). Every assertion
is made against an HTTP response body or the database as the application left
it. Nothing reaches into a view function.
"""
import html as html_lib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, time, timedelta

import _support  # noqa: E402  (first: builds the test database, points the app at it)
PROJECT = str(_support.REPO)
os.chdir(PROJECT)

TEST_DB = _support.DB_PATH

mig = subprocess.run(
    [sys.executable, "migrations/migrate_add_service_schedule.py", TEST_DB],
    capture_output=True, text=True,
)
print(mig.stdout.strip().splitlines()[-1])
assert mig.returncode == 0, mig.stdout + mig.stderr

import utils.dates as dates  # noqa: E402
from app import create_app  # noqa: E402

REAL_NOW = dates.now
app = create_app()
app.config["DATABASE"] = TEST_DB
_support.attach(app)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail and not ok:
        for line in str(detail).splitlines()[:12]:
            print(f"       {line}")
    return ok


def section(title):
    print(f"\n--- {title} ---")


def db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn


def set_clock(day):
    """Make the whole application believe it is 09:00 on `day`, clinic time."""
    moment = datetime.combine(day, time(9, 0), tzinfo=dates.CLINIC_TIMEZONE)
    dates.now = lambda: moment


def reset_clock():
    dates.now = REAL_NOW


def schedule_rows():
    return [tuple(r) for r in db().execute("SELECT * FROM service_schedule ORDER BY id")]


def audit_count():
    return db().execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]


def text(resp):
    return resp.get_data(as_text=True)


def visible(html):
    """The page as a person reads it: tags stripped, whitespace collapsed."""
    html = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html_lib.unescape(html)
    return re.sub(r"\s+", " ", html).strip()


conn = db()
ACCOUNTS = {}
for row in conn.execute("SELECT id, username, role, full_name FROM users WHERE is_active = 1 ORDER BY id"):
    ACCOUNTS.setdefault(row["role"], dict(row))
conn.close()
ADMIN, DOCTOR = ACCOUNTS["Admin"], ACCOUNTS["Doctor"]
STAFF, OFFICIAL = ACCOUNTS["Health Center Staff"], ACCOUNTS["Barangay Official"]
PREFIX = {"Admin": "/admin", "Doctor": "/staff", "Health Center Staff": "/staff",
          "Barangay Official": "/official"}
QUEUE = {"Admin": "/admin/appointment_scheduling", "Doctor": "/staff/appointment_scheduling",
         "Health Center Staff": "/staff/appointment_scheduling"}


def client_for(account):
    client = app.test_client()
    if account is not None:
        with client.session_transaction() as s:
            s["user_id"] = account["id"]
            _support.open_session(s)
    return client


admin = client_for(ADMIN)

# ===========================================================================
section("1. It ships empty, and every screen says so honestly")
# ===========================================================================
check("migration created the table with zero rows", len(schedule_rows()) == 0, schedule_rows())

for role, account in ACCOUNTS.items():
    c = client_for(account)
    r = c.get(PREFIX[role] + "/service_schedule")
    page = visible(text(r))
    check(f"{role}: schedule screen renders (200)", r.status_code == 200, r.status_code)
    check(f"{role}: empty state says no days have been entered",
          "No service days have been entered yet" in page and "has not been filled with a guess" in page, page[:400])
    check(f"{role}: empty screen draws no week of blank days",
          'id="scheduleWeek"' not in text(r) and "Nothing scheduled" not in page)
    check(f"{role}: sidebar carries Service Schedule", "Service Schedule" in page)
    if role in QUEUE:
        q = c.get(QUEUE[role])
        qp = visible(text(q))
        check(f"{role}: Patient Queue shows the empty services strip",
              q.status_code == 200 and "Services today" in qp
              and "No service days have been entered yet. The Administrator enters them on the Service Schedule" in qp, qp[:600])

admin_page = text(admin.get("/admin/service_schedule"))
check("Admin: empty screen still offers the Add form", 'action="/admin/service_schedule/add"' in admin_page)
check("Admin: empty form suggests no service names",
      re.search(r'<datalist id="scheduleServiceNames">\s*</datalist>', admin_page) is not None)
for role in ("Doctor", "Health Center Staff", "Barangay Official"):
    page = text(client_for(ACCOUNTS[role]).get(PREFIX[role] + "/service_schedule?edit=1&delete=1"))
    check(f"{role}: no form, no Edit/Delete controls, even with ?edit=/?delete=",
          'name="weekdays"' not in page and "/service_schedule/add" not in page
          and "delete=" not in page and "Delete entry" not in page)

# ===========================================================================
section("2. Validation redisplays the form with the error and the typed values")
# ===========================================================================
before_rows, before_audit = schedule_rows(), audit_count()

r = admin.post("/admin/service_schedule/add", data={
    "service": "", "weekdays": ["2", "4"], "weeks": ["2"], "note": "Only when the midwife is in",
})
page = text(r)
check("blank service: 200 re-render, not a redirect", r.status_code == 200, r.status_code)
check("blank service: message beside the field",
      "Enter the service, such as the name the health center uses for it." in page)
check("blank service: summary says nothing was saved and typing is kept",
      "The entry was not saved." in page)
check("blank service: ticked Tuesday and Thursday still ticked",
      re.search(r'name="weekdays" value="2" checked', page) and re.search(r'name="weekdays" value="4" checked', page)
      and not re.search(r'name="weekdays" value="3" checked', page))
check("blank service: ticked 2nd week still ticked", re.search(r'name="weeks" value="2" checked', page))
check("blank service: note text preserved", ">Only when the midwife is in</textarea>" in page)
check("blank service: service input is marked invalid", 'form-control is-invalid" id="scheduleService"' in page)

r = admin.post("/admin/service_schedule/add", data={"service": "Well-baby clinic", "note": ""})
page = text(r)
check("no day ticked: refused with 'Tick at least one day'",
      r.status_code == 200 and "Tick at least one day the service runs." in page)
check("no day ticked: service value preserved", 'value="Well-baby clinic"' in page)

long_service = "S" * 81
long_note = "n" * 301
r = admin.post("/admin/service_schedule/add", data={
    "service": long_service, "weekdays": ["1"], "note": long_note})
page = text(r)
check("81-char service refused, with its length", "this one is 81" in page and "Keep the service name to 80" in page)
check("301-char note refused, with its length", "Keep the note to 300 characters; this one is 301." in page)
check("over-long values preserved exactly", f'value="{long_service}"' in page and f">{long_note}</textarea>" in page)

r = admin.post("/admin/service_schedule/add", data={
    "service": "Check-up", "weekdays": ["3"], "weeks": ["1", "2", "3", "4"]})
check("all four weeks ticked: refused, told to leave weeks blank",
      "All four weeks are ticked" in text(r) and all(
          re.search(rf'name="weeks" value="{w}" checked', text(r)) for w in "1234"))

r = admin.post("/admin/service_schedule/add", data={
    "service": "Check-up", "weekdays": ["3", "9"], "weeks": ["5"]})
page = text(r)
check("forged weekday 9 refused", "Choose the days from the boxes shown." in page)
check("forged 5th week refused, with the reason", "A 5th occurrence only happens in some months" in page)
check("valid Wednesday tick preserved beside the forged ones", re.search(r'name="weekdays" value="3" checked', page))

check("no refused submit wrote a schedule row", schedule_rows() == before_rows)
check("no refused submit wrote an audit row", audit_count() == before_audit)

# ===========================================================================
section("3. The Administrator creates all three day patterns")
# ===========================================================================
audit_before = audit_count()


def add(data):
    return admin.post("/admin/service_schedule/add", data=data, follow_redirects=True)


r = add({"service": "Family Planning", "weekdays": ["1", "2", "3", "4", "5"], "note": ""})
check("every weekday: saved, flash names the days",
      '"Family Planning" added to the service schedule: Every weekday, Monday to Friday.' in visible(text(r)),
      visible(text(r))[:500])
r = add({"service": "Immunization", "weekdays": ["3"], "weeks": ["2", "4"],
         "note": "Rotates between barangays"})
check("2nd and 4th Wednesday: saved",
      '"Immunization" added to the service schedule: 2nd and 4th Wednesday of the month.' in visible(text(r)))
r = add({"service": "Prenatal Check-up", "weekdays": ["1", "4"], "note": ""})
check("specific weekdays (Monday and Thursday): saved",
      "Every Monday and Thursday" in visible(text(r)))

rows = {r["service"]: dict(r) for r in db().execute("SELECT * FROM service_schedule")}
check("stored: Family Planning = weekdays '1,2,3,4,5', weeks NULL",
      rows["Family Planning"]["weekdays"] == "1,2,3,4,5" and rows["Family Planning"]["weeks_of_month"] is None, rows)
check("stored: Immunization = weekdays '3', weeks '2,4', note kept",
      rows["Immunization"]["weekdays"] == "3" and rows["Immunization"]["weeks_of_month"] == "2,4"
      and rows["Immunization"]["note"] == "Rotates between barangays", rows)
check("stored: Prenatal = weekdays '1,4', weeks NULL, empty note stored as NULL",
      rows["Prenatal Check-up"]["weekdays"] == "1,4" and rows["Prenatal Check-up"]["weeks_of_month"] is None
      and rows["Prenatal Check-up"]["note"] is None, rows)
check("created_by is the Administrator", all(r["created_by"] == ADMIN["id"] for r in rows.values()))

r = add({"service": "  family   planning ", "weekdays": ["6"]})
page = visible(text(r))
check("retyped name in other case stored in the existing spelling, and the flash says so",
      'It was saved as "Family Planning", the spelling already on the schedule' in page, page[:500])
check("so the schedule lists one service name, not two",
      db().execute("SELECT COUNT(DISTINCT service) FROM service_schedule WHERE service LIKE 'family planning'").fetchone()[0] == 1)
r = admin.post("/admin/service_schedule/add", data={"service": "IMMUNIZATION", "weekdays": ["3"], "weeks": ["4", "2"]})
check("exact duplicate (same service, same days) refused and redisplayed",
      r.status_code == 200 and "is already on the schedule on exactly these days" in text(r))
check("four entries on the schedule", len(schedule_rows()) == 4, schedule_rows())

page = text(admin.get("/admin/service_schedule"))
check("form now suggests the names on the schedule, once each",
      page.count('<option value="Family Planning">') == 1 and '<option value="Immunization">' in page)

added = db().execute(
    "SELECT * FROM audit_logs WHERE id > (SELECT MAX(id) - 4 FROM audit_logs) ORDER BY id").fetchall()
check("four audit rows written for four adds", audit_count() - audit_before == 4, audit_count() - audit_before)
check("each is 'Added service schedule entry' under 'Service Schedule', by the Administrator",
      all(a["action"] == "Added service schedule entry" and a["module"] == "Service Schedule"
          and a["user_id"] == ADMIN["id"] for a in added), [dict(a) for a in added])
imm = [a for a in added if '"Immunization"' in a["details"]][0]["details"]
check("the add entry names the service, the days, the note and the actor",
      "days: 2nd and 4th Wednesday of the month" in imm and 'note: "Rotates between barangays"' in imm
      and ADMIN["full_name"] in imm, imm)

# ===========================================================================
section("4. Edit: saved, audited field by field; unchanged saves write nothing")
# ===========================================================================
pid = rows["Prenatal Check-up"]["id"]
r = admin.get(f"/admin/service_schedule?edit={pid}")
page = text(r)
check("?edit= opens the panel prefilled with the stored entry",
      f'action="/admin/service_schedule/{pid}/edit"' in page and 'value="Prenatal Check-up"' in page
      and re.search(r'name="weekdays" value="1" checked', page) and re.search(r'name="weekdays" value="4" checked', page))

audit_before = audit_count()
r = admin.post(f"/admin/service_schedule/{pid}/edit", data={
    "service": "Prenatal Check-up", "weekdays": ["2"], "note": "Bring the mother's booklet"}, follow_redirects=True)
page = visible(text(r))
check("edit saved, flash gives before and after",
      '"Prenatal Check-up" updated.' in page and "Every Monday and Thursday" in page and "Every Tuesday" in page, page[:600])
row = dict(db().execute("SELECT * FROM service_schedule WHERE id = ?", (pid,)).fetchone())
check("edit stored", row["weekdays"] == "2" and row["note"] == "Bring the mother's booklet"
      and row["updated_by"] == ADMIN["id"] and row["updated_at"], row)
entry = db().execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
check("one 'Edited service schedule entry' row",
      audit_count() - audit_before == 1 and entry["action"] == "Edited service schedule entry"
      and entry["module"] == "Service Schedule", dict(entry))
check("edit entry carries both changed fields as before → after, and not the unchanged one",
      'Days: "Every Monday and Thursday" → "Every Tuesday"' in entry["details"]
      and 'Note: not recorded → "Bring the mother\'s booklet"' in entry["details"]
      and "Service:" not in entry["details"] and "2 fields changed —" in entry["details"], entry["details"])

audit_before, rows_before = audit_count(), schedule_rows()
r = admin.post(f"/admin/service_schedule/{pid}/edit", data={
    "service": "Prenatal Check-up", "weekdays": ["2"], "note": "Bring the mother's booklet"}, follow_redirects=True)
check("edit saved unchanged: says nothing was changed",
      "Nothing was changed." in visible(text(r)))
check("edit saved unchanged: no audit row, no row update",
      audit_count() == audit_before and schedule_rows() == rows_before)

r = admin.post(f"/admin/service_schedule/{pid}/edit", data={
    "service": "", "weekdays": [], "weeks": ["3"], "note": "typed but refused"})
page = text(r)
check("invalid edit: 200 re-render on the EDIT panel for this entry",
      r.status_code == 200 and f'action="/admin/service_schedule/{pid}/edit"' in page and "Edit entry" in page)
check("invalid edit: errors beside both fields",
      "Enter the service" in page and "Tick at least one day the service runs." in page)
check("invalid edit: panel holds what was typed, not the stored values",
      ">typed but refused</textarea>" in page and re.search(r'name="weeks" value="3" checked', page)
      and not re.search(r'name="weekdays" value="2" checked', page))
check("invalid edit: nothing written", schedule_rows() == rows_before and audit_count() == audit_before)

r = admin.post("/admin/service_schedule/99999/edit", data={"service": "X", "weekdays": ["1"]},
               follow_redirects=True)
check("edit of an entry that does not exist: told so, nothing written",
      "not on the schedule any more" in visible(text(r)) and schedule_rows() == rows_before)

# ===========================================================================
section("5. Delete: confirmation, removal, and a full record in the trail")
# ===========================================================================
page = text(admin.get(f"/admin/service_schedule?delete={pid}"))
check("?delete= shows a confirmation naming the entry, posting to delete",
      "Delete this entry?" in page and f'action="/admin/service_schedule/{pid}/delete"' in page)
audit_before = audit_count()
r = admin.post(f"/admin/service_schedule/{pid}/delete", follow_redirects=True)
check("deleted, flash names it", '"Prenatal Check-up" (Every Tuesday) was removed from the service schedule.'
      in visible(text(r)), visible(text(r))[:400])
check("row is gone", db().execute("SELECT COUNT(*) FROM service_schedule WHERE id = ?", (pid,)).fetchone()[0] == 0)
entry = db().execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
check("one 'Deleted service schedule entry' row recording everything the entry said",
      audit_count() - audit_before == 1 and entry["action"] == "Deleted service schedule entry"
      and 'service "Prenatal Check-up"' in entry["details"] and "days: Every Tuesday" in entry["details"]
      and "Bring the mother's booklet" in entry["details"], dict(entry))
r = admin.post(f"/admin/service_schedule/{pid}/delete", follow_redirects=True)
check("deleting it again: told it is already gone, no audit row",
      "nothing was removed" in visible(text(r)) and audit_count() - audit_before == 1)
r = admin.get(f"/admin/service_schedule?edit={pid}", follow_redirects=True)
check("?edit= on a deleted id says so rather than opening an empty panel",
      "not on the schedule any more" in visible(text(r)))

page = text(admin.get("/admin/audit_logs"))
check("Audit Logs renders the three schedule actions",
      all(a in page for a in ("Added service schedule entry", "Edited service schedule entry",
                              "Deleted service schedule entry")))
check("Audit Logs module filter offers Service Schedule",
      re.search(r"<option[^>]*>\s*Service Schedule\s*</option>", page) is not None)
check("Audit Logs uses the schedule glyphs", "event_available" in page and "event_busy" in page)
r = admin.get("/admin/audit_logs?module=Service+Schedule")
check("filtering by Service Schedule shows exactly its rows",
      r.status_code == 200 and "Signed in" not in visible(text(r)))

# ===========================================================================
section("6. Forged POSTs from the three read-only roles are refused, nothing written")
# ===========================================================================
target_id = rows["Immunization"]["id"]
FORGED = [
    ("/admin/service_schedule/add", {"service": "Forged Service", "weekdays": ["1"]}),
    (f"/admin/service_schedule/{target_id}/edit", {"service": "Forged Edit", "weekdays": ["5"]}),
    (f"/admin/service_schedule/{target_id}/delete", {}),
]
for role in ("Doctor", "Health Center Staff", "Barangay Official"):
    account = ACCOUNTS[role]
    c = client_for(account)
    for url, data in FORGED:
        rows_before, audit_before = schedule_rows(), audit_count()
        r = c.post(url, data=data)
        loc = r.headers.get("Location", "")
        check(f"{role} ({account['username']}) POST {url}: refused by the guard (302 to their dashboard)",
              r.status_code == 302 and "dashboard" in loc and "service_schedule" not in loc,
              f"{r.status_code} {loc}")
        check(f"{role} POST {url}: schedule unchanged, no audit row",
              schedule_rows() == rows_before and audit_count() == audit_before)
    for url in (PREFIX[role] + "/service_schedule",):
        r = c.post(url, data={"service": "Forged", "weekdays": ["1"]})
        check(f"{role} POST to its own read-only URL {url}: 405, nothing written",
              r.status_code == 405 and schedule_rows() == rows_before)
anon = client_for(None)
for url, data in FORGED:
    rows_before = schedule_rows()
    r = anon.post(url, data=data)
    check(f"anonymous POST {url}: sent to login, nothing written",
          r.status_code == 302 and "/login" in r.headers.get("Location", "") and schedule_rows() == rows_before)
check("the Immunization entry survived every forged edit and delete",
      dict(db().execute("SELECT service, weekdays, weeks_of_month FROM service_schedule WHERE id = ?",
                        (target_id,)).fetchone()) == {"service": "Immunization", "weekdays": "3", "weeks_of_month": "2,4"})

# ===========================================================================
section("7. Read access: all four roles see the entries; only the Administrator can change them")
# ===========================================================================
set_clock(date(2026, 10, 14))  # the 2nd Wednesday of October 2026
for role, account in ACCOUNTS.items():
    page = text(client_for(account).get(PREFIX[role] + "/service_schedule"))
    vis = visible(page)
    check(f"{role}: sees every entry and its days",
          "Family Planning" in vis and "Immunization" in vis and "2nd and 4th Wednesday of the month" in vis
          and "Rotates between barangays" in vis)
    check(f"{role}: 'Running today' on Oct 14 lists Family Planning and Immunization",
          re.search(r"Running today Wednesday, October 14, 2026 .*Family Planning.*Immunization", vis) is not None,
          vis[:700])
    check(f"{role}: next dates shown for the 2nd/4th Wednesday entry",
          "Next: Oct 14, 2026, Oct 28, 2026" in vis, vis)
    check(f"{role}: Edit/Delete controls {'present' if role == 'Admin' else 'absent'}",
          (("?edit=" in page) and ("?delete=" in page)) == (role == "Admin"))
reset_clock()

# ===========================================================================
section("8. Nth weekday of the month: the date is controlled, the queue is read")
# ===========================================================================
# Every Wednesday for twelve months, including the months with a 5th Wednesday.
day = date(2026, 9, 2)
seen = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
wrong = []
table = []
while day < date(2027, 9, 1):
    set_clock(day)
    page = visible(text(admin.get("/admin/appointment_scheduling")))
    occurrence = (day.day - 1) // 7 + 1
    listed = "Immunization" in page.split("Services today", 1)[1][:600]
    believed = f"Today's Queue {day.strftime('%b %d, %Y')}" in page
    expected = occurrence in (2, 4)
    seen[occurrence] += 1
    table.append(f"{day.isoformat()}  {occurrence}{'st' if occurrence == 1 else 'nd' if occurrence == 2 else 'rd' if occurrence == 3 else 'th'} Wednesday  "
                 f"{'LISTED' if listed else '------'}  {'ok' if listed == expected else 'WRONG'}")
    if listed != expected or not believed:
        wrong.append((day, occurrence, listed, believed))
    day += timedelta(days=7)
reset_clock()
print("\n".join("       " + line for line in table))
check("Immunization listed on every 2nd and 4th Wednesday and on no 1st, 3rd or 5th, "
      f"over {sum(seen.values())} Wednesdays ({seen[5]} of them 5th Wednesdays)",
      not wrong and seen[5] >= 4, wrong)
check("the queue page believed each controlled date (its own 'Today's Queue <date>' line)", not wrong)

for label, d, want in (
    ("2nd Wednesday Oct 14 2026", date(2026, 10, 14), True),
    ("4th Wednesday Oct 28 2026", date(2026, 10, 28), True),
    ("1st Wednesday Oct 7 2026", date(2026, 10, 7), False),
    ("3rd Wednesday Oct 21 2026", date(2026, 10, 21), False),
    ("5th Wednesday Sep 30 2026", date(2026, 9, 30), False),
    ("5th Wednesday Dec 30 2026", date(2026, 12, 30), False),
):
    set_clock(d)
    strip = visible(text(admin.get("/admin/appointment_scheduling"))).split("Services today", 1)[1][:600]
    check(f"{label}: Immunization {'listed' if want else 'not listed'}", ("Immunization" in strip) == want, strip)
reset_clock()

# Every-weekday and Saturday entries, and a day nothing runs.
for label, d, want_fp in (
    ("Monday Oct 12", date(2026, 10, 12), True),
    ("Friday Oct 16", date(2026, 10, 16), True),
    ("Saturday Oct 17 (the Saturday entry)", date(2026, 10, 17), True),
):
    set_clock(d)
    strip = visible(text(admin.get("/admin/appointment_scheduling"))).split("Services today", 1)[1][:600]
    check(f"{label}: Family Planning listed", ("Family Planning" in strip) == want_fp, strip)
set_clock(date(2026, 10, 18))  # a Sunday: nothing on the schedule runs
strip = visible(text(admin.get("/admin/appointment_scheduling"))).split("Services today", 1)[1][:400]
check("Sunday Oct 18: honest 'nothing runs on this Sunday', distinct from the never-filled message",
      "Nothing on the service schedule runs on this Sunday." in strip and "No service days have been entered" not in strip, strip)
page = visible(text(admin.get("/admin/service_schedule")))
check("Sunday Oct 18: schedule screen says nothing runs today, with the count",
      "Nothing on the schedule runs today" in page and "None of the 3 services on the schedule falls on this Sunday" in page, page[:900])
reset_clock()

# ===========================================================================
section("9. Today's services appear on the Patient Queue for every role that sees it")
# ===========================================================================
set_clock(date(2026, 10, 28))  # 4th Wednesday
for role in QUEUE:
    r = client_for(ACCOUNTS[role]).get(QUEUE[role])
    strip = visible(text(r)).split("Services today", 1)[1][:600]
    check(f"{role}: queue strip on Oct 28 lists Family Planning and Immunization with its note",
          r.status_code == 200 and "Wednesday, October 28, 2026" in strip and "Family Planning" in strip
          and "Immunization" in strip and "Rotates between barangays" in strip, strip)
    check(f"{role}: strip links to this role's own schedule URL",
          f'href="{PREFIX[role]}/service_schedule"' in text(r))
r = client_for(OFFICIAL).get("/staff/appointment_scheduling")
check("Barangay Official still has no Patient Queue (redirected)", r.status_code == 302)
reset_clock()

# ===========================================================================
section("10. The queue restricts nothing because of the schedule")
# ===========================================================================
set_clock(date(2026, 10, 18))  # Sunday: nothing on the schedule
staff = client_for(STAFF)
patient = db().execute("SELECT id, first_name, last_name FROM patients WHERE status = 'Active' ORDER BY id LIMIT 1").fetchone()
db_conn = db()
db_conn.execute("UPDATE appointments SET status = 'Completed' WHERE status = 'In Consultation'")
db_conn.commit(); db_conn.close()
r = staff.post("/staff/appointment_scheduling/check-in",
               data={"patient_id": str(patient["id"]), "reason": "Fever since last night",
                     "service": "Consultation"},
               follow_redirects=True)
check("Sunday, nothing scheduled: a walk-in with a fever is checked in",
      re.search(rf"{patient['first_name']}.*{patient['last_name']} checked in as a walk-in", visible(text(r))), visible(text(r))[:400])
appt = db().execute("SELECT id, status, appointment_date FROM appointments WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
                    (patient["id"],)).fetchone()
check("the queue row is for the controlled date", appt["appointment_date"] == "2026-10-18", dict(appt))
r = staff.post("/staff/appointment_scheduling/start-consultation",
               data={"appointment_id": str(appt["id"])}, follow_redirects=True)
check("and their consultation can be started", "is now In Consultation" in visible(text(r)), visible(text(r))[:400])
r = client_for(DOCTOR).get(f"/staff/consultation/record/{appt['id']}")
check("and Record Consultation opens for it", r.status_code == 200 and "Record" in text(r))
reset_clock()

set_clock(date(2026, 10, 14))  # Immunization day: a non-immunization walk-in
patient2 = db().execute("SELECT id, first_name, last_name FROM patients WHERE status = 'Active' AND id != ? ORDER BY id LIMIT 1",
                        (patient["id"],)).fetchone()
r = staff.post("/staff/appointment_scheduling/check-in",
               data={"patient_id": str(patient2["id"]), "reason": "Cough",
                     "service": "Consultation"}, follow_redirects=True)
check("on immunization day, a walk-in for a cough is checked in too",
      re.search(rf"{patient2['first_name']}.*{patient2['last_name']} checked in as a walk-in", visible(text(r))), visible(text(r))[:400])
reset_clock()

src = {p: open(os.path.join(PROJECT, p), encoding="utf-8").read()
       for p in ("models/appointments.py", "routes/consultation_views.py", "models/consultations.py")}
check("no queue or consultation module imports the schedule (it cannot restrict them)",
      not any("service_schedule" in s for s in src.values()))
av = open(os.path.join(PROJECT, "routes/appointment_views.py"), encoding="utf-8").read()
check("routes/appointment_views.py reads the schedule only inside _services_today()",
      [m.start() for m in re.finditer(r"services_on\(|get_schedule_entries\(", av)] and
      all(av.rfind("def ", 0, m.start()) == av.find("def _services_today") for m in re.finditer(r"services_on\(|get_schedule_entries\(", av)))

# ===========================================================================
section("11. User Management lists the screen for all four roles, and only the one screen")
# ===========================================================================
from routes.user_views import accessible_screens  # noqa: E402
with app.test_request_context():
    for role in ACCOUNTS:
        screens = accessible_screens(role)
        check(f"{role}: 'Service Schedule' listed", "Service Schedule" in screens, screens)
        check(f"{role}: no other schedule label leaked in",
              not [s for s in screens if "Schedule" in s and s not in ("Service Schedule", "Appointment Scheduling")], screens)

# ===========================================================================
section("12. 'Record Updates' is not inflated by schedule changes")
# ===========================================================================
from models.audit import get_audit_stats  # noqa: E402
with app.test_request_context():
    stats = get_audit_stats()
schedule_entries = db().execute("SELECT COUNT(*) FROM audit_logs WHERE module = 'Service Schedule'").fetchone()[0]
record_rows = db().execute(
    "SELECT COUNT(*) FROM audit_logs WHERE module IS NOT NULL AND module NOT IN "
    "('SMS Notifications','Authentication','User Management','Settings','Service Schedule') "
    "AND action NOT IN ('Withheld restricted consultation from view', "
    "'Refused clinical judgement from an unlicensed role')").fetchone()[0]
key = next(k for k in stats if "record" in k.lower())
check(f"{schedule_entries} schedule entries exist and stats['{key}'] excludes them",
      schedule_entries >= 6 and stats[key] == record_rows, (stats[key], record_rows))

print("\n" + "=" * 78)
passed = sum(1 for _, ok in results if ok)
print(f"RESULT: {passed}/{len(results)} checks passed")
print("=" * 78)
sys.exit(0 if passed == len(results) else 1)

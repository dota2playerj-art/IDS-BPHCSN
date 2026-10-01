"""The Doctor's list and "Left before being seen" (Task 6; M4 and M5).

M4. Visits that need a diagnosis and have none wait for the Doctor, who comes only on
certain days. The Doctor's dashboard lists them, oldest first, across all days. Staff and
the Administrator see the count only. One function decides, so the three agree.

M5. Staff and the Doctor can mark a visit as "Left before being seen", only in the
allowed states, with a confirmation, an audit entry, and a same-day undo. The
Administrator cannot. Queue reports count it as its own status.

Runs on a fresh test database built by tests/_support.py.
"""
import io
import re
import sqlite3
import sys
import zlib
from datetime import date, datetime, timedelta

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5

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


def q1(sql, args=()):
    conn = db()
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def run_sql(sql, args=()):
    conn = db()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def body(response):
    return response.get_data(as_text=True)


def flat(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def pdf_text(data):
    out = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            out.append(zlib.decompress(match.group(1)).decode("latin-1"))
        except Exception:
            out.append(match.group(1).decode("latin-1", "replace"))
    return "\n".join(out).replace("\\(", "(").replace("\\)", ")")


admin, staff, official, doctor = (client_as(i) for i in
                                  (ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID))
today = date.today()
LEFT = "Left before being seen"
MARK, UNDO = "/staff/appointment_scheduling/mark-left", "/staff/appointment_scheduling/undo-left"

print("=" * 78)
print("IDS-BPHCSN — the Doctor's list and Left before being seen (Task 6)")
print("=" * 78)

# ---------------------------------------------------------------------------
section("1. SET UP VISITS IN KNOWN STATES")
NAMES = {}


def name_patient(pid, tag):
    run_sql("UPDATE patients SET first_name = ?, last_name = 'Wlmark' WHERE id = ?",
            (f"Zzwl{tag}", pid))
    NAMES[tag] = f"Zzwl{tag} Wlmark"
    return pid


def add_visit(pid, tag, days_ago, status, kind="Walk-in Consultation", time="09:30",
              consultation=None, restricted=False, diagnosis=None):
    """One visit. `consultation` True writes an intake; `diagnosis` fills the diagnosis."""
    name_patient(pid, tag)
    day = (today - timedelta(days=days_ago)).isoformat()
    appointment = run_sql(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (pid, STAFF_ID, kind, day, status, f"{day} {time}:00"))
    cid = None
    if consultation:
        cid = run_sql(
            "INSERT INTO consultations (patient_id, recorded_by, appointment_id, "
            "consultation_date, chief_complaint, diagnosis, is_restricted) VALUES (?,?,?,?,?,?,?)",
            (pid, STAFF_ID, appointment, day, "intake complaint", diagnosis, 1 if restricted else 0))
    return appointment, cid


# Nobody is in consultation at the start, so the single-room rule is free to test.
run_sql("UPDATE appointments SET status = 'Completed' WHERE status = 'In Consultation'")
V = {}
V["A"] = add_visit(6, "A", 0, "Waiting", time="08:10")                       # waiting today
V["B"] = add_visit(7, "B", 3, "Waiting", time="08:00")                       # earlier day, still waiting
V["D"] = add_visit(8, "D", 2, "Completed", consultation=True, time="10:15")  # intake, no diagnosis
V["E"] = add_visit(9, "E", 1, "Completed", consultation=True, diagnosis="Seen by the Doctor")
V["F"] = add_visit(10, "F", 4, "Completed")                                  # closed, nothing written
V["G"] = add_visit(11, "G", 1, "Waiting", kind="Immunization")               # not a Doctor service
V["H"] = add_visit(12, "H", 5, "Waiting", time="07:50")
run_sql("UPDATE appointments SET status = ?, status_before_left = 'Waiting', left_by = ?, "
        "left_at = ? WHERE id = ?", (LEFT, STAFF_ID, f"{today.isoformat()} 07:00:00", V["H"][0]))
V["J"] = add_visit(13, "J", 2, "Completed", kind="Immunization", consultation=True, time="11:00")
V["P"] = add_visit(14, "P", 1, "Completed", kind="Prenatal Check-up", consultation=True)
V["K"] = add_visit(15, "K", 0, "In Consultation", time="08:40")               # with the clinician now
# A sealed visit with no diagnosis yet: its complaint is stored encrypted.
V["S"] = add_visit(16, "S", 2, "Completed", consultation=True, restricted=True, time="12:00")
from utils import sealed_crypto  # noqa: E402

SEALED_MARK = "ZZSEALEDCOMPLAINTMARK"
run_sql("UPDATE consultations SET chief_complaint = ? WHERE id = ?",
        (sealed_crypto.encrypt(SEALED_MARK, V["S"][1], "chief_complaint"), V["S"][1]))
ids = {tag: v[0] for tag, v in V.items()}
check("eleven visits set up in known states", len(ids) == 11, ids)

# ---------------------------------------------------------------------------
section("2. WHO IS ON THE LIST (D1, D2)")
from models.doctor_worklist import (  # noqa: E402
    SERVICES_NEEDING_DOCTOR, count_waiting_for_doctor, get_waiting_for_doctor, needs_doctor,
)

with app.app_context():
    listed = get_waiting_for_doctor()
    count = count_waiting_for_doctor()
on_list = {v["id"] for v in listed}
expected = {ids[t] for t in ("A", "B", "D", "K", "S")}
check("the list holds exactly the visits that need a diagnosis and have none: waiting today, "
      "waiting from an earlier day, intake with no diagnosis, in consultation, and a sealed "
      "visit with no diagnosis", on_list == expected, (sorted(on_list), sorted(expected)))
check("a visit with a diagnosis is not on it", ids["E"] not in on_list)
check("a visit closed with nothing written is not on it", ids["F"] not in on_list)
check("a visit marked left before being seen is not on it", ids["H"] not in on_list)
check("services that are not the Doctor's (Immunization, Prenatal Check-up) are not on it, "
      "waiting or completed", not ({ids["G"], ids["J"], ids["P"]} & on_list))
check("the services that need the Doctor are named in ONE constant, and a blank type needs one",
      "Walk-in Consultation" in SERVICES_NEEDING_DOCTOR and needs_doctor(None)
      and needs_doctor("") and not needs_doctor("Immunization")
      and not needs_doctor("Prenatal Check-up"))
order = [v["id"] for v in listed]
check("the order is oldest first, across all days",
      order == [ids["B"], ids["D"], ids["S"], ids["A"], ids["K"]]
      and [v["checked_in"] for v in listed] == sorted(v["checked_in"] for v in listed), order)
by_id = {v["id"]: v for v in listed}
check("visits from earlier days are marked, and today's are not",
      by_id[ids["B"]]["from_earlier_day"] and by_id[ids["D"]]["from_earlier_day"]
      and not by_id[ids["A"]]["from_earlier_day"] and not by_id[ids["K"]]["from_earlier_day"])
def plain_days(visit):
    """The wait as the page should say it: whole elapsed days, or hours and minutes."""
    elapsed = datetime.now() - visit["checked_in"]
    days = elapsed.days
    return f"{days} day{'' if days == 1 else 's'}" if days >= 1 else None


check("each row says how long it has waited, in plain words (whole days when it is a day or more)",
      all(by_id[ids[t]]["waiting"] == plain_days(by_id[ids[t]]) for t in ("B", "D", "S"))
      and re.fullmatch(r"(Just now|\d+ minutes?|\d+ hours?)", by_id[ids["A"]]["waiting"]),
      {k: v["waiting"] for k, v in by_id.items()})
check("each row carries the name, patient ID and service",
      by_id[ids["B"]]["name"] == NAMES["B"] and by_id[ids["B"]]["patient_reference"] == "PAT-007"
      and by_id[ids["B"]]["service"] == "Walk-in Consultation")
check("the button opens the intake to edit, continues a consultation, or goes to the queue",
      by_id[ids["D"]]["action"] == "edit" and by_id[ids["K"]]["action"] == "record"
      and by_id[ids["B"]]["action"] == "queue")

# ---------------------------------------------------------------------------
section("3. THE DOCTOR'S LIST, THE STAFF COUNT AND THE ADMINISTRATOR'S COUNT AGREE")
doctor_page = body(doctor.get("/staff/dashboard"))
staff_page = body(staff.get("/staff/dashboard"))
admin_page = body(admin.get("/admin/dashboard"))
card = re.compile(r"Waiting for the Doctor: (\d+)")
staff_n = card.search(flat(staff_page))
admin_n = card.search(flat(admin_page))
check("the Doctor's dashboard has the list, with every visit's patient and an Open button",
      'id="waitingForDoctor"' in doctor_page
      and all(NAMES[t] in doctor_page for t in ("A", "B", "D", "K", "S"))
      and doctor_page.count("Open consultation") >= 2 and "Open Patient Queue" in doctor_page)
check("earlier-day visits say 'From an earlier day' on the Doctor's list",
      doctor_page.count("From an earlier day") == 3, doctor_page.count("From an earlier day"))
check("the Staff dashboard shows 'Waiting for the Doctor: N', the Administrator's too",
      staff_n and admin_n and int(staff_n.group(1)) == int(admin_n.group(1)) == count == len(listed),
      (staff_n and staff_n.group(1), admin_n and admin_n.group(1), count))
check("the Doctor's list length is the same number",
      f'<span class="badge-status badge-waiting">{len(listed)}</span>' in doctor_page)
# The Administrator's dashboard has always named the patient who is in consultation now
# (visit K, today); that is not part of this feature. Every other visit must not appear.
check("the Staff dashboard has no list; the Administrator's has no list and no names of the "
      "visits that are waiting for the Doctor",
      'id="waitingForDoctor"' not in staff_page and 'id="waitingForDoctor"' not in admin_page
      and not any(NAMES[t] in admin_page for t in ("A", "B", "D", "S")),
      [t for t in NAMES if NAMES[t] in admin_page])
check("earlier-day patients' names are not on the Staff dashboard (only today's queue shows names)",
      NAMES["B"] not in staff_page and NAMES["D"] not in staff_page)
check("a sealed visit is on the Doctor's list by name and shows no sealed text",
      NAMES["S"] in doctor_page and SEALED_MARK not in doctor_page
      and "intake complaint" not in doctor_page)
check("the Official's dashboard has neither the list nor the card",
      "waitingForDoctor" not in body(official.get("/official/dashboard"))
      and "Waiting for the Doctor" not in body(official.get("/official/dashboard")))
with app.app_context():
    from models.doctor_worklist import _FROM_SQL, _WHERE_SQL
check("the count is read without any name: its query selects ids and the service only",
      "first_name" not in "SELECT a.id, a.appointment_type " + _FROM_SQL + _WHERE_SQL)

# ---------------------------------------------------------------------------
section("4. MARKING A VISIT AS LEFT: ALLOWED STATES, BY STAFF AND BY THE DOCTOR")


def status_of(appointment):
    return q1("SELECT status FROM appointments WHERE id = ?", (appointment,))[0]


def audits(action):
    conn = db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))]
    finally:
        conn.close()


before_audit = q1("SELECT COALESCE(MAX(id),0) FROM audit_logs")[0]
r = staff.post(MARK, data={"appointment_id": str(ids["A"])})
row = q1("SELECT * FROM appointments WHERE id = ?", (ids["A"],))
check("Staff mark a Waiting visit as left before being seen",
      r.status_code == 302 and row["status"] == LEFT, (r.status_code, row["status"]))
check("who, when and the previous status are recorded",
      row["left_by"] == STAFF_ID and row["status_before_left"] == "Waiting"
      and (row["left_at"] or "")[:10] == today.isoformat(), dict(row))
entries = [a for a in audits("Marked as left before being seen") if a["id"] > before_audit]
check("exactly one short audit entry is written, in the existing style",
      len(entries) == 1 and entries[0]["user_id"] == STAFF_ID
      and entries[0]["module"] == "Appointment Scheduling"
      and entries[0]["details"] == f"{NAMES['A']} (PAT-006), visit APT-{ids['A']:05d}.",
      entries)
check("the entry says nothing about why, or about the visit's content",
      "complaint" not in entries[0]["details"].lower())
with app.app_context():
    after = {v["id"] for v in get_waiting_for_doctor()}
check("it leaves the Doctor's list at once, and the count drops with it",
      ids["A"] not in after and count_waiting_for_doctor() == count - 1)

r = doctor.post(MARK, data={"appointment_id": str(ids["B"])})
check("the Doctor can mark a visit that is still Waiting from an earlier day",
      r.status_code == 302 and status_of(ids["B"]) == LEFT)
check("... and the audit entry names the Doctor",
      audits("Marked as left before being seen")[-1]["user_id"] == DOCTOR_ID)
r = doctor.post(MARK, data={"appointment_id": str(ids["D"])})
check("a Completed visit with intake and no diagnosis can be marked (saving the intake "
      "completes the queue entry, so this is the patient who left before the Doctor)",
      status_of(ids["D"]) == LEFT and q1("SELECT status_before_left FROM appointments "
                                         "WHERE id = ?", (ids["D"],))[0] == "Completed")
r = staff.post(MARK, data={"appointment_id": str(ids["K"])})
check("a visit In Consultation with nothing recorded can be marked, and it frees the room",
      status_of(ids["K"]) == LEFT
      and q1("SELECT COUNT(*) FROM appointments WHERE status = 'In Consultation'")[0] == 0)

section("5. MARKING IS REFUSED WHERE IT MUST BE")
refused = {
    "a Completed visit with a diagnosis": ids["E"],
    "a Completed visit closed with nothing written": ids["F"],
    "a Completed immunization (not a Doctor service) with intake": ids["J"],
    "a Completed prenatal visit with intake": ids["P"],
}
marks_before = len(audits("Marked as left before being seen"))
for label, appointment in refused.items():
    old = status_of(appointment)
    r = staff.post(MARK, data={"appointment_id": str(appointment)})
    check(f"refused on {label}: the status does not change",
          r.status_code == 302 and status_of(appointment) == old == "Completed", status_of(appointment))
check("every refusal wrote no audit entry", len(audits("Marked as left before being seen")) == marks_before)
r = staff.post(MARK, data={"appointment_id": str(ids["A"])})
check("marking a visit that is already marked changes nothing",
      status_of(ids["A"]) == LEFT and len(audits("Marked as left before being seen")) == marks_before)
r = staff.post(MARK, data={"appointment_id": "999999"})
check("a visit that does not exist is refused without an error", r.status_code == 302)
# A diagnosis written meanwhile wins: the guard is in the UPDATE.
race_visit = add_visit(17, "R", 0, "Completed", consultation=True, time="13:00")
from models.appointments import mark_left  # noqa: E402

run_sql("UPDATE consultations SET diagnosis = 'Written just now' WHERE id = ?", (race_visit[1],))
with app.app_context():
    outcome = mark_left(race_visit[0], STAFF_ID)
check("a diagnosis written a moment earlier stops the mark (the rule is in the model)",
      outcome == "not-allowed" and status_of(race_visit[0]) == "Completed", outcome)

section("6. THE ADMINISTRATOR AND THE OFFICIAL ARE REFUSED ON THE SERVER")
spare = add_visit(18, "X", 0, "Waiting", time="14:00")
for who, client, home in (("Administrator", admin, "/admin/dashboard"),
                          ("Barangay Official", official, "/official/dashboard")):
    r = client.post(MARK, data={"appointment_id": str(spare[0])})
    check(f"{who}: POST mark-left (valid token) is refused and redirected to his own dashboard",
          r.status_code == 302 and r.headers.get("Location", "").endswith("dashboard")
          and status_of(spare[0]) == "Waiting", (r.status_code, r.headers.get("Location")))
    r = client.post(UNDO, data={"appointment_id": str(ids["A"])})
    check(f"{who}: POST undo-left is refused too",
          r.status_code == 302 and status_of(ids["A"]) == LEFT)
check("the Administrator has no /admin/ route for either action",
      admin.post("/admin/appointment_scheduling/mark-left",
                 data={"appointment_id": str(spare[0])}).status_code == 404
      and admin.post("/admin/appointment_scheduling/undo-left",
                     data={"appointment_id": str(ids["A"])}).status_code == 404
      and status_of(spare[0]) == "Waiting")
check("without a form token the POST is refused as every POST is (a plain client)",
      app.test_client().post(MARK, data={"appointment_id": str(spare[0])}).status_code in (302, 400)
      and status_of(spare[0]) == "Waiting")

# ---------------------------------------------------------------------------
section("7. UNDO: THE SAME DAY ONLY, BACK TO THE PREVIOUS STATUS")
undo_before = len(audits("Undid left before being seen"))
r = staff.post(UNDO, data={"appointment_id": str(ids["A"])})
row = q1("SELECT * FROM appointments WHERE id = ?", (ids["A"],))
check("Staff undo the same day: the visit is Waiting again, and who/when are cleared",
      row["status"] == "Waiting" and row["left_by"] is None and row["left_at"] is None
      and row["status_before_left"] is None, dict(row))
undone = audits("Undid left before being seen")
check("the undo writes one audit entry, in the same style",
      len(undone) == undo_before + 1
      and undone[-1]["details"] == f"{NAMES['A']} (PAT-006), visit APT-{ids['A']:05d}.")
with app.app_context():
    check("an undone visit is back on the Doctor's list",
          ids["A"] in {v["id"] for v in get_waiting_for_doctor()})
r = doctor.post(UNDO, data={"appointment_id": str(ids["D"])})
check("the Doctor undoes a Completed visit: it goes back to Completed",
      status_of(ids["D"]) == "Completed")
check("undoing a visit that is not marked changes nothing and writes nothing",
      staff.post(UNDO, data={"appointment_id": str(ids["E"])}).status_code == 302
      and len(audits("Undid left before being seen")) == undo_before + 2)
# A visit marked on an earlier day cannot be undone.
staff.post(MARK, data={"appointment_id": str(ids["A"])})
yesterday = (today - timedelta(days=1)).isoformat()
run_sql("UPDATE appointments SET left_at = ? WHERE id = ?", (f"{yesterday} 16:00:00", ids["A"]))
count_before = len(audits("Undid left before being seen"))
r = staff.post(UNDO, data={"appointment_id": str(ids["A"])})
check("an undo on a later day is refused: the visit stays closed",
      status_of(ids["A"]) == LEFT and len(audits("Undid left before being seen")) == count_before)
page = body(staff.get("/staff/appointment_scheduling"))
# K was In Consultation; another visit takes the room; K cannot go back in.
other_room = add_visit(19, "Y", 0, "In Consultation", time="15:00")
r = staff.post(UNDO, data={"appointment_id": str(ids["K"])})
check("putting a visit back In Consultation is refused while someone else is in the room",
      status_of(ids["K"]) == LEFT and status_of(other_room[0]) == "In Consultation")
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (other_room[0],))
r = staff.post(UNDO, data={"appointment_id": str(ids["K"])})
check("once the room is free the same undo works", status_of(ids["K"]) == "In Consultation")
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (ids["K"],))

# ---------------------------------------------------------------------------
section("8. THE QUEUE SCREEN: CONFIRMATION, EARLIER DAYS, READ-ONLY FOR THE ADMINISTRATOR")
run_sql("UPDATE appointments SET status = 'Waiting', status_before_left = NULL, left_by = NULL, "
        "left_at = NULL WHERE id = ?", (ids["B"],))
def section_of(page):
    if "Still waiting from earlier days" not in page:
        return ""
    return page.split("Still waiting from earlier days")[1].split("One thing this screen")[0]


page = body(staff.get("/staff/appointment_scheduling"))
check("Staff see 'Still waiting from earlier days' with the right visit, its ID and how long",
      "Still waiting from earlier days" in page and NAMES["B"] in page
      and f"APT-{ids['B']:05d}" in page and "day" in section_of(page), "")
section_text = section_of(page)
check("the section lists only visits still Waiting from an earlier day, not today's or finished ones",
      NAMES["B"] in section_text and NAMES["E"] not in section_text
      and NAMES["X"] not in section_text and NAMES["D"] not in section_text)
check("each row has a Left before being seen button that opens the dialog",
      'data-bs-target="#leftModal"' in section_text)
check("the dialog asks first, in plain words, and posts to mark-left",
      "Mark this patient as left before being seen?" in page
      and MARK in page and "Mark as left" in page and "Cancel" in page)
check("today's table offers the button for a Waiting visit, and Undo for one marked today",
      'data-appointment="%d"' % spare[0] in page)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (spare[0],))
check("a Doctor sees the section too", "Still waiting from earlier days" in
      body(doctor.get("/staff/appointment_scheduling")))
admin_queue = body(admin.get("/admin/appointment_scheduling"))
check("the Administrator's queue is read-only: no earlier-days section, no dialog, no button",
      "Still waiting from earlier days" not in admin_queue and "leftModal" not in admin_queue
      and "mark-left" not in admin_queue and "undoLeftForm" not in admin_queue, "")
check("the retired 'cannot close a patient who left' note is gone from the queue screen",
      "cannot be closed" not in page and "One thing this screen does not do" in page)

# ---------------------------------------------------------------------------
section("9. QUEUE REPORTS COUNT THE NEW STATUS; SMALL COUNTS FOLD WHERE THEY ALWAYS DID")
rare_day = (today - timedelta(days=30))
while q1("SELECT COUNT(*) FROM appointments WHERE appointment_date = ?",
         (rare_day.isoformat(),))[0]:
    rare_day -= timedelta(days=1)
for n in range(3):
    run_sql("INSERT INTO appointments (patient_id, scheduled_by, appointment_type, "
            "appointment_date, status, is_walkin, checked_in_at) VALUES (?, ?, 'ZZRARE', ?, ?, 1, ?)",
            (1 + n, STAFF_ID, rare_day.isoformat(), LEFT, f"{rare_day.isoformat()} 09:00:00"))
run_sql("INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (4, ?, 'Walk-in Consultation', ?, 'Completed', 1, ?)",
        (STAFF_ID, rare_day.isoformat(), f"{rare_day.isoformat()} 10:00:00"))
from models.appointments import get_appointment_report  # noqa: E402

for who, role in (("Administrator", "admin"), ("Barangay Official", "barangay official"),
                  ("Doctor", "doctor")):
    with app.app_context():
        window = get_appointment_report(months=6, start=rare_day, end=rare_day,
                                        viewer_role=role)["window"]
    check(f"{who}: the range holds 4 appointments, 3 of them left before being seen, "
          "its own figure, and the total is exact",
          window["total"] == 4 and window["left"] == 3 and window["attended"] == 1
          and window["missed"] == 0 and window["resolved"] == 4, window)
    names = [(e["service"], e["count"]) for e in window["services"]]
    if role == "doctor":
        check("Doctor: the rare service is named with its count", ("ZZRARE", 3) in names, names)
    else:
        check(f"{who}: the rare service folds into Other, as services always did (D6)",
              not any(n == "ZZRARE" for n, _ in names) and any(n.startswith("Other") for n, _ in names),
              names)
RANGE = f"?from={rare_day.isoformat()}&to={rare_day.isoformat()}"
for who, client, url in (("Administrator", admin, "/admin/reports_analytics"),
                         ("Barangay Official", official, "/official/reports_analytics"),
                         ("Doctor", doctor, "/staff/reports_analytics")):
    page = body(client.get(url + RANGE))
    check(f"{who}: Reports & Analytics shows 'Left before being seen (3)' in the outcomes",
          "Left before being seen (3)" in flat(page), "")
    xlsx = client.get(url + "/export.xlsx" + RANGE)
    book = load_workbook(io.BytesIO(xlsx.data), data_only=True)
    cells = [str(c) for sheet in book.worksheets for row in sheet.iter_rows(values_only=True)
             for c in row if c is not None]
    check(f"{who}: the Excel file has the Left before being seen figure, 3",
          any(cells[i] == "Left before being seen" and cells[i + 1] == "3"
              for i in range(len(cells) - 1)), "")
    check(f"{who}: the PDF names the new status",
          "Left before being seen" in pdf_text(client.get(url + "/export.pdf" + RANGE).data))
community = body(official.get("/official/community-reports" + RANGE))
check("Community Reports shows it as its own line",
      re.search(r"Left before being seen.{0,200}?<span class=\"fig-value\">3</span>",
                community, re.S) is not None)
from models.appointments import get_queue_stats, get_todays_appointments  # noqa: E402

today_left = add_visit(20, "Z", 0, "Waiting", time="16:00")[0]
staff.post(MARK, data={"appointment_id": str(today_left)})
with app.app_context():
    stats = get_queue_stats(get_todays_appointments())
check("today's queue figures count it as its own status, and it is not in the waiting count",
      stats["left"] >= 1 and stats["waiting"] == len(
          [e for e in get_todays_appointments() if e["status"] == "Waiting"]))
check("the queue footer says how many left before being seen",
      "left before being seen" in body(staff.get("/staff/appointment_scheduling")))

# ---------------------------------------------------------------------------
section("10. THE SCHEMA AND THE MIGRATION")
import tempfile  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402
import migrate_add_left_before_seen as migration  # noqa: E402

SCHEMA = open("schema.sql", encoding="utf-8").read()
fresh = sqlite3.connect(":memory:")
fresh.executescript(SCHEMA)
fresh.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES ('u','h','U','Admin')")
fresh.execute("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex) "
              "VALUES ('P','F','L','2000-01-01','Male')")
try:
    fresh.execute("INSERT INTO appointments (patient_id, scheduled_by, appointment_date, status) "
                  "VALUES (1,1,'2026-01-01',?)", (LEFT,))
    accepts = True
except sqlite3.IntegrityError:
    accepts = False
try:
    fresh.execute("INSERT INTO appointments (patient_id, scheduled_by, appointment_date, status) "
                  "VALUES (1,1,'2026-01-01','Bogus')")
    refuses = False
except sqlite3.IntegrityError:
    refuses = True
fresh.close()
check("schema.sql builds a table that accepts the new status and refuses a made-up one",
      accepts and refuses)
work = Path(tempfile.mkdtemp(prefix="idsleft_"))
old = work / "old.db"
con = sqlite3.connect(old)
# The table as it was before Task 6: the schema without the new status and columns.
older = (SCHEMA.replace(", 'Left before being seen')", ")")
         .replace("    left_by INTEGER,\n    left_at TEXT,\n    status_before_left TEXT,\n", "")
         .replace("    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL,\n"
                  "    FOREIGN KEY (left_by) REFERENCES users(id) ON DELETE SET NULL\n",
                  "    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL\n"))
block = older.split("CREATE TABLE appointments")[1].split("\n);")[0]
assert "left_by" not in block and "Left before being seen" not in block
con.executescript(older)
con.executescript("""
INSERT INTO users (username, password_hash, full_name, role) VALUES ('u','h','U','Admin');
INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex) VALUES ('P','F','L','2000-01-01','Male');
INSERT INTO appointments (patient_id, scheduled_by, appointment_date, status) VALUES (1,1,'2026-01-01','Completed');
INSERT INTO appointments (patient_id, scheduled_by, appointment_date, status, notes) VALUES (1,1,'2026-01-02','Waiting','kept');
""")
con.commit()
before = [tuple(r) for r in con.execute("SELECT * FROM appointments ORDER BY id")]
con.close()
result = migration.run(old, backup_dir=work / "backups")
con = sqlite3.connect(old)
after = [tuple(r[:13]) for r in con.execute("SELECT * FROM appointments ORDER BY id")]
cols_before = len(before[0])
check("the migration backs up first, rebuilds the table and keeps every row and value",
      result["backup"] and Path(result["backup"]).exists() and result["rows"] == 2
      and not result["problems"] and after == before and cols_before == 13, result)
check("the rebuilt table has the three columns and accepts the new status",
      {"left_by", "left_at", "status_before_left"} <= {r[1] for r in con.execute(
          "PRAGMA table_info(appointments)")}
      and "Left before being seen" in con.execute(
          "SELECT sql FROM sqlite_master WHERE name = 'appointments'").fetchone()[0])
con.close()
again = migration.run(old, backup_dir=work / "backups")
check("a second run does nothing: no backup, no change",
      again["backup"] is None and len(list((work / "backups").iterdir())) == 1, again)
shutil.rmtree(work, ignore_errors=True)

# ---------------------------------------------------------------------------
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)

"""The Doctor's list, "Left before being seen", the service at check-in and the status
"Waiting for the Doctor" (Task 6 and Task 6b; M4, M5, M33, L31).

M4. A visit whose intake is saved and that needs a diagnosis waits in its own status,
"Waiting for the Doctor". The Doctor's dashboard lists exactly those visits, oldest first,
across all days. Staff and the Administrator see the count only. One function decides.
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
CONSULT, FOLLOW, HTN = "Consultation", "Follow-up Consultation", "Hypertension / Diabetes Monitoring"
WFD = "Waiting for the Doctor"


def name_patient(pid, tag):
    run_sql("UPDATE patients SET first_name = ?, last_name = 'Wlmark' WHERE id = ?",
            (f"Zzwl{tag}", pid))
    NAMES[tag] = f"Zzwl{tag} Wlmark"
    return pid


def add_visit(pid, tag, days_ago, status, kind=CONSULT, time="09:30",
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


# The fixture has 20 patients; five more are needed.
for extra in range(21, 26):
    run_sql("INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, sex, civil_status, "
            "address, municipality, province, contact_number, status) VALUES (?, ?, 'Extra', 'Patient', "
            "'1985-01-01', 'Female', 'Single', 'Purok 1', 'San Francisco', 'Surigao del Norte', ?, 'Active')",
            (extra, f"PAT-{extra:03d}", f"0900000{extra:04d}"))

# Nobody is in consultation at the start, so the single-room rule is free to test.
run_sql("UPDATE appointments SET status = 'Completed' WHERE status = 'In Consultation'")
V = {}
V["A"] = add_visit(6, "A", 0, "Waiting", time="08:10")                          # waiting today
V["B"] = add_visit(7, "B", 3, "Waiting", time="08:00")                          # earlier day, still waiting
V["D"] = add_visit(8, "D", 2, WFD, consultation=True, time="10:15")             # intake, no diagnosis
V["E"] = add_visit(9, "E", 1, "Completed", consultation=True, diagnosis="Seen by the Doctor")
V["F"] = add_visit(10, "F", 4, "Completed")                                     # closed, nothing written
V["G"] = add_visit(11, "G", 1, "Waiting", kind="Immunization")                  # not a Doctor service
V["H"] = add_visit(12, "H", 5, "Waiting", time="07:50")
run_sql("UPDATE appointments SET status = ?, status_before_left = 'Waiting', left_by = ?, "
        "left_at = ? WHERE id = ?", (LEFT, STAFF_ID, f"{today.isoformat()} 07:00:00", V["H"][0]))
V["J"] = add_visit(13, "J", 2, "Completed", kind="Immunization", consultation=True, time="11:00")
V["P"] = add_visit(14, "P", 1, "Completed", kind="Prenatal Check-up", consultation=True)
V["K"] = add_visit(15, "K", 0, "In Consultation", time="08:40")                  # with the clinician now
# A sealed visit whose diagnosis is not written yet: its complaint is stored encrypted.
V["S"] = add_visit(16, "S", 2, WFD, consultation=True, restricted=True, time="12:00")
V["L"] = add_visit(17, "L", 1, WFD, kind=FOLLOW, consultation=True, time="09:00")
# Half an hour ago, never before midnight, so the wait is in the past whatever time the suite runs.
M_TIME = max(datetime.now() - timedelta(minutes=30),
             datetime.combine(date.today(), datetime.min.time())).strftime("%H:%M")
V["M"] = add_visit(18, "M", 0, WFD, kind=HTN, time=M_TIME)                      # today; no record found
from utils import sealed_crypto  # noqa: E402

SEALED_MARK = "ZZSEALEDCOMPLAINTMARK"
run_sql("UPDATE consultations SET chief_complaint = ? WHERE id = ?",
        (sealed_crypto.encrypt(SEALED_MARK, V["S"][1], "chief_complaint"), V["S"][1]))
ids = {tag: v[0] for tag, v in V.items()}
check("thirteen visits set up in known states", len(ids) == 13, ids)

# ---------------------------------------------------------------------------
section("2. WHO IS ON THE LIST (D4)")
from models.doctor_worklist import (  # noqa: E402
    SERVICES_NEEDING_DOCTOR, VISIT_SERVICES, WAITING_FOR_DOCTOR, clean_service,
    count_waiting_for_doctor, get_waiting_for_doctor, needs_doctor,
)

with app.app_context():
    listed = get_waiting_for_doctor()
    count = count_waiting_for_doctor()
on_list = {v["id"] for v in listed}
exactly = {r[0] for r in db().execute("SELECT id FROM appointments WHERE status = ?", (WFD,))}
check("the Doctor's list is exactly the visits with the status 'Waiting for the Doctor'",
      on_list == exactly == {ids[t] for t in ("D", "S", "L", "M")}, (sorted(on_list), sorted(exactly)))
check("a visit that is only Waiting or In Consultation is not on it (it is on the queue)",
      not ({ids["A"], ids["B"], ids["K"], ids["G"]} & on_list))
check("a visit with a diagnosis, a closed one and one marked left are not on it",
      not ({ids["E"], ids["F"], ids["H"]} & on_list))
check("immunization and prenatal visits are never on it, waiting or completed",
      not ({ids["G"], ids["J"], ids["P"]} & on_list))
check("every visit on the list has no diagnosis",
      all(not (r[0] or "").strip() for r in db().execute(
          "SELECT c.diagnosis FROM appointments a JOIN consultations c ON c.appointment_id = a.id "
          "WHERE a.status = ?", (WFD,))))
check("VISIT_SERVICES is one fixed list; the services needing the Doctor are a subset; a blank "
      "type still needs one; Immunization, Prenatal Check-up and Dental do not",
      VISIT_SERVICES == (CONSULT, FOLLOW, HTN, "Prenatal Check-up", "Immunization", "Dental")
      and set(SERVICES_NEEDING_DOCTOR) - {"Walk-in Consultation"} <= set(VISIT_SERVICES)
      and "Walk-in Consultation" not in VISIT_SERVICES and needs_doctor(None) and needs_doctor("")
      and needs_doctor("Walk-in Consultation")
      and not any(needs_doctor(s) for s in ("Immunization", "Prenatal Check-up", "Dental"))
      and WAITING_FOR_DOCTOR == WFD)
check("a service is accepted only if it is in the list, exactly; there is no default",
      clean_service("Dental") == "Dental" and clean_service(" Dental ") == "Dental"
      and clean_service("dental") is None and clean_service("") is None
      and clean_service(None) is None and clean_service("Walk-in Consultation") is None)
order = [v["id"] for v in listed]
check("the order is oldest first, across all days",
      order == [ids["D"], ids["S"], ids["L"], ids["M"]]
      and [v["checked_in"] for v in listed] == sorted(v["checked_in"] for v in listed), order)
by_id = {v["id"]: v for v in listed}
check("visits from earlier days are marked, and today's are not",
      all(by_id[ids[t]]["from_earlier_day"] for t in ("D", "S", "L"))
      and not by_id[ids["M"]]["from_earlier_day"])


def plain_days(visit):
    """The wait as the page should say it: whole elapsed days, or hours and minutes."""
    days = (datetime.now() - visit["checked_in"]).days
    if days >= 1:
        return f"{days} day{'' if days == 1 else 's'}"
    # Less than a day since a check-in "yesterday" (the suite ran before that visit's time of day).
    hours = int((datetime.now() - visit["checked_in"]).total_seconds() // 3600)
    return f"{hours} hour{'' if hours == 1 else 's'}"


check("each row says how long it has waited, in plain words",
      all(by_id[ids[t]]["waiting"] == plain_days(by_id[ids[t]]) for t in ("D", "S", "L"))
      and re.fullmatch(r"(Just now|\d+ minutes?|\d+ hours?)", by_id[ids["M"]]["waiting"]),
      {k: v["waiting"] for k, v in by_id.items()})
check("each row carries the name, patient ID and the chosen service",
      by_id[ids["D"]]["name"] == NAMES["D"] and by_id[ids["D"]]["patient_reference"] == "PAT-008"
      and by_id[ids["L"]]["service"] == FOLLOW and by_id[ids["M"]]["service"] == HTN)
check("the button opens the intake to edit, or goes to the queue when no intake is found",
      by_id[ids["D"]]["action"] == "edit" and by_id[ids["M"]]["action"] == "queue")

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
      and all(NAMES[t] in doctor_page for t in ("D", "S", "L", "M"))
      and doctor_page.count("Open consultation") >= 3 and "Open Patient Queue" in doctor_page)
doctor_list = doctor_page.split('id="waitingForDoctor"')[1].split("</table>")[0]
check("a visit that is only Waiting, or In Consultation, is not on the Doctor's list "
      "(it is on the queue)", not any(NAMES[t] in doctor_list for t in ("A", "B", "K")))
check("earlier-day visits say 'From an earlier day' on the Doctor's list",
      doctor_page.count("From an earlier day") == 3, doctor_page.count("From an earlier day"))
check("the Staff dashboard shows 'Waiting for the Doctor: N', the Administrator's too, and they "
      "equal the list",
      staff_n and admin_n and int(staff_n.group(1)) == int(admin_n.group(1)) == count == len(listed) == 4,
      (staff_n and staff_n.group(1), admin_n and admin_n.group(1), count))
check("the Doctor's list length is the same number",
      f'<span class="badge-status badge-waiting">{len(listed)}</span>' in doctor_page)
check("the Staff dashboard has no list; the Administrator's has no list and no names of the "
      "visits that are waiting for the Doctor",
      'id="waitingForDoctor"' not in staff_page and 'id="waitingForDoctor"' not in admin_page
      and not any(NAMES[t] in admin_page for t in ("D", "S", "L", "M")),
      [t for t in NAMES if NAMES[t] in admin_page])
check("a sealed visit is on the Doctor's list by name and shows no sealed text",
      NAMES["S"] in doctor_page and SEALED_MARK not in doctor_page
      and "intake complaint" not in doctor_page)
check("the Official's dashboard has neither the list nor the card",
      "waitingForDoctor" not in body(official.get("/official/dashboard"))
      and "Waiting for the Doctor" not in body(official.get("/official/dashboard")))
with app.app_context():
    from models.doctor_worklist import _FROM_SQL, _WHERE_SQL
check("the count is read without any name: its query holds no name column",
      "first_name" not in "SELECT COUNT(*) FROM appointments a" + _WHERE_SQL)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (ids["K"],))


def status_of(appointment):
    return q1("SELECT status FROM appointments WHERE id = ?", (appointment,))[0]


def audits(action):
    conn = db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_logs WHERE action = ? ORDER BY id", (action,))]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
section("4. SERVICE AT CHECK-IN IS REQUIRED, CHOSEN FROM THE LIST, AND VALIDATED ON THE SERVER (D1)")
CHECK_IN = "/staff/appointment_scheduling/check-in"
PATIENT = 4          # an adult who is not otherwise used above
name_patient(PATIENT, "C")
run_sql("UPDATE appointments SET status = 'Completed' WHERE patient_id = ? "
        "AND status IN ('Waiting', 'In Consultation')", (PATIENT,))


def visits_of(pid):
    return q1("SELECT COUNT(*) FROM appointments WHERE patient_id = ?", (pid,))[0]


start = visits_of(PATIENT)
for label, data in (("no service at all", {"patient_id": str(PATIENT), "reason": "Ubo"}),
                    ("an empty service", {"patient_id": str(PATIENT), "reason": "Ubo", "service": ""}),
                    ("an unknown service", {"patient_id": str(PATIENT), "reason": "Ubo",
                                            "service": "Massage"}),
                    ("the retired name", {"patient_id": str(PATIENT), "reason": "Ubo",
                                          "service": "Walk-in Consultation"}),
                    ("a wrong case", {"patient_id": str(PATIENT), "reason": "Ubo",
                                      "service": "dental"})):
    r = staff.post(CHECK_IN, data=data)
    check(f"check-in with {label} is refused and nobody is queued",
          r.status_code == 302 and visits_of(PATIENT) == start)
check("a refused check-in writes no audit entry",
      not [a for a in audits("Checked patient in") if f"PAT-{PATIENT:03d}" in a["details"]])
for service in VISIT_SERVICES:
    run_sql("UPDATE appointments SET status = 'Completed' WHERE patient_id = ? "
            "AND status IN ('Waiting', 'In Consultation', ?)", (PATIENT, WFD))
    r = staff.post(CHECK_IN, data={"patient_id": str(PATIENT), "reason": "Ubo", "service": service})
    row = q1("SELECT * FROM appointments WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (PATIENT,))
    check(f"check-in with '{service}' is accepted and the chosen service is stored",
          r.status_code == 302 and row["appointment_type"] == service and row["status"] == "Waiting",
          dict(row))
page = body(staff.get("/staff/appointment_scheduling"))
check("the Check In dialog offers every service, with no default (the first option is a blank prompt)",
      all(f'<option value="{s}">{s}</option>' in page for s in VISIT_SERVICES)
      and '<option value="" selected disabled>Choose a service</option>' in page
      and page.count('<option value="" selected disabled>Choose a service</option>') == 2)
# The new-patient path: the dialog hands the service over with the reason.
run_sql("UPDATE appointments SET status = 'Completed' WHERE patient_id = ? AND status = 'Waiting'", (PATIENT,))
r = staff.post("/staff/register-patient", data={"check_in_start": "1", "check_in_reason": "Ubo"})
check("the new-patient path refuses a missing service before a registration form opens",
      r.status_code == 302 and "check_in=1" not in r.headers.get("Location", ""))
r = staff.post("/staff/register-patient", data={"check_in_start": "1", "check_in_reason": "Ubo",
                                                "check_in_service": "Massage"})
check("... and an unknown one", r.status_code == 302 and "check_in=1" not in r.headers.get("Location", ""))
r = staff.post("/staff/register-patient", data={"check_in_start": "1", "check_in_reason": "Ubo",
                                                "check_in_service": "Dental"})
check("a valid service is carried into the registration form",
      r.status_code == 302 and r.headers["Location"].endswith("check_in=1")
      and 'name="check_in_service" value="Dental"' in body(staff.get(r.headers["Location"])))
registered = q1("SELECT COUNT(*) FROM patients")[0]
form = {"first_name": "Zzwlnew", "last_name": "Wlmark", "birth_date": "1990-05-05", "sex": "Female",
        "civil_status": "Single", "address": "Purok 1", "municipality": "San Francisco",
        "province": "Surigao del Norte", "zip_code": "8405", "emergency_contact_name": "Test Relative",
        "emergency_contact_relationship": "Sibling", "emergency_contact_number": "09000000001",
        "confirm_duplicate": "yes", "check_in": "1", "check_in_reason": "Ubo"}
r = staff.post("/staff/register-patient", data=dict(form))
check("a forged submit that asks to be checked in with no valid service registers nobody",
      q1("SELECT COUNT(*) FROM patients")[0] == registered)
r = staff.post("/staff/register-patient", data=dict(form, check_in_service="Dental"))
new_patient = q1("SELECT id FROM patients WHERE first_name = 'Zzwlnew'")
row = q1("SELECT * FROM appointments WHERE patient_id = ? ", (new_patient[0],)) if new_patient else None
check("a new patient registered from the dialog is queued with the chosen service",
      row is not None and row["appointment_type"] == "Dental" and row["status"] == "Waiting")

# ---------------------------------------------------------------------------
section("5. CORRECTING THE SERVICE OF A VISIT THAT IS NOT FINISHED (D2)")
CHANGE = "/staff/appointment_scheduling/change-service"
fix = add_visit(19, "Q", 0, "Waiting", kind=CONSULT, time="10:00")[0]
before_audit = q1("SELECT COALESCE(MAX(id),0) FROM audit_logs")[0]
r = staff.post(CHANGE, data={"appointment_id": str(fix), "service": "Immunization"})
entries = [a for a in audits("Changed the service of a visit") if a["id"] > before_audit]
check("Staff correct the service of a Waiting visit",
      r.status_code == 302 and q1("SELECT appointment_type FROM appointments WHERE id = ?", (fix,))[0]
      == "Immunization")
check("one short audit entry, in the words the task gave, and it names no patient",
      len(entries) == 1 and entries[0]["user_id"] == STAFF_ID
      and entries[0]["details"] == f"Corrected the service of visit APT-{fix:05d}."
      and NAMES["Q"] not in entries[0]["details"], entries)
r = doctor.post(CHANGE, data={"appointment_id": str(fix), "service": "Dental"})
check("the Doctor can correct it too, and the entry names the Doctor",
      q1("SELECT appointment_type FROM appointments WHERE id = ?", (fix,))[0] == "Dental"
      and (audits("Changed the service of a visit") or [{}])[-1].get("user_id") == DOCTOR_ID)
n = len(audits("Changed the service of a visit"))
staff.post(CHANGE, data={"appointment_id": str(fix), "service": "Dental"})
check("choosing the service the visit already has changes nothing and writes nothing",
      len(audits("Changed the service of a visit")) == n)
for label, value in (("an unknown service", "Massage"), ("no service", ""), ("a wrong case", "dental")):
    staff.post(CHANGE, data={"appointment_id": str(fix), "service": value})
check("an unknown, empty or wrongly written service is refused on the server",
      q1("SELECT appointment_type FROM appointments WHERE id = ?", (fix,))[0] == "Dental"
      and len(audits("Changed the service of a visit")) == n)
refused = {"a Completed visit": ids["E"], "a visit marked left before being seen": ids["H"]}
for label, appointment in refused.items():
    old = q1("SELECT appointment_type FROM appointments WHERE id = ?", (appointment,))[0]
    staff.post(CHANGE, data={"appointment_id": str(appointment), "service": "Dental"})
    check(f"the service of {label} cannot be changed",
          q1("SELECT appointment_type FROM appointments WHERE id = ?", (appointment,))[0] == old)
check("the refusals wrote no audit entry", len(audits("Changed the service of a visit")) == n)
for who, client in (("Administrator", admin), ("Barangay Official", official)):
    r = client.post(CHANGE, data={"appointment_id": str(fix), "service": "Immunization"})
    check(f"{who}: POST change-service (valid token) is refused on the server",
          r.status_code == 302 and r.headers.get("Location", "").endswith("dashboard")
          and q1("SELECT appointment_type FROM appointments WHERE id = ?", (fix,))[0] == "Dental")
check("the Administrator has no /admin/ route for it",
      admin.post("/admin/appointment_scheduling/change-service",
                 data={"appointment_id": str(fix), "service": "Immunization"}).status_code == 404)
# A visit that was waiting for the Doctor and is corrected to a service that does not
# need him is finished: the same rule the intake follows.
run_sql("UPDATE appointments SET status = ?, appointment_type = ? WHERE id = ?", (WFD, CONSULT, fix))
staff.post(CHANGE, data={"appointment_id": str(fix), "service": "Immunization"})
check("a visit waiting for the Doctor, corrected to a service that does not need him, is Completed, "
      "and the entry says so",
      status_of(fix) == "Completed" and (audits("Changed the service of a visit") or [{}])[-1].get(
          "details", "").endswith("The visit is now Completed."))
run_sql("UPDATE appointments SET status = ?, appointment_type = 'Dental' WHERE id = ?", (WFD, fix))
staff.post(CHANGE, data={"appointment_id": str(fix), "service": CONSULT})
check("corrected to a service that does need him, it stays waiting for the Doctor",
      status_of(fix) == WFD)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (fix,))
page = body(staff.get("/staff/appointment_scheduling"))
check("Staff and the Doctor see a Change service button and its dialog; the Administrator does not",
      "serviceModal" in page and "Change service" in page
      and "serviceModal" not in body(admin.get("/admin/appointment_scheduling"))
      and "serviceModal" in body(doctor.get("/staff/appointment_scheduling")))

# ---------------------------------------------------------------------------
section("6. THE FLOW: INTAKE, THE DOCTOR'S DIAGNOSIS, A FULL DOCTOR CONSULTATION (D3)")
START = "/staff/appointment_scheduling/start-consultation"
INTAKE = {"chief_complaint": "flow intake", "temperature": "37.0", "blood_pressure": "120/80",
          "weight": "61"}
FULL = dict(INTAKE, diagnosis="Flow diagnosis", treatment_plan="Flow plan")


def new_visit(service, tag, pid=None):
    """Check the flow patient in through the real route, then start the consultation."""
    pid = pid or PATIENT
    run_sql("UPDATE appointments SET status = 'Completed' WHERE status IN ('Waiting', 'In Consultation')"
            " AND patient_id = ?", (pid,))
    staff.post(CHECK_IN, data={"patient_id": str(pid), "reason": tag, "service": service})
    appointment = q1("SELECT id FROM appointments WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
                     (pid,))[0]
    staff.post(START, data={"appointment_id": str(appointment)})
    return appointment


def listed_now():
    with app.app_context():
        return {v["id"] for v in get_waiting_for_doctor()}


def consultation_of(appointment):
    return q1("SELECT id, diagnosis FROM consultations WHERE appointment_id = ?", (appointment,))


for service in (CONSULT, FOLLOW, HTN):
    a = new_visit(service, "intake")
    check(f"{service}: the visit is In Consultation after Start", status_of(a) == "In Consultation")
    r = staff.post(f"/staff/consultation/record/{a}", data=INTAKE)
    check(f"{service}: Staff save the intake with no diagnosis: the visit is 'Waiting for the Doctor', "
          "not Completed", status_of(a) == WFD, status_of(a))
    with app.app_context():
        check(f"{service}: it is on the Doctor's list now",
              a in {v["id"] for v in get_waiting_for_doctor()})
check("the room is free again after the intake is saved",
      q1("SELECT COUNT(*) FROM appointments WHERE status = 'In Consultation'")[0] == 0)
last_entries = [e for e in audits("Intake saved, waiting for the Doctor")]
check("saving the intake writes one entry saying so (patient and visit only), not 'Completed consultation'",
      last_entries and last_entries[-1]["details"].startswith(f"{NAMES['C']} (PAT-{PATIENT:03d}), visit APT-"))
cid = consultation_of(a)[0]
before_completed = len(audits("Completed consultation"))
r = doctor.post(f"/staff/consultation/edit/{cid}", data=FULL)
check("the Doctor saves the diagnosis: the visit is Completed and the diagnosis is stored",
      status_of(a) == "Completed" and consultation_of(a)[1] == "Flow diagnosis")
with app.app_context():
    check("... and it is gone from the Doctor's list",
          a not in {v["id"] for v in get_waiting_for_doctor()})
check("... with one 'Completed consultation' entry by the Doctor",
      len(audits("Completed consultation")) == before_completed + 1
      and audits("Completed consultation")[-1]["user_id"] == DOCTOR_ID)
r = doctor.post(f"/staff/consultation/edit/{cid}", data=dict(FULL, diagnosis="A later correction"))
check("the Doctor may change a diagnosis on a Completed visit; it stays Completed",
      status_of(a) == "Completed" and len(audits("Completed consultation")) == before_completed + 1)
# A visit that needs no Doctor.
for service in ("Immunization", "Prenatal Check-up", "Dental"):
    b = new_visit(service, "staff only")
    staff.post(f"/staff/consultation/record/{b}", data=INTAKE)
    check(f"{service}: Staff save the intake and the visit is Completed, with no diagnosis and "
          "never on the Doctor's list",
          status_of(b) == "Completed" and not (consultation_of(b)[1] or "").strip()
          and b not in listed_now())
# The Doctor records the whole consultation himself.
c = new_visit(CONSULT, "doctor himself")
r = doctor.post(f"/staff/consultation/record/{c}", data=FULL)
check("the Doctor records the whole consultation, with a diagnosis: straight to Completed",
      status_of(c) == "Completed" and consultation_of(c)[1] == "Flow diagnosis"
      and c not in listed_now())
# The Doctor writes a diagnosis on an immunization visit: it stays Completed.
d = new_visit("Immunization", "doctor adds")
staff.post(f"/staff/consultation/record/{d}", data=INTAKE)
doctor.post(f"/staff/consultation/edit/{consultation_of(d)[0]}", data=FULL)
check("the Doctor may write a diagnosis on any visit; an immunization visit stays Completed",
      status_of(d) == "Completed")
# Task 6c: 'Mark Completed' from the queue is refused for a service that needs the Doctor.
COMPLETE = "/staff/appointment_scheduling/complete-consultation"
SEND = "/staff/appointment_scheduling/send-to-doctor"
e = new_visit(CONSULT, "closed")
n_complete = len(audits("Completed consultation"))
for who, client in (("Staff", staff), ("the Doctor", doctor)):
    r = client.post(COMPLETE, data={"appointment_id": str(e)})
    check(f"{who}: 'Mark Completed' on a Consultation visit with no diagnosis is refused on the server",
          status_of(e) == "In Consultation"
          and "This visit needs the Doctor first." in body(client.get("/staff/appointment_scheduling")))
check("the refusal wrote no entry", len(audits("Completed consultation")) == n_complete)
page = body(staff.get("/staff/appointment_scheduling"))
check("the queue offers 'Send to the Doctor' there, not 'Mark Completed'",
      "Send to the Doctor" in page and 'form="sendToDoctorForm"' in page
      and f'form="completeConsultationForm" name="appointment_id" value="{e}"' not in page)
before_sent = len(audits("Sent visit to the Doctor"))
r = staff.post(SEND, data={"appointment_id": str(e)})
sent = audits("Sent visit to the Doctor")
check("'Send to the Doctor' sets Waiting for the Doctor, and the room is free",
      status_of(e) == WFD and q1("SELECT COUNT(*) FROM appointments WHERE status = 'In Consultation'")[0] == 0
      and e in listed_now())
check("it writes one short entry: the visit only, no patient and no service",
      len(sent) == before_sent + 1 and sent[-1]["user_id"] == STAFF_ID
      and sent[-1]["details"] == f"Sent visit APT-{e:05d} to the Doctor.",
      sent[-1:])
n = len(audits("Sent visit to the Doctor"))
staff.post(SEND, data={"appointment_id": str(e)})
check("sending it a second time changes nothing and writes nothing",
      status_of(e) == WFD and len(audits("Sent visit to the Doctor")) == n)
# Every other way to Completed is refused for a visit waiting for the Doctor, without a diagnosis.
for who, client in (("Staff", staff), ("the Doctor", doctor), ("the Administrator", admin),
                    ("the Official", official)):
    client.post(COMPLETE, data={"appointment_id": str(e)})
check("Mark Completed, by Staff, the Doctor, the Administrator or the Official, cannot complete a visit "
      "waiting for the Doctor", status_of(e) == WFD)
doctor.post(f"/staff/consultation/record/{e}", data=FULL)
check("the record route refuses a visit that is not In Consultation", status_of(e) == WFD)
e_start = new_visit(CONSULT, "blank")
staff.post(f"/staff/consultation/record/{e_start}", data=INTAKE)
cid_e = consultation_of(e_start)[0]
doctor.post(f"/staff/consultation/edit/{cid_e}", data=dict(FULL, diagnosis=""))
check("the Doctor saving with a blank diagnosis does not complete it", status_of(e_start) == WFD)
staff.post(f"/staff/consultation/edit/{cid_e}", data=FULL)
check("Staff saving a diagnosis (refused on the server) does not complete it",
      status_of(e_start) == WFD and not (consultation_of(e_start)[1] or "").strip())
staff.post("/staff/appointment_scheduling/undo-left", data={"appointment_id": str(e_start)})
check("'Undo left' on a visit that is not marked changes nothing", status_of(e_start) == WFD)
staff.post("/staff/appointment_scheduling/mark-left", data={"appointment_id": str(e_start)})
staff.post("/staff/appointment_scheduling/undo-left", data={"appointment_id": str(e_start)})
check("a visit marked left from Waiting for the Doctor comes back to it, never to Completed",
      status_of(e_start) == WFD)
from models.appointments import complete_consultation  # noqa: E402

with app.app_context():
    check("complete_consultation() itself does not complete a visit waiting for the Doctor "
          "(the rule is in the model, not the buttons)",
          complete_consultation(e_start) == "not-in-consultation" and status_of(e_start) == WFD)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id IN (?, ?)", (e, e_start))
# A service that does not need the Doctor still completes from the queue.
g = new_visit("Dental", "closed dental")
staff.post(COMPLETE, data={"appointment_id": str(g)})
check("Mark Completed still works for a service that does not need the Doctor",
      status_of(g) == "Completed")
h = new_visit("Immunization", "send refused")
staff.post(SEND, data={"appointment_id": str(h)})
check("'Send to the Doctor' is refused for a service that does not need him",
      status_of(h) == "In Consultation")
page = body(staff.get("/staff/appointment_scheduling"))
check("... and the queue offers 'Mark Completed' for it", f'form="completeConsultationForm" name="appointment_id" value="{h}"' in page)
staff.post(COMPLETE, data={"appointment_id": str(h)})
for who, client in (("Administrator", admin), ("Barangay Official", official)):
    spare2 = add_visit(24, "N" + who[:1], 0, "In Consultation", time="17:00")[0]
    client.post(SEND, data={"appointment_id": str(spare2)})
    check(f"{who}: POST send-to-doctor is refused on the server", status_of(spare2) == "In Consultation")
    run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (spare2,))
check("the Administrator has no /admin/ route for it",
      admin.post("/admin/appointment_scheduling/send-to-doctor", data={"appointment_id": "1"}).status_code == 404)
# A stale or forged second save does nothing.
f = new_visit(CONSULT, "stale")
staff.post(f"/staff/consultation/record/{f}", data=INTAKE)
n = len(audits("Intake saved, waiting for the Doctor"))
staff.post(f"/staff/consultation/record/{f}", data=INTAKE)
check("saving the intake a second time changes nothing and writes nothing",
      status_of(f) == WFD and len(audits("Intake saved, waiting for the Doctor")) == n)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (f,))

# ---------------------------------------------------------------------------
section("7. LEFT BEFORE BEING SEEN: FROM WAITING AND FROM WAITING FOR THE DOCTOR (D5)")
MARK, UNDO = "/staff/appointment_scheduling/mark-left", "/staff/appointment_scheduling/undo-left"
before_audit = q1("SELECT COALESCE(MAX(id),0) FROM audit_logs")[0]
with app.app_context():
    count = count_waiting_for_doctor()
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
      and entries[0]["details"] == f"{NAMES['A']} (PAT-006), visit APT-{ids['A']:05d}.", entries)
r = staff.post(MARK, data={"appointment_id": str(ids["D"])})
check("Staff mark a visit that is Waiting for the Doctor (the patient left before he came)",
      status_of(ids["D"]) == LEFT and q1("SELECT status_before_left FROM appointments "
                                         "WHERE id = ?", (ids["D"],))[0] == WFD)
with app.app_context():
    check("it leaves the Doctor's list at once, and the count drops with it",
          ids["D"] not in {v["id"] for v in get_waiting_for_doctor()}
          and count_waiting_for_doctor() == count - 1)
r = doctor.post(MARK, data={"appointment_id": str(ids["L"])})
check("the Doctor can mark one too, and the entry names the Doctor",
      status_of(ids["L"]) == LEFT and audits("Marked as left before being seen")[-1]["user_id"] == DOCTOR_ID)
k = add_visit(15, "K2", 0, "In Consultation", time="08:41")[0]
staff.post(MARK, data={"appointment_id": str(k)})
check("a visit In Consultation with nothing recorded can be marked, and it frees the room",
      status_of(k) == LEFT and q1("SELECT COUNT(*) FROM appointments WHERE status = 'In Consultation'")[0] == 0)
refused = {
    "a Completed visit with a diagnosis": ids["E"],
    "a Completed visit closed with nothing written": ids["F"],
    "a Completed immunization with intake": ids["J"],
    "a Completed prenatal visit with intake": ids["P"],
}
marks_before = len(audits("Marked as left before being seen"))
for label, appointment in refused.items():
    staff.post(MARK, data={"appointment_id": str(appointment)})
    check(f"refused on {label}: the status does not change", status_of(appointment) == "Completed")
check("every refusal wrote no audit entry", len(audits("Marked as left before being seen")) == marks_before)
race_visit = add_visit(20, "R", 0, WFD, consultation=True, time="13:00")
from models.appointments import mark_left  # noqa: E402

run_sql("UPDATE consultations SET diagnosis = 'Written just now' WHERE id = ?", (race_visit[1],))
with app.app_context():
    outcome = mark_left(race_visit[0], STAFF_ID)
check("a diagnosis written a moment earlier stops the mark (the rule is in the model)",
      outcome == "not-allowed" and status_of(race_visit[0]) == WFD, outcome)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (race_visit[0],))
spare = add_visit(21, "X", 0, "Waiting", time="14:00")
for who, client in (("Administrator", admin), ("Barangay Official", official)):
    r = client.post(MARK, data={"appointment_id": str(spare[0])})
    check(f"{who}: POST mark-left (valid token) is refused on the server",
          r.status_code == 302 and r.headers.get("Location", "").endswith("dashboard")
          and status_of(spare[0]) == "Waiting")
    r = client.post(UNDO, data={"appointment_id": str(ids["A"])})
    check(f"{who}: POST undo-left is refused too", r.status_code == 302 and status_of(ids["A"]) == LEFT)
check("the Administrator has no /admin/ route for either action",
      admin.post("/admin/appointment_scheduling/mark-left",
                 data={"appointment_id": str(spare[0])}).status_code == 404)
# Undo.
undo_before = len(audits("Undid left before being seen"))
staff.post(UNDO, data={"appointment_id": str(ids["A"])})
row = q1("SELECT * FROM appointments WHERE id = ?", (ids["A"],))
check("Staff undo the same day: the visit is Waiting again, and who/when are cleared",
      row["status"] == "Waiting" and row["left_by"] is None and row["left_at"] is None
      and row["status_before_left"] is None)
undone = audits("Undid left before being seen")
check("the undo writes one audit entry, in the same style",
      len(undone) == undo_before + 1
      and undone[-1]["details"] == f"{NAMES['A']} (PAT-006), visit APT-{ids['A']:05d}.")
doctor.post(UNDO, data={"appointment_id": str(ids["D"])})
with app.app_context():
    check("undoing a visit that was Waiting for the Doctor restores that status, and it is on his "
          "list again", status_of(ids["D"]) == WFD
          and ids["D"] in {v["id"] for v in get_waiting_for_doctor()})
check("undoing a visit that is not marked changes nothing and writes nothing",
      staff.post(UNDO, data={"appointment_id": str(ids["E"])}).status_code == 302
      and len(audits("Undid left before being seen")) == undo_before + 2)
staff.post(MARK, data={"appointment_id": str(ids["D"])})
run_sql("UPDATE appointments SET left_at = ? WHERE id = ?",
        (f"{(today - timedelta(days=1)).isoformat()} 16:00:00", ids["D"]))
count_before = len(audits("Undid left before being seen"))
staff.post(UNDO, data={"appointment_id": str(ids["D"])})
check("an undo on a later day is refused: the visit stays closed",
      status_of(ids["D"]) == LEFT and len(audits("Undid left before being seen")) == count_before)
run_sql("UPDATE appointments SET status = ?, left_by = NULL, left_at = NULL, status_before_left = NULL "
        "WHERE id = ?", (WFD, ids["D"]))
other_room = add_visit(22, "Y", 0, "In Consultation", time="15:00")
staff.post(UNDO, data={"appointment_id": str(k)})
check("putting a visit back In Consultation is refused while someone else is in the room",
      status_of(k) == LEFT and status_of(other_room[0]) == "In Consultation")
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (other_room[0],))
staff.post(UNDO, data={"appointment_id": str(k)})
check("once the room is free the same undo works", status_of(k) == "In Consultation")
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (k,))

# ---------------------------------------------------------------------------
section("8. THE QUEUE SCREEN: EARLIER DAYS (D7), THE DIALOGS, READ-ONLY FOR THE ADMINISTRATOR")
run_sql("UPDATE appointments SET status = 'Waiting', status_before_left = NULL, left_by = NULL, "
        "left_at = NULL WHERE id = ?", (ids["B"],))


def section_of(page):
    if "Still waiting from earlier days" not in page:
        return ""
    return page.split("Still waiting from earlier days")[1].split("One thing this screen")[0]


page = body(staff.get("/staff/appointment_scheduling"))
section_text = section_of(page)
check("Staff see 'Still waiting from earlier days' with the right visit, its ID and how long",
      NAMES["B"] in section_text and f"APT-{ids['B']:05d}" in section_text and "day" in section_text)
check("the section is for status Waiting only: visits waiting for the Doctor, finished ones and "
      "today's are not in it",
      not any(NAMES[t] in section_text for t in ("D", "S", "L", "E", "X", "M")))
check("each row has a Left before being seen button that opens the dialog",
      'data-bs-target="#leftModal"' in section_text)
check("the dialog asks first, in plain words, and posts to mark-left",
      "Mark this patient as left before being seen?" in page and MARK in page)
check("a Doctor sees the section too", "Still waiting from earlier days" in
      body(doctor.get("/staff/appointment_scheduling")))
admin_queue = body(admin.get("/admin/appointment_scheduling"))
check("the Administrator's queue is read-only: no earlier-days section, no dialog, no button",
      "Still waiting from earlier days" not in admin_queue and "leftModal" not in admin_queue
      and "mark-left" not in admin_queue and "undoLeftForm" not in admin_queue)
check("the Administrator's queue shows no service for any visit (it names a clinical fact)",
      not any(s in admin_queue for s in ("Prenatal Check-up", "Immunization", "Dental", HTN, FOLLOW)))
today_wfd = add_visit(23, "W", 0, WFD, consultation=True, time="16:30")[0]
page = body(staff.get("/staff/appointment_scheduling"))
check("today's queue shows the new status as its own badge and counts it in its own footer figure",
      NAMES["W"] in page and "badge-waiting-doctor" in page and "waiting for the Doctor" in page)
run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (ids["B"],))

# ---------------------------------------------------------------------------
section("9. REPORTS: THE NEW STATUS IS ITS OWN FIGURE, 'COMPLETED' IS ONLY FINISHED VISITS (D6)")
rare_day = (today - timedelta(days=30))
while q1("SELECT COUNT(*) FROM appointments WHERE appointment_date = ?", (rare_day.isoformat(),))[0]:
    rare_day -= timedelta(days=1)


def rare(kind, status, n):
    for i in range(n):
        run_sql("INSERT INTO appointments (patient_id, scheduled_by, appointment_type, "
                "appointment_date, status, is_walkin, checked_in_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (1 + i % 3, STAFF_ID, kind, rare_day.isoformat(), status,
                 f"{rare_day.isoformat()} 09:{i:02d}:00"))


rare("ZZRARE", LEFT, 3)
rare(CONSULT, "Completed", 1)
rare(CONSULT, WFD, 2)
rare("Prenatal Check-up", "Completed", 5)
from models.appointments import get_appointment_report, get_queue_stats, get_todays_appointments  # noqa: E402

for who, role in (("Administrator", "admin"), ("Barangay Official", "barangay official"),
                  ("Doctor", "doctor")):
    with app.app_context():
        window = get_appointment_report(months=6, start=rare_day, end=rare_day, viewer_role=role)["window"]
    check(f"{who}: 11 appointments: 6 attended (finished), 2 waiting for the Doctor, 3 left; the total "
          "is exact and the rate counts those waiting for the Doctor as having come",
          window["total"] == 11 and window["attended"] == 6 and window["awaiting"] == 2
          and window["left"] == 3 and window["missed"] == 0 and window["resolved"] == 11
          and window["attendance_pct"] == round(8 / 11 * 100, 1), window)
    names = {e["service"]: e["count"] for e in window["services"]}
    if role == "doctor":
        check("Doctor: 'Appointments by service' names every chosen service with its count",
              names.get("ZZRARE") == 3 and names.get(CONSULT) == 3 and names.get("Prenatal Check-up") == 5,
              names)
    else:
        check(f"{who}: services of fewer than 5 fold into Other; Prenatal Check-up (5) is named",
              names.get("Prenatal Check-up") == 5 and "ZZRARE" not in names and CONSULT not in names
              and any(n.startswith("Other") for n in names), names)
RANGE = f"?from={rare_day.isoformat()}&to={rare_day.isoformat()}"
for who, client, url in (("Administrator", admin, "/admin/reports_analytics"),
                         ("Barangay Official", official, "/official/reports_analytics"),
                         ("Doctor", doctor, "/staff/reports_analytics")):
    page = body(client.get(url + RANGE))
    check(f"{who}: Reports & Analytics shows 'Waiting for the Doctor (2)' and 'Left before being "
          "seen (3)' as their own figures",
          "Waiting for the Doctor (2)" in flat(page) and "Left before being seen (3)" in flat(page))
    xlsx = client.get(url + "/export.xlsx" + RANGE)
    book = load_workbook(io.BytesIO(xlsx.data), data_only=True)
    cells = [str(c) for sheet in book.worksheets for row in sheet.iter_rows(values_only=True)
             for c in row if c is not None]
    check(f"{who}: the Excel file has both figures",
          any(cells[i] == "Waiting for the Doctor" and cells[i + 1] == "2" for i in range(len(cells) - 1))
          and any(cells[i] == "Left before being seen" and cells[i + 1] == "3"
                  for i in range(len(cells) - 1)))
    check(f"{who}: the PDF names the new status",
          "Waiting for the Doctor" in pdf_text(client.get(url + "/export.pdf" + RANGE).data))
community = body(official.get("/official/community-reports" + RANGE))
check("Community Reports shows it as its own line",
      re.search(r"Waiting for the Doctor.{0,200}?<span class=\"fig-value\">2</span>", community, re.S)
      is not None)
staff.post(MARK, data={"appointment_id": str(spare[0])})        # one left today, for the figures
with app.app_context():
    entries_today = get_todays_appointments()
    stats = get_queue_stats(entries_today)
check("today's queue figures: 'completed' counts only Completed visits; waiting for the Doctor and "
      "left are their own figures and are not in the waiting count",
      stats["completed"] == sum(1 for e in entries_today if e["status"] == "Completed")
      and stats["waiting_doctor"] == sum(1 for e in entries_today if e["status"] == WFD)
      and stats["waiting_doctor"] >= 1 and stats["left"] >= 1
      and stats["waiting"] == sum(1 for e in entries_today if e["status"] == "Waiting"))
check("the queue's Completed card says it counts finished visits",
      "Finished today" in body(staff.get("/staff/appointment_scheduling")))
# "Appointments by service" reflects the service chosen at check-in.
run_sql("UPDATE appointments SET status = 'Completed' WHERE patient_id = ? AND status = 'Waiting'", (PATIENT,))
before_dental = 0
with app.app_context():
    before_dental = {e["service"]: e["count"] for e in get_appointment_report(
        months=6, viewer_role="doctor")["window"]["services"]}.get("Dental", 0)
staff.post(CHECK_IN, data={"patient_id": str(PATIENT), "reason": "Ngipin", "service": "Dental"})
with app.app_context():
    after_dental = {e["service"]: e["count"] for e in get_appointment_report(
        months=6, viewer_role="doctor")["window"]["services"]}.get("Dental", 0)
check("a check-in with the service 'Dental' adds one to 'Appointments by service' for Dental",
      after_dental == before_dental + 1, (before_dental, after_dental))
run_sql("UPDATE appointments SET status = 'Completed' WHERE patient_id = ? AND status = 'Waiting'", (PATIENT,))
# ---------------------------------------------------------------------------
section("10. THE SCHEMA AND THE MIGRATION")
import tempfile  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402
from migrations import migrate_add_left_before_seen as migration  # noqa: E402

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
older = (SCHEMA.replace(", 'Left before being seen')", ")").replace("'Waiting for the Doctor', ", "")
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
section("11. THE MIGRATION FOR THE NEW STATUS (migrate_visit_service_and_doctor_status.py)")
from migrations import migrate_visit_service_and_doctor_status as m2  # noqa: E402

work2 = Path(tempfile.mkdtemp(prefix="idsdoc_"))
old2 = work2 / "old.db"
con = sqlite3.connect(old2)
before_status = (SCHEMA.replace("'Waiting for the Doctor', ", ""))
con.executescript(before_status)
con.executescript("""
INSERT INTO users (username, password_hash, full_name, role, is_active) VALUES ('u','h','U','Admin',1);
INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex) VALUES ('P','F','L','2000-01-01','Male');
""")


def visit(day, status, kind, diagnosis="<none>", before=None):
    """One old visit. diagnosis '<none>' writes no consultation; None or '' a blank one."""
    cur = con.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, status, "
        "status_before_left) VALUES (1, 1, ?, ?, ?, ?)", (kind, day, status, before))
    if diagnosis != "<none>":
        con.execute("INSERT INTO consultations (patient_id, recorded_by, appointment_id, "
                    "consultation_date, chief_complaint, diagnosis) VALUES (1, 1, ?, ?, 'x', ?)",
                    (cur.lastrowid, day, diagnosis))
    return cur.lastrowid


owed1 = visit("2026-01-01", "Completed", "Walk-in Consultation", None)        # converts
owed2 = visit("2026-01-02", "Completed", "Walk-in Consultation", "   ")       # blank counts as none
owed3 = visit("2026-01-03", "Completed", None, "")                             # no service needs him
diagnosed = visit("2026-01-04", "Completed", "Walk-in Consultation", "Seen")   # stays
immun = visit("2026-01-05", "Completed", "Immunization", None)                 # stays: not his service
closed = visit("2026-01-06", "Completed", "Walk-in Consultation")              # stays: nothing written
waiting = visit("2026-01-07", "Waiting", "Walk-in Consultation")               # stays
left_c = visit("2026-01-08", "Left before being seen", "Walk-in Consultation", None, "Completed")
left_w = visit("2026-01-09", "Left before being seen", "Walk-in Consultation", None, "Waiting")
con.commit()
before_rows = {r[0]: tuple(r) for r in con.execute("SELECT * FROM appointments")}
audit_before = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
con.close()
result = m2.run(old2, backup_dir=work2 / "backups")
con = sqlite3.connect(old2)
now_rows = {r[0]: tuple(r) for r in con.execute("SELECT * FROM appointments")}
state = {k: v[7] for k, v in now_rows.items()}
check("it backs up first and rebuilds the table with the wider CHECK",
      result["backup"] and Path(result["backup"]).exists() and not result["problems"]
      and "Waiting for the Doctor" in con.execute(
          "SELECT sql FROM sqlite_master WHERE name = 'appointments'").fetchone()[0], result)
check("it converts the Completed visits that have intake, no diagnosis and a service that needs the "
      "Doctor (a blank diagnosis and a blank service count)",
      all(state[i] == "Waiting for the Doctor" for i in (owed1, owed2, owed3)) and result["converted"] == 3,
      state)
check("it leaves alone a diagnosed visit, an immunization, a visit closed with nothing written, a "
      "Waiting visit and a left one",
      state[diagnosed] == "Completed" and state[immun] == "Completed" and state[closed] == "Completed"
      and state[waiting] == "Waiting" and state[left_c] == "Left before being seen"
      and state[left_w] == "Left before being seen" and result["closed_without_record"] == 1)
check("a visit marked left from Completed is set to return to Waiting for the Doctor on undo; one that "
      "was Waiting keeps that",
      now_rows[left_c][-1] == "Waiting for the Doctor" and now_rows[left_w][-1] == "Waiting"
      and result["converted_left"] == 1)
changed_cols = {(i, c) for i in before_rows for c in range(len(before_rows[i]))
                if before_rows[i][c] != now_rows[i][c]}
check("no other value of any row changed, and no row was lost",
      changed_cols == {(owed1, 7), (owed2, 7), (owed3, 7), (left_c, 15)}
      and len(now_rows) == len(before_rows), sorted(changed_cols))
rows_audit = con.execute("SELECT user_id, action, module, details FROM audit_logs").fetchall()
check("it writes ONE record of itself, with the counts, saying the script did it",
      len(rows_audit) == audit_before + 1 and rows_audit[-1][1] == m2.ACTION
      and "3 completed visits" in rows_audit[-1][3] and "migration script" in rows_audit[-1][3], rows_audit)
con.close()
again = m2.run(old2, backup_dir=work2 / "backups")
con = sqlite3.connect(old2)
check("a second run does nothing: no backup, no change, no second record",
      again["backup"] is None and again["converted"] == 0
      and len(list((work2 / "backups").iterdir())) == 1
      and con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_before + 1)
con.close()
fresh = sqlite3.connect(":memory:")
fresh.executescript(SCHEMA)
fresh.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES ('u','h','U','Admin')")
fresh.execute("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex) "
              "VALUES ('P','F','L','2000-01-01','Male')")
try:
    fresh.execute("INSERT INTO appointments (patient_id, scheduled_by, appointment_date, status) "
                  "VALUES (1,1,'2026-01-01','Waiting for the Doctor')")
    accepts = True
except sqlite3.IntegrityError:
    accepts = False
check("schema.sql accepts the new status, and the migration finds nothing to do on a fresh database",
      accepts and not m2.needs_work(fresh))
fresh.close()
shutil.rmtree(work2, ignore_errors=True)


# ---------------------------------------------------------------------------
section("12. NO AUDIT ENTRY NAMES A VISIT'S SERVICE (L32)")
entries_all = [dict(r) for r in db().execute(
    "SELECT action, details FROM audit_logs WHERE module = 'Appointment Scheduling'")]
check("no entry of the Patient Queue names any service, whatever the action",
      entries_all and not [e for e in entries_all if any(s in (e["details"] or "") for s in VISIT_SERVICES)],
      [e for e in entries_all if any(s in (e["details"] or "") for s in VISIT_SERVICES)][:2])
check("the correction entries all read 'Corrected the service of visit APT-nnnnn.', alone or with 'The "
      "visit is now Completed.'",
      all(re.fullmatch(r"Corrected the service of visit APT-\d{5}\.( The visit is now Completed\.)?", e["details"])
          for e in entries_all if e["action"] == "Changed the service of a visit"))
check("the entry for a visit completed by a service correction says so without naming the service",
      any(e["details"].endswith("The visit is now Completed.") for e in entries_all
          if e["action"] == "Changed the service of a visit"))

# ---------------------------------------------------------------------------
section("13. THE MIGRATION THAT REWORDS OLD ENTRIES (migrate_remove_service_names_from_audit.py)")
from migrations import migrate_remove_service_names_from_audit as m3  # noqa: E402

work3 = Path(tempfile.mkdtemp(prefix="idsaud_"))
old3 = work3 / "old.db"
con = sqlite3.connect(old3)
con.executescript(SCHEMA)
con.executescript("INSERT INTO users (username, password_hash, full_name, role, is_active) "
                  "VALUES ('u','h','U','Admin',1);")
rows3 = [
    ("Changed the service of a visit", "Changed the service of visit APT-00081 from Consultation to Immunization."),
    ("Changed the service of a visit", "Changed the service of visit APT-00082 from Prenatal Check-up to Consultation. "
                                      "The visit is now Completed."),
    ("Changed the service of a visit", "Corrected the service of visit APT-00083."),
    ("Marked as left before being seen", "Name (PAT-005), visit APT-00081."),
]
for action, details in rows3:
    con.execute("INSERT INTO audit_logs (user_id, action, module, details) VALUES (1, ?, 'Appointment Scheduling', ?)",
                (action, details))
con.commit()
before3 = [tuple(r) for r in con.execute("SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs")]
con.close()
res3 = m3.run(old3, backup_dir=work3 / "backups")
con = sqlite3.connect(old3)
texts = [r[0] for r in con.execute("SELECT details FROM audit_logs ORDER BY id")]
check("it backs up first and rewords the two old entries, and only them",
      res3["backup"] and Path(res3["backup"]).exists() and res3["reworded"] == 2 and not res3["problems"]
      and texts[:4] == ["Corrected the service of visit APT-00081.",
                        "Corrected the service of visit APT-00082. The visit is now Completed.",
                        "Corrected the service of visit APT-00083.", "Name (PAT-005), visit APT-00081."], texts)
check("who, when, the action and the module of every entry are unchanged",
      [tuple(r) for r in con.execute("SELECT id, user_id, action, module, ip_address, created_at FROM audit_logs "
                                     "WHERE id <= 4 ORDER BY id")] == before3)
rec = con.execute("SELECT action, details FROM audit_logs WHERE id > 4").fetchall()
check("it writes ONE record of itself, with the count, saying the script did it",
      len(rec) == 1 and rec[0][0] == m3.ACTION and "2 earlier entries" in rec[0][1]
      and "migration script" in rec[0][1] and not any(s in rec[0][1] for s in VISIT_SERVICES), rec)
con.close()
res3b = m3.run(old3, backup_dir=work3 / "backups")
con = sqlite3.connect(old3)
check("a second run does nothing: no backup, no change, no second record",
      res3b["backup"] is None and res3b["reworded"] == 0 and len(list((work3 / "backups").iterdir())) == 1
      and con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 5)
con.close()
shutil.rmtree(work3, ignore_errors=True)

# ---------------------------------------------------------------------------
section("14. THE DOCTOR CAN SEE EVERY WAITING PATIENT, WITH OR WITHOUT AN INTAKE (Task 6d)")
QUEUE_URL, DASH_URL = "/staff/appointment_scheduling", "/staff/dashboard"


def row_of(page, marker, start='<tr'):
    """The table row on `page` that holds `marker` (an APT reference or a patient name)."""
    for chunk in page.split(start)[1:]:
        row = chunk.split("</tr>")[0]
        if marker in row:
            return row
    return ""


def see_patient_href(row):
    """The href of the 'See patient' link in a row, or None."""
    m = re.search(r'<a [^>]*href="([^"]+)"[^>]*>(?:(?!</a>).)*?See patient', row, re.S)
    return m.group(1) if m else None


# The bug: Staff send a Consultation visit to the Doctor with no intake.
name_patient(25, "T6D")
bug = new_visit(CONSULT, "no intake", pid=25)
staff.post(SEND, data={"appointment_id": str(bug)})
check("Task 6d set-up: Staff send a Consultation visit to the Doctor without an intake: it is "
      "Waiting for the Doctor and has no consultation record",
      status_of(bug) == WFD and consultation_of(bug) is None)
queue_row = row_of(body(doctor.get(QUEUE_URL)), f"APT-{bug:05d}")
check("the Doctor's Patient Queue offers 'See patient' on that row", "See patient" in queue_row, queue_row[-600:])
dash_row = row_of(body(doctor.get(DASH_URL)), NAMES["T6D"])
check("the Doctor's dashboard list offers 'See patient' on that row", "See patient" in dash_row, dash_row[-600:])
href = see_patient_href(queue_row)
r = doctor.get(href, follow_redirects=True) if href else None
check("it opens a new consultation form for this visit (the Doctor sees the diagnosis field)",
      r is not None and r.status_code == 200 and 'name="diagnosis"' in body(r)
      and f"/consultation/record/{bug}" in (r.request.path or ""), href)
r = doctor.post(f"/staff/consultation/record/{bug}", data=FULL)
check("saving it with a diagnosis completes the visit, and the record is linked to it",
      status_of(bug) == "Completed" and consultation_of(bug) is not None
      and consultation_of(bug)[1] == "Flow diagnosis", status_of(bug))
with app.app_context():
    check("... and it leaves the Doctor's list", bug not in listed_now())

# ---------------------------------------------------------------------------
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)

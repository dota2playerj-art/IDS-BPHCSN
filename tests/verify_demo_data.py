"""The fictional demo data follows every rule the system enforces (Task 8).

seed_demo_data.py builds a database from nothing by driving the app's own routes as
each role. This suite builds it twice into the test folder (never app.db) and checks:

* it is deterministic: two builds hold identical content;
* the workflow is the real one: Staff check in and take the intake, only the Doctor
  writes a diagnosis and treatment plan, the Administrator made no clinical write;
* sealed visits are stored encrypted;
* every phone number is 0900000NNNN, and every patient name comes from the
  generator's own invented lists (no real name is stored anywhere in the repo);
* immunization dates follow the DOH EPI schedule;
* the top three diagnoses, complaints and dispensed medicines reach 5 over one month
  and over twelve months, so the Administrator's and the Official's reports show real
  named rows;
* the audit trail holds the workflow actions;
* every role's pages load;
* archive_plain_databases.py archives, verifies, removes, skips what it has done, and
  keeps a plain file when the check fails.

Runs in a temporary folder built by tests/_support.py.
"""
import contextlib
import io
import os
import re
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import _support  # noqa: E402  (first: builds the test folder, points the app at it)

import config  # noqa: E402

sys.stdout.reconfigure(errors="replace")

TEST_DIR = Path(_support.TEST_DIR)
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


import seed_demo_data as seed  # noqa: E402
import archive_plain_databases as archive  # noqa: E402
from utils import sealed_crypto  # noqa: E402

print("=" * 78)
print("IDS-BPHCSN — the fictional demo data (Task 8)")
print("=" * 78)

# ===========================================================================
section("1. BUILD IT TWICE, INTO THE TEST FOLDER")
PATH_A = _support.guard_path(str(TEST_DIR / "demo_a.db"))
PATH_B = _support.guard_path(str(TEST_DIR / "demo_b.db"))
started = time.time()
with contextlib.redirect_stdout(io.StringIO()):
    built_a = seed.build(PATH_A, show_passwords=False)
    built_b = seed.build(PATH_B, show_passwords=False)
print(f"       two builds took {time.time() - started:.0f} s")
check("both builds finished and made a database file",
      Path(PATH_A).exists() and Path(PATH_B).exists())
try:
    seed.build(PATH_A, show_passwords=False)
    refused = False
except SystemExit:
    refused = True
check("building onto an existing file stops with a plain message", refused)

counts = built_a["counts"]
check("about 150 patients and about 400 visits, a handful of sealed visits, ten broadcasts",
      140 <= counts["patients"] <= 160 and 350 <= counts["visits"] <= 450
      and 3 <= counts["sealed visits"] <= 5 and counts["broadcasts"] == 10, counts)
check("immunizations, dispensing, inventory and audit entries are all filled",
      counts["immunizations"] > 100 and counts["dispensing issues"] > 100
      and counts["inventory items"] == 15 and counts["audit entries"] > 1000, counts)


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(path):
    """Every table's rows, with sealed text opened and password hashes left out."""
    conn = connect(path)
    out = {}
    try:
        for (table,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"):
            columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            rows = []
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
                values = []
                for column, value in zip(columns, row):
                    if table == "users" and column == "password_hash":
                        value = ""
                    elif isinstance(value, str) and sealed_crypto.is_encrypted(value):
                        value = sealed_crypto.decrypt(value, row["id"], column, table)
                    values.append(value)
                rows.append(tuple(values))
            out[table] = rows
        return out
    finally:
        conn.close()


section("2. IT IS DETERMINISTIC")
snap_a, snap_b = snapshot(PATH_A), snapshot(PATH_B)
different = [t for t in snap_a if snap_a[t] != snap_b.get(t)]
check("two builds hold identical content in every table (sealed text opened, "
      "password hashes left out)", not different, different)
check("the same row counts, table by table",
      {t: len(r) for t, r in snap_a.items()} == {t: len(r) for t, r in snap_b.items()})
check("the account passwords are random, so they differ between builds",
      built_a["passwords"] != built_b["passwords"])

# ===========================================================================
section("3. THE WORKFLOW IS THE REAL ONE")
db = connect(PATH_A)
users = {r["username"]: r for r in db.execute("SELECT * FROM users")}
by_id = {r["id"]: r for r in users.values()}
check("five accounts: one Administrator, one Doctor, two Staff, one Official",
      sorted(u["role"] for u in users.values())
      == ["Admin", "Barangay Official", "Doctor", "Health Center Staff", "Health Center Staff"])
check("every account must change its password at first sign-in",
      all(u["must_change_password"] == 1 for u in users.values()))
check("account passwords are random and pass the password rule",
      len({p for _, p in built_a["passwords"]}) == 5)
from models.users import check_password_strength  # noqa: E402

check("every generated password meets the strength rule",
      all(check_password_strength(p, u, "") is None for u, p in built_a["passwords"]))
check("the full names of the accounts are the invented ones",
      {u["full_name"] for u in users.values()} == set(seed.ACCOUNT_NAMES))

recorded_by_roles = {r[0] for r in db.execute(
    "SELECT u.role FROM consultations c JOIN users u ON u.id = c.recorded_by")}
check("every intake (the consultation record) was made by Health Center Staff",
      recorded_by_roles == {"Health Center Staff"}, recorded_by_roles)
doctor_id = users["doctor"]["id"]
consultation_ids = [r[0] for r in db.execute("SELECT id FROM consultations")]
diagnosed = set()
for row in db.execute("SELECT user_id, details FROM audit_logs WHERE action = 'Updated consultation record'"):
    match = re.search(r"Consultation #(\d+)", row["details"])
    if match and row["user_id"] == doctor_id and "Diagnosis" in row["details"] \
            and "Treatment plan" in row["details"]:
        diagnosed.add(int(match.group(1)))
# Task 6: a few visits are left waiting for the Doctor on purpose, so the Doctor's list
# has something to show. They have intake by Staff and no diagnosis yet.
undiagnosed = {r[0] for r in db.execute(
    "SELECT id FROM consultations WHERE diagnosis IS NULL OR TRIM(diagnosis) = ''")}
check("every consultation has a diagnosis and treatment plan that the Doctor account wrote, "
      "except the six visits left waiting for the Doctor (which have neither)",
      diagnosed == set(consultation_ids) - undiagnosed and len(undiagnosed) == seed.INTAKE_ONLY_VISITS
      and not (diagnosed & undiagnosed)
      and db.execute("SELECT COUNT(*) FROM consultations WHERE id IN (%s) AND "
                     "(treatment_plan IS NOT NULL AND TRIM(treatment_plan) != '')"
                     % ",".join(map(str, undiagnosed or [0]))).fetchone()[0] == 0,
      (len(diagnosed), len(consultation_ids), len(undiagnosed)))
written_by_others = [r for r in db.execute(
    "SELECT user_id, details FROM audit_logs WHERE action = 'Updated consultation record' "
    "AND user_id != ? AND (details LIKE '%Diagnosis%' OR details LIKE '%Treatment plan%')",
    (doctor_id,))]
check("no other account changed a diagnosis or treatment plan", not written_by_others)
check("no diagnosis was refused: nobody outside the Doctor tried to write one",
      db.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE '%refused%' "
                 "OR action LIKE '%Refused%'").fetchone()[0] == 0)
admin_actions = {r[0] for r in db.execute(
    "SELECT DISTINCT action FROM audit_logs WHERE user_id = ?", (users["admin"]["id"],))}
check("the Administrator made no clinical write: only an inventory item and SMS broadcasts",
      admin_actions <= {"Added inventory item", "Sent community SMS broadcast"}, admin_actions)
official_actions = {r[0] for r in db.execute(
    "SELECT DISTINCT action FROM audit_logs WHERE user_id = ?", (users["official"]["id"],))}
check("the Barangay Official only sent SMS broadcasts",
      official_actions == {"Sent community SMS broadcast"}, official_actions)
check("both the Administrator and the Official sent broadcasts, all simulated",
      db.execute("SELECT COUNT(DISTINCT sent_by) FROM sms_broadcasts").fetchone()[0] == 2
      and db.execute("SELECT COUNT(*) FROM sms_broadcasts WHERE delivery_mode != 'simulated'")
      .fetchone()[0] == 0)
check("every dispensing was done by Health Center Staff",
      {r[0] for r in db.execute("SELECT u.role FROM medicine_dispensing d "
                                "JOIN users u ON u.id = d.dispensed_by")} <= {"Health Center Staff"})
statuses = dict(db.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status").fetchall())
check("nobody is in consultation; eight visits were left before being seen and two are still "
      "waiting from earlier days; every other visit is completed",
      set(statuses) == {"Completed", "Left before being seen", "Waiting"}
      and statuses["Left before being seen"] == seed.LEFT_VISITS
      and statuses["Waiting"] == seed.STALE_WAITING_VISITS
      and statuses["Completed"] == counts["visits"], statuses)
actions = {r[0] for r in db.execute("SELECT DISTINCT action FROM audit_logs")}
wanted = {"Marked as left before being seen", "Registered patient", "Checked patient in", "Started consultation",
          "Recorded consultation", "Updated consultation record", "Completed consultation",
          "Dispensed medicine", "Recorded EPI immunisation doses",
          "Recorded doses given elsewhere", "Marked consultation restricted",
          "Changed patient status", "Declared patient deceased", "Added inventory item",
          "Sent community SMS broadcast"}
check("the audit trail holds an entry for every workflow action", wanted <= actions,
      sorted(wanted - actions))
check("each visit has its check-in, start, record and completion entries (and the eight left "
      "and two waiting visits have a check-in)",
      db.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'Checked patient in'").fetchone()[0]
      == counts["visits"] + seed.LEFT_VISITS + seed.STALE_WAITING_VISITS
      and all(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action = ?", (a,)).fetchone()[0]
              == counts["visits"] for a in ("Started consultation", "Recorded consultation",
                                             "Completed consultation")))
check("audit entries carry dates across the year, not the day it was built",
      db.execute("SELECT COUNT(DISTINCT substr(created_at,1,10)) FROM audit_logs").fetchone()[0] > 150)
today = date.today()
low, high = db.execute("SELECT MIN(substr(consultation_date,1,10)), "
                       "MAX(substr(consultation_date,1,10)) FROM consultations").fetchone()
check("visits cover the last 12 months and none is today or later",
      date.fromisoformat(low) >= today - timedelta(days=365)
      and date.fromisoformat(high) < today
      and (today - date.fromisoformat(low)).days > 330, (low, high))
check("no visit falls on a weekend",
      all(date.fromisoformat(r[0]).weekday() < 5 for r in db.execute(
          "SELECT DISTINCT substr(consultation_date,1,10) FROM consultations")))

# ===========================================================================
section("3b. THE DOCTOR'S LIST AND 'LEFT BEFORE BEING SEEN' SHOW IN THE DEMO (Task 6)")
left_rows = db.execute("SELECT * FROM appointments WHERE status = 'Left before being seen'").fetchall()
staff_ids = {u["id"] for u in users.values() if u["role"] == "Health Center Staff"}
check("the left visits were marked by Staff, on the day they checked in, with the status before",
      len(left_rows) == seed.LEFT_VISITS
      and all(r["left_by"] in staff_ids and r["status_before_left"] == "Waiting"
              and (r["left_at"] or "")[:10] == r["appointment_date"][:10] for r in left_rows))
check("a visit that left has no consultation and was not diagnosed",
      all(db.execute("SELECT COUNT(*) FROM consultations WHERE appointment_id = ?",
                     (r["id"],)).fetchone()[0] == 0 for r in left_rows))
marks = db.execute("SELECT user_id, details FROM audit_logs WHERE action = "
                   "'Marked as left before being seen'").fetchall()
check("each has exactly one audit entry by Staff, in the existing style: Name (PAT-005), "
      "visit APT-00081.",
      len(marks) == seed.LEFT_VISITS and all(m["user_id"] in staff_ids for m in marks)
      and all(re.fullmatch(r".+ \(PAT-\d{3}\), visit APT-\d{5}\.", m["details"]) for m in marks),
      [m["details"] for m in marks][:2])
waiting_rows = db.execute("SELECT * FROM appointments WHERE status = 'Waiting'").fetchall()
check("the still-waiting visits are from earlier days, never started, with no consultation",
      len(waiting_rows) == seed.STALE_WAITING_VISITS
      and all(r["appointment_date"][:10] < date.today().isoformat() for r in waiting_rows)
      and all(db.execute("SELECT COUNT(*) FROM consultations WHERE appointment_id = ?",
                         (r["id"],)).fetchone()[0] == 0 for r in waiting_rows))
check("the intake-only visits are from the last two weeks",
      all(date.fromisoformat(r[0]) >= date.today() - timedelta(days=16) for r in db.execute(
          "SELECT substr(consultation_date,1,10) FROM consultations WHERE diagnosis IS NULL "
          "OR TRIM(diagnosis) = ''")))

# ===========================================================================
section("4. SEALED VISITS ARE ENCRYPTED; PATIENT STATUS; THE SHELF; THE SCHEDULE")
sealed = db.execute("SELECT * FROM consultations WHERE is_restricted = 1").fetchall()
check("three to five visits are sealed, and the Doctor sealed each",
      3 <= len(sealed) <= 5 and all(r["restricted_by"] == doctor_id for r in sealed))
check("every sealed visit's diagnosis, treatment plan and chief complaint are stored encrypted",
      all(sealed_crypto.is_encrypted(r[c]) for r in sealed
          for c in ("diagnosis", "treatment_plan", "chief_complaint")))
check("and their notes, when there are any, and the check-in reason too",
      all((not r["remarks"]) or sealed_crypto.is_encrypted(r["remarks"]) for r in sealed)
      and all(sealed_crypto.is_encrypted(db.execute(
          "SELECT notes FROM appointments WHERE id = ?", (r["appointment_id"],)).fetchone()[0])
          for r in sealed))
check("no unsealed visit holds encrypted text",
      db.execute("SELECT COUNT(*) FROM consultations WHERE is_restricted = 0 AND "
                 "(diagnosis LIKE 'enc:v1:%' OR chief_complaint LIKE 'enc:v1:%')")
      .fetchone()[0] == 0)
check("the sealed text is not in the file as plain text",
      all(seed_text.encode() not in Path(PATH_A).read_bytes()
          for _, seed_text, _ in seed.SEALED_VISITS))
check("exactly one patient is Deceased, declared by the Doctor, and three are Inactive",
      db.execute("SELECT COUNT(*) FROM patients WHERE status = 'Deceased'").fetchone()[0] == 1
      and db.execute("SELECT COUNT(*) FROM patients WHERE status = 'Inactive'").fetchone()[0] == 3
      and db.execute("SELECT user_id FROM audit_logs WHERE action = 'Declared patient deceased'")
      .fetchone()[0] == doctor_id)
late = []
for p_row in db.execute("SELECT id, patient_id FROM patients WHERE status != 'Active'"):
    changed_on = db.execute(
        "SELECT MIN(substr(created_at,1,10)) FROM audit_logs WHERE action IN "
        "('Changed patient status', 'Declared patient deceased') AND details LIKE ?",
        (f"%{p_row['patient_id']}%",)).fetchone()[0]
    last_visit = db.execute("SELECT MAX(substr(consultation_date,1,10)) FROM consultations "
                            "WHERE patient_id = ?", (p_row["id"],)).fetchone()[0]
    if changed_on is None or (last_visit and last_visit > changed_on):
        late.append(p_row["patient_id"])
check("each of the four patients whose status changed has the change on record, and no visit "
      "after it", not late and db.execute(
          "SELECT COUNT(*) FROM patients WHERE status != 'Active'").fetchone()[0] == 4, late)
check("the Service Schedule is empty: it holds the real service days, not invented ones",
      db.execute("SELECT COUNT(*) FROM service_schedule").fetchone()[0] == 0)
items = db.execute("SELECT * FROM inventory_items").fetchall()
check("no item has negative stock, and at least two are at or below their reorder level",
      all(i["stock_quantity"] >= 0 for i in items)
      and sum(1 for i in items if i["stock_quantity"] <= i["low_stock_threshold"]
              and i["category"] == "Medicine") >= 2)
check("the common barangay medicines are on the shelf",
      {"Paracetamol 500mg", "Amoxicillin 500mg", "Oral Rehydration Salts", "Zinc Sulfate 20mg",
       "Cotrimoxazole 400/80mg", "Losartan 50mg", "Amlodipine 5mg", "Metformin 500mg",
       "Ferrous Sulfate + Folic Acid"} <= {i["name"] for i in items})
check("no medicine is expired on the day the data was built",
      all(i["expiry_date"] is None or i["expiry_date"] > today.isoformat() for i in items))

# ===========================================================================
section("5. PEOPLE, NAMES AND PHONE NUMBERS ARE INVENTED")
patients = db.execute("SELECT * FROM patients").fetchall()
firsts = set(seed.MALE_FIRST) | set(seed.FEMALE_FIRST)
check("every patient's first name, middle name and surname come from the generator's lists",
      all(p["first_name"] in firsts and p["last_name"] in seed.SURNAMES
          and p["middle_name"] in seed.SURNAMES for p in patients))
check("every emergency contact name is built from the same lists",
      all(len(p["emergency_contact_name"].split(" ", 1)) == 2
          and p["emergency_contact_name"].split(" ", 1)[0] in firsts
          and p["emergency_contact_name"].split(" ", 1)[1] in seed.SURNAMES for p in patients))
check("every sex matches the first name's list",
      all((p["first_name"] in seed.FEMALE_FIRST) == (p["sex"] == "Female") for p in patients))
check("addresses are Purok 1 to 7, Barangay Poblacion, San Francisco, Surigao del Norte",
      all(re.fullmatch(r"Purok [1-7], Barangay Poblacion", p["address"])
          and p["municipality"] == "San Francisco" and p["province"] == "Surigao del Norte"
          for p in patients))
phone = re.compile(seed.PHONE_PATTERN)
check("every patient and emergency phone number is 0900000NNNN",
      all(phone.match(p["contact_number"]) and phone.match(p["emergency_contact_number"])
          for p in patients))
check("every SMS recipient number is 0900000NNNN too, and no account holds a phone",
      all(phone.match(r[0]) for r in db.execute("SELECT mobile_number FROM sms_broadcast_recipients"))
      and all(u["phone"] is None for u in users.values()))
check("no number outside the 0900000NNNN pattern is stored anywhere in the database file",
      not re.search(rb"(?<!\d)(?:\+?63|0)9(?!0000)\d{9}(?!\d)", Path(PATH_A).read_bytes()))
ages = [(today - date.fromisoformat(p["birth_date"])).days / 365.25 for p in patients]
check("a realistic mix of ages: infants, children, adults and seniors, and both sexes",
      sum(a < 1 for a in ages) >= 8 and sum(1 <= a < 5 for a in ages) >= 12
      and sum(a >= 60 for a in ages) >= 20
      and 40 <= sum(p["sex"] == "Female" for p in patients) <= 110)
check("no patient is registered before they were born",
      all(p["created_at"][:10] >= p["birth_date"] for p in patients))
check("patient IDs are PAT-001 onward, in order",
      [p["patient_id"] for p in patients] == [f"PAT-{i:03d}" for i in range(1, len(patients) + 1)])

# ===========================================================================
section("6. IMMUNIZATIONS FOLLOW THE DOH EPI SCHEDULE")
from models.immunizations import EPI_SCHEDULE, due_date_for  # noqa: E402

offsets = {(code, dose): (value, unit) for code, _n, _p, dose, _t, value, unit, _note in EPI_SCHEDULE}
born = {p["id"]: date.fromisoformat(p["birth_date"]) for p in patients}
doses = db.execute("SELECT * FROM immunizations ORDER BY patient_id, vaccine_code, dose_number").fetchall()
early, before_birth, close, future = [], [], [], []
last_seen = {}
for row in doses:
    key = (row["vaccine_code"], row["dose_number"])
    given = row["date_administered"] and date.fromisoformat(row["date_administered"])
    if given is None:
        continue
    if given < born[row["patient_id"]]:
        before_birth.append(row["id"])
    if given > today:
        future.append(row["id"])
    if row["source"] == "administered" and given < due_date_for(born[row["patient_id"]], *offsets[key]):
        early.append(row["id"])
    previous = last_seen.get((row["patient_id"], row["vaccine_code"]))
    if previous and (given - previous).days < 28:
        close.append(row["id"])
    last_seen[(row["patient_id"], row["vaccine_code"])] = given
check("every dose given here was given on or after the day the schedule says it falls due",
      not early, early[:5])
check("no dose is dated before the child was born, or in the future",
      not before_birth and not future)
check("doses of one vaccine are at least four weeks apart", not close, close[:5])
check("some doses were given here and some were reported as given elsewhere",
      any(r["source"] == "administered" for r in doses) and any(r["source"] == "reported" for r in doses))
check("every dose is a pair the schedule lists",
      all((r["vaccine_code"], r["dose_number"]) in offsets for r in doses))
check("every dose given here is tied to its consultation, on that visit's date",
      all(db.execute("SELECT substr(consultation_date,1,10) FROM consultations WHERE id = ?",
                     (r["consultation_id"],)).fetchone()[0] == r["date_administered"]
          for r in doses if r["source"] == "administered"))

# ===========================================================================
section("7. THE REPORTS SHOW REAL, NAMED ROWS")
config.DATABASE = PATH_A
import app as app_module  # noqa: E402

flask_app = app_module.create_app()
from models.consultations import get_consultation_stats  # noqa: E402
from models.dispensing import get_dispensing_stats  # noqa: E402
from models.immunizations import get_immunization_alert  # noqa: E402
from models.inventory import get_low_stock_alert  # noqa: E402
from models.settings import clear_cache  # noqa: E402
from utils.dates import today as clinic_today  # noqa: E402

clear_cache()
with flask_app.app_context():
    end = clinic_today()
    for label, days in (("one month", 30), ("twelve months", 364)):
        start = end - timedelta(days=days)
        for role in ("doctor", "admin", "barangay official"):
            consult = get_consultation_stats(months=12, limit=60, start=start, end=end,
                                             viewer_role=role)["window"]
            dispense = get_dispensing_stats(months=12, limit=60, start=start, end=end,
                                            viewer_role=role)["window"]
            top_dx = [e for e in consult["top_diagnoses"] if not e.get("other")][:3]
            top_cc = [e for e in consult["top_complaints"] if not e.get("other")][:3]
            top_med = sorted((e for e in dispense["all_medicines"] if not e.get("other")),
                             key=lambda e: -e["events"])[:3]
            who = {"doctor": "Doctor", "admin": "Administrator",
                   "barangay official": "Official"}[role]
            check(f"{who}, {label}: the top three diagnoses each have 5 or more visits, named",
                  len(top_dx) == 3 and all(e["count"] >= 5 for e in top_dx), top_dx)
            check(f"{who}, {label}: the top three complaints each have 5 or more visits, named",
                  len(top_cc) == 3 and all(e["count"] >= 5 for e in top_cc), top_cc)
            check(f"{who}, {label}: the top three dispensed medicines each have 5 or more issues, named",
                  len(top_med) == 3 and all(e["events"] >= 5 for e in top_med), top_med)
    from models.doctor_worklist import count_waiting_for_doctor, get_waiting_for_doctor

    listed = get_waiting_for_doctor()
    check("the Doctor's list holds the six intake-only visits and the two still waiting, oldest "
          "first, and the count agrees",
          len(listed) == seed.INTAKE_ONLY_VISITS + seed.STALE_WAITING_VISITS
          == count_waiting_for_doctor()
          and [v["checked_in"] for v in listed] == sorted(v["checked_in"] for v in listed),
          len(listed))
    check("all of them are from earlier days (the demo ends yesterday)",
          all(v["from_earlier_day"] for v in listed))
    alert = get_immunization_alert(limit=50)
    check("the immunization alert shows children who are due or overdue",
          alert.get("needs_attention_count", alert.get("count", 0)) > 0
          or len(alert.get("children", [])) > 0, {k: v for k, v in alert.items() if k != "children"})
    low_stock = get_low_stock_alert()
    check("the low-stock alert shows items", len(low_stock.get("items", low_stock)) > 0
          if isinstance(low_stock, dict) else len(low_stock) > 0)

# ===========================================================================
section("8. EVERY ROLE'S PAGES LOAD")
conn = sqlite3.connect(PATH_A)
conn.execute("UPDATE users SET must_change_password = 0")
conn.commit()
conn.close()
rules = sorted({r.rule for r in flask_app.url_map.iter_rules()
                if "GET" in r.methods and not r.arguments and not r.rule.startswith("/static")
                and r.rule != "/logout" and not r.rule.endswith(".idsbackup")})
sample_ids = [r[0] for r in db.execute("SELECT id FROM patients ORDER BY id")][::15]
end_day = date.today()
ranges = ["", f"?from={(end_day - timedelta(days=30)).isoformat()}&to={end_day.isoformat()}",
          f"?from={(end_day - timedelta(days=364)).isoformat()}&to={end_day.isoformat()}"]
roles = (("admin", "/admin", "/admin/patient_profile/"), ("official", "/official", None),
         ("doctor", "/staff", "/staff/patient_profile/"), ("staff1", "/staff", "/staff/patient_profile/"))
for username, prefix, profile in roles:
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = users[username]["id"]
        _support.open_session(sess)
    loaded = failed = 0
    problems = []
    urls = [r for r in rules if r.startswith(prefix)]
    if profile:
        for pid in sample_ids:
            urls += [f"{profile}{pid}", f"{profile}{pid}?print=1"]
    for url in urls:
        for suffix in (ranges if "report" in url else [""]):
            try:
                status = client.get(url + suffix).status_code
            except Exception as error:  # a server error is the failure being looked for
                status, problems = 500, problems + [f"{url}: {type(error).__name__}"]
            if status == 200:
                loaded += 1
            elif status >= 400:
                failed += 1
                problems.append(f"{url}{suffix}: {status}")
    check(f"{username}: every page in the menu, every report over three ranges and a sample "
          f"of profiles load with no error ({loaded} pages)", failed == 0 and loaded >= 20,
          problems[:5])

# ===========================================================================
section("9. ARCHIVING OLD DATABASES")
import shutil  # noqa: E402

work = TEST_DIR / "archive_work"
project, backups = work / "project", work / "backups"
project.mkdir(parents=True)
backups.mkdir()


def plain_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row {i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return path


plain_db(project / "app.db", 7)
plain_db(backups / "app.db.OLD_BACKUP_one", 3)
shutil.copy(backups / "app.db.OLD_BACKUP_one", backups / "app.db.OLD_BACKUP_same")
(backups / "notes.txt").write_text("not a database", encoding="utf-8")
(backups / "kept.idsbackup").write_bytes(b"IDSBAK1 already encrypted")
bundle = backups / "history.bundle"
bundle.write_bytes(b"# v2 git bundle")
originals = [archive.fingerprint(project / "app.db"),
             archive.fingerprint(backups / "app.db.OLD_BACKUP_one")]
output = []
result = archive.run(project=project, backup_dir=backups, say=output.append)
check("it found the old app.db and two plain backups, archived two (one was a copy of "
      "the other), verified all three and removed all three, with no failure",
      result == {"found": 3, "archived": 2, "verified": 3, "removed": 3, "failed": 0}, result)
archives = sorted(backups.glob("archive-*.idsbackup"))
check("the archives are .idsbackup files named archive-<original name>-<timestamp>",
      len(archives) == 2 and all(re.fullmatch(r"archive-.+-\d{8}_\d{6}\.idsbackup", a.name)
                                 for a in archives), [a.name for a in archives])
check("they start with the backup header, not 'SQLite format 3', and hold no row text",
      all(a.read_bytes().startswith(b"IDSBAK1") and b"SQLite format 3" not in a.read_bytes()
          and b"row 1" not in a.read_bytes() for a in archives))
check("the plain backups are gone; app.db was moved aside as previous-app.db, not deleted",
      not (backups / "app.db.OLD_BACKUP_one").exists()
      and not (backups / "app.db.OLD_BACKUP_same").exists()
      and not (project / "app.db").exists() and (backups / archive.PREVIOUS_NAME).exists())
check("a file that is not a database, an existing .idsbackup and a bundle were left alone",
      (backups / "notes.txt").exists() and (backups / "kept.idsbackup").exists()
      and bundle.exists())
restored = []
for a in archives:
    handle = TEST_DIR / f"roundtrip_{a.stem}.db"
    handle.write_bytes(archive.decrypt_backup(a.read_bytes()))
    restored.append(archive.fingerprint(handle))
check("each archive decrypts again to a database whose table counts and content hash equal "
      "an original's", sorted(restored, key=str) == sorted(originals, key=str), restored)
again = archive.run(project=project, backup_dir=backups, say=output.append)
check("a second run finds nothing to do", again["found"] == 0 and again["failed"] == 0, again)
check("the counts are printed, and only counts",
      output and all(re.fullmatch(r"files found: \d+, archived: \d+, verified: \d+, removed: "
                                  r"\d+, failed: \d+", line) for line in output[:1]))
removed = archive.run(project=project, backup_dir=backups, remove_previous=True, say=output.append)
check("--remove-previous deletes previous-app.db after checking its archive again",
      removed["removed"] == 1 and removed["failed"] == 0
      and not (backups / archive.PREVIOUS_NAME).exists(), removed)

# A copy of an already-archived file is recognised by its contents and not archived again.
plain_db(backups / "app.db.LATER_COPY", 7)
copy_result = archive.run(project=project, backup_dir=backups, say=output.append)
check("a file whose contents were archived before is not archived again (matched by hash), "
      "and is removed after its archive is decrypted and compared",
      copy_result["archived"] == 0 and copy_result["verified"] == 1 and copy_result["removed"] == 1
      and len(list(backups.glob("archive-*.idsbackup"))) == 2, copy_result)

# A mismatch keeps the plain file and says so.
plain_db(backups / "app.db.MISMATCH", 11)
real_encrypt = archive.encrypt_backup
archive.encrypt_backup = lambda data: real_encrypt(data[:-512] + b"\0" * 512)
try:
    failed_result = archive.run(project=project, backup_dir=backups, say=output.append)
finally:
    archive.encrypt_backup = real_encrypt
check("when the encrypted copy does not match, the plain file is kept and the failure is "
      "counted", failed_result["failed"] == 1 and failed_result["removed"] == 0
      and (backups / "app.db.MISMATCH").exists(), failed_result)
check("a damaged archive is not left in the index: the same file archives properly next time",
      archive.run(project=project, backup_dir=backups, say=output.append)["removed"] == 1
      and not (backups / "app.db.MISMATCH").exists())

# The demo database is not archived, and --replace on it just removes it.
plain_db(project / "app.db", 2)
conn = sqlite3.connect(project / "app.db")
conn.execute(f"PRAGMA user_version = {archive.DEMO_MARKER}")
conn.commit()
conn.close()
check("a database marked as the fictional demo is not archived", archive.run(
    project=project, backup_dir=backups, say=output.append)["found"] == 0
      and (project / "app.db").exists())
check("seed_demo_data's archive step moves a real database aside as previous-app.db only after "
      "it is archived and checked",
      (lambda: (plain_db(work / "existing.db", 4),
                seed.archive_existing(work / "existing.db", backups),
                (backups / archive.PREVIOUS_NAME).exists() and not (work / "existing.db").exists())[-1])())
check("and removes a demo database without archiving it",
      (lambda: (shutil.copy(project / "app.db", work / "demo_again.db"),
                seed.archive_existing(work / "demo_again.db", backups),
                not (work / "demo_again.db").exists())[-1])())
check("the archive marker is the one seed_demo_data writes",
      seed.DEMO_MARKER == archive.DEMO_MARKER == 5001
      and sqlite3.connect(PATH_B).execute("PRAGMA user_version").fetchone()[0] == 5001)
db.close()

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed_names = [name for name, ok in results if not ok]
for name in failed_names:
    print(f"  FAILED: {name}")
sys.exit(1 if failed_names else 0)

"""Audit coverage (H3): every health-record write leaves exactly one entry,
written by the account that acted, in one short line with no clinical text.

Runs on a fresh test database built by tests/_support.py. The clients send the
form token like a page does (tests/_support.py TokenClient).

Section 9 is structural: it lists every function that writes to the database
and fails if a write path has no audit entry, so new code cannot skip it.
"""
import ast
import io
import re
import sqlite3
import sys
from pathlib import Path

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
from models import audit as A  # noqa: E402
from models.inventory import DOSAGE_FORMS, DRUG_CLASSES, INVENTORY_FIELDS, UNITS  # noqa: E402
from models.patients import get_patient_by_id  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from routes.patient_views import patient_to_form  # noqa: E402
from utils.dates import display_date, today  # noqa: E402

# The entries contain "→". Some Windows consoles cannot print it.
sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
REPO = Path(_support.REPO)
PW = _support.PASSWORDS
DOCTOR_ID, STAFF_ID, ADMIN_ID = 5, 2, 1
TODAY = display_date(today())

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


def q(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def mark():
    return q("SELECT COALESCE(MAX(id), 0) FROM audit_logs")[0][0]


def since(start):
    return [dict(r) for r in q("SELECT * FROM audit_logs WHERE id > ? ORDER BY id", (start,))]


def sign_in(username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": PW[username]})
    return client


def one_entry(name, start, action, module, user_id, details):
    """Exactly one new entry, with this phrase, module, actor and details."""
    rows = since(start)
    ok = (len(rows) == 1 and rows[0]["action"] == action and rows[0]["module"] == module
          and rows[0]["user_id"] == user_id and rows[0]["details"] == details)
    return check(name, ok, "\n".join(f"{r['action']} | {r['module']} | {r['user_id']} | "
                                     f"{r['details']}" for r in rows) or "no entry"
                 + f"\nexpected: {details}")


def none_written(name, start):
    rows = since(start)
    return check(name, not rows, "\n".join(f"{r['action']} | {r['details']}" for r in rows))


def patient_ref(pid):
    p = get_patient_by_id(pid)
    return f"{p['full_name']} ({p['patient_id']})"


def item_ref(item_id):
    row = q("SELECT name, item_code FROM inventory_items WHERE id = ?", (item_id,))[0]
    return f"{row['name']} ({row['item_code']})"


def latest_visit(pid):
    return q("SELECT id FROM appointments WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
             (pid,))[0][0]


doctor, staff, admin = sign_in("doctor"), sign_in("staff"), sign_in("admin")
SUITE_START = mark()

# ===========================================================================
section("1. DECLARING A DEATH, AND REVERSING IT (Doctor only)")
pid = 12
start = mark()
r = staff.post("/staff/patient_records/archive",
               data={"single_patient_id": str(pid), "status": "Deceased"})
none_written("Health Center Staff is refused, and nothing is written", start)
check("and the patient is unchanged", q("SELECT status FROM patients WHERE id = ?",
                                        (pid,))[0][0] == "Active")
start = mark()
doctor.post("/staff/patient_records/archive",
            data={"single_patient_id": str(pid), "status": "Deceased"})
one_entry("the Doctor's declaration writes one entry, by the Doctor", start,
          A.ACTION_PATIENT_DECLARED_DECEASED, A.MODULE_PATIENTS, DOCTOR_ID,
          f"{patient_ref(pid)} — Status: Active → Deceased; Declared deceased on {TODAY}")
start = mark()
doctor.post("/staff/patient_records/archive",
            data={"single_patient_id": str(pid), "status": "Active"})
one_entry("the reversal writes one entry of its own, by the Doctor", start,
          A.ACTION_PATIENT_DEATH_REVERSED, A.MODULE_PATIENTS, DOCTOR_ID,
          f"{patient_ref(pid)} — Status: Deceased → Active; Death declaration reversed on {TODAY}")

# ===========================================================================
section("2. PATIENT RECORDS: STATUS, REGISTER, EDIT")
start = mark()
staff.post("/staff/patient_records/archive", data={"single_patient_id": "13", "status": "Inactive"})
one_entry("Active to Inactive writes one entry", start, A.ACTION_PATIENT_STATUS_CHANGED,
          A.MODULE_PATIENTS, STAFF_ID, f"{patient_ref(13)} — Status: Active → Inactive")
start = mark()
staff.post("/staff/patient_records/archive", data={"single_patient_id": "13", "status": "Inactive"})
none_written("the same status again changes nothing and writes nothing", start)
start = mark()
staff.post("/staff/patient_records/archive", data={"patient_ids": ["13", "18"], "status": "Active"})
rows = since(start)
check("a bulk change writes one entry per patient changed",
      sorted(r["details"] for r in rows) == sorted(
          [f"{patient_ref(13)} — Status: Inactive → Active",
           f"{patient_ref(18)} — Status: Inactive → Active"])
      and all(r["action"] == A.ACTION_PATIENT_STATUS_CHANGED for r in rows),
      [r["details"] for r in rows])

register = {
    "first_name": "Lorna", "last_name": "Dimaculangit", "birth_date": "1991-04-04",
    "sex": "Female", "civil_status": "Single", "address": "Purok 5, Barangay Poblacion",
    "municipality": "San Francisco", "province": "Surigao del Norte", "zip_code": "8405",
    "emergency_contact_name": "Test Relative", "emergency_contact_relationship": "Sibling",
    "emergency_contact_number": "09000002001", "confirm_duplicate": "yes",
}
start = mark()
r = staff.post("/staff/register-patient", data=dict(register, last_name=""))
none_written("a registration refused by validation writes nothing", start)
start = mark()
r = staff.post("/staff/register-patient", data=register)
new_pid = q("SELECT id FROM patients WHERE last_name = 'Dimaculangit'")[0][0]
one_entry("registering a patient writes one entry", start, A.ACTION_PATIENT_REGISTERED,
          A.MODULE_PATIENTS, STAFF_ID, f"{patient_ref(new_pid)} registered.")

form = patient_to_form(get_patient_by_id(new_pid))
form.update({"address": "Purok 6, Barangay Poblacion", "contact_number": "09000002002"})
start = mark()
staff.post(f"/staff/register-patient/{new_pid}", data=form)
one_entry("editing a patient writes one entry naming the fields, not the values", start,
          A.ACTION_PATIENT_UPDATED, A.MODULE_PATIENTS, STAFF_ID,
          f"{patient_ref(new_pid)} — Changed: Address, Contact number")
check("the new contact number is not in the entry",
      all("9000072" not in (r["details"] or "") for r in since(start - 1)))
start = mark()
staff.post(f"/staff/register-patient/{new_pid}", data=patient_to_form(get_patient_by_id(new_pid)))
none_written("saving the form with nothing changed writes nothing", start)

# ===========================================================================
section("3. THE PATIENT QUEUE: CHECK IN, START, COMPLETE")
reason = "Masakit ang tiyan mula kahapon"
start = mark()
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "2", "reason": reason})
visit = latest_visit(2)
one_entry("check-in writes one entry, without the visit reason", start,
          A.ACTION_PATIENT_CHECKED_IN, A.MODULE_APPOINTMENTS, STAFF_ID,
          f"{patient_ref(2)}, visit APT-{visit:05d}, walk-in.")
start = mark()
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "2", "reason": reason})
none_written("checking in someone already in the queue writes nothing", start)
start = mark()
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "3", "reason": ""})
none_written("a check-in refused for no reason writes nothing", start)
start = mark()
doctor.post("/staff/appointment_scheduling/start-consultation", data={"appointment_id": str(visit)})
one_entry("starting a consultation writes one entry", start, A.ACTION_CONSULTATION_STARTED,
          A.MODULE_APPOINTMENTS, DOCTOR_ID, f"{patient_ref(2)}, visit APT-{visit:05d}.")
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "3", "reason": "Ubo"})
other = latest_visit(3)
start = mark()
staff.post("/staff/appointment_scheduling/start-consultation", data={"appointment_id": str(other)})
none_written("starting while the room is busy is refused and writes nothing", start)
start = mark()
staff.post("/staff/appointment_scheduling/complete-consultation", data={"appointment_id": str(visit)})
one_entry("completing from the queue writes one entry", start, A.ACTION_CONSULTATION_COMPLETED,
          A.MODULE_APPOINTMENTS, STAFF_ID, f"{patient_ref(2)}, visit APT-{visit:05d}.")
start = mark()
staff.post("/staff/appointment_scheduling/complete-consultation", data={"appointment_id": str(visit)})
none_written("completing it again writes nothing", start)

# ===========================================================================
section("4. A NEW CONSULTATION, WITH DOSES, DISPENSING AND A SEAL (Doctor)")
DIAGNOSIS = "Zzdiagnosis Dengue fever suspected"
TREATMENT = "Zztreatment Paracetamol and oral fluids"
COMPLAINT = "Zzcomplaint fever for two days"
REMARKS = "Zzremarks return if worse"
SECRET_TEXTS = (DIAGNOSIS, TREATMENT, COMPLAINT, REMARKS, "Zzdiagnosis", "Zztreatment")
consult = {
    "chief_complaint": COMPLAINT, "diagnosis": DIAGNOSIS, "treatment_plan": TREATMENT,
    "temperature": "38.4", "blood_pressure": "110/70", "pulse_rate": "90",
    "respiratory_rate": "18", "weight": "58", "remarks": REMARKS,
}
medicine = q("""SELECT id, name, unit FROM inventory_items WHERE status = 'Active'
                AND category = 'Medicine' AND stock_quantity > 20
                AND (expiry_date IS NULL OR expiry_date > date('now')) ORDER BY id LIMIT 1""")[0]
stock_before = q("SELECT stock_quantity FROM inventory_items WHERE id = ?", (medicine["id"],))[0][0]

staff.post("/staff/appointment_scheduling/start-consultation", data={"appointment_id": str(other)})
start = mark()
r = doctor.post(f"/staff/consultation/record/{other}",
                data=dict(consult, chief_complaint=""))
none_written("a consultation refused by validation writes nothing", start)
start = mark()
r = doctor.post(f"/staff/consultation/record/{other}", data=dict(
    consult, dispense_item_0=str(medicine["id"]), dispense_qty_0=str(stock_before + 50)))
none_written("a consultation refused for too little stock writes nothing", start)
check("and no stock moved", q("SELECT stock_quantity FROM inventory_items WHERE id = ?",
                              (medicine["id"],))[0][0] == stock_before)

start = mark()
r = doctor.post(f"/staff/consultation/record/{other}", data=dict(
    consult, is_restricted="1", general_vaccinations=["influenza"],
    dispense_item_0=str(medicine["id"]), dispense_qty_0="4"))
cid = q("SELECT id FROM consultations WHERE appointment_id = ?", (other,))
check("the sealed consultation was saved", r.status_code == 302 and cid, r.status_code)
cid = cid[0][0] if cid else 0
rows = since(start)
by_action = {}
for row in rows:
    by_action.setdefault(row["action"], []).append(row)
expected = {
    A.ACTION_CONSULTATION_RECORDED: f"Consultation #{cid} for {patient_ref(3)}, visit {TODAY}.",
    A.ACTION_OTHER_VACCINATIONS_RECORDED: f"1 dose for {patient_ref(3)} at consultation #{cid}: Influenza.",
    A.ACTION_MEDICINE_DISPENSED: f"For {patient_ref(3)}, consultation #{cid}: 1 item. "
                                 "Names not shown: the consultation is restricted.",
    A.ACTION_CONSULTATION_COMPLETED: f"{patient_ref(3)}, visit APT-{other:05d}.",
}
for action, details in expected.items():
    got = by_action.get(action, [])
    check(f"one '{action}' entry, by the Doctor",
          len(got) == 1 and got[0]["details"] == details and got[0]["user_id"] == DOCTOR_ID,
          [g["details"] for g in got] + [f"expected: {details}"])
check("the seal is recorded by its existing entry", len(by_action.get(
    A.ACTION_CONSULTATION_RESTRICTED, [])) == 1)
check("nothing else was written",
      set(by_action) == set(expected) | {A.ACTION_CONSULTATION_RESTRICTED}, sorted(by_action))
check("the dispensing entry of a sealed consultation does not name the medicine",
      medicine["name"] not in by_action[A.ACTION_MEDICINE_DISPENSED][0]["details"])

# An unsealed visit: the medicine is named, with its quantity.
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "4", "reason": "Lagnat"})
v4 = latest_visit(4)
doctor.post("/staff/appointment_scheduling/start-consultation", data={"appointment_id": str(v4)})
start = mark()
doctor.post(f"/staff/consultation/record/{v4}", data=dict(
    consult, dispense_item_0=str(medicine["id"]), dispense_qty_0="2"))
c4 = q("SELECT id FROM consultations WHERE appointment_id = ?", (v4,))[0][0]
unit = (medicine["unit"] or "unit").lower()
got = [r for r in since(start) if r["action"] == A.ACTION_MEDICINE_DISPENSED]
check("dispensing writes one entry: who, which patient, which item, how many",
      len(got) == 1 and got[0]["details"] == f"For {patient_ref(4)}, consultation #{c4}: "
      f"2 {unit}s of {medicine['name']}." and got[0]["user_id"] == DOCTOR_ID,
      [g["details"] for g in got])

# A child: an EPI dose given here, and one reported as given elsewhere. The
# fixture already holds this infant's birth doses (BCG, Hepatitis B).
staff.post("/staff/appointment_scheduling/check-in", data={"patient_id": "17", "reason": "Bakuna"})
v17 = latest_visit(17)
doctor.post("/staff/appointment_scheduling/start-consultation", data={"appointment_id": str(v17)})
start = mark()
r = doctor.post(f"/staff/consultation/record/{v17}", data=dict(
    consult, weight="6", immunizations=["PENTA:1"], immunizations_elsewhere=["OPV:1"]))
c17 = q("SELECT id FROM consultations WHERE appointment_id = ?", (v17,))
c17 = c17[0][0] if c17 else 0
got = {r["action"]: r for r in since(start)}
check("EPI doses given here write one entry", A.ACTION_EPI_DOSES_RECORDED in got
      and got[A.ACTION_EPI_DOSES_RECORDED]["details"]
      == f"1 dose for {patient_ref(17)} at consultation #{c17}: Pentavalent dose 1.",
      {k: v["details"] for k, v in got.items()})
check("a dose reported as given elsewhere writes one entry", A.ACTION_REPORTED_DOSES_RECORDED in got
      and got[A.ACTION_REPORTED_DOSES_RECORDED]["details"].startswith(
          f"1 dose for {patient_ref(17)} at consultation #{c17}: OPV dose 1 ("),
      {k: v["details"] for k, v in got.items()})

# ===========================================================================
section("5. EDITING A CONSULTATION: DISPENSING STILL WRITES ITS OWN ENTRY")
# A second medicine: the same one again on this visit is refused by design.
second = q("""SELECT id, name, unit FROM inventory_items WHERE status = 'Active'
              AND category = 'Medicine' AND stock_quantity > 20 AND id != ?
              AND (expiry_date IS NULL OR expiry_date > date('now')) ORDER BY id LIMIT 1""",
           (medicine["id"],))[0]
start = mark()
edit = dict(consult, dispense_item_0=str(second["id"]), dispense_qty_0="1")
r = doctor.post(f"/staff/consultation/edit/{c4}", data=edit)
got = [r for r in since(start) if r["action"] == A.ACTION_MEDICINE_DISPENSED]
unit2 = (second["unit"] or "unit").lower()
check("an edit that dispenses writes one dispensing entry",
      len(got) == 1 and got[0]["details"] == f"For {patient_ref(4)}, consultation #{c4}: "
      f"1 {unit2} of {second['name']}.", [g["details"] for g in since(start)])

# ===========================================================================
section("6. MEDICINE INVENTORY: ADD, EDIT, STOCK, ARCHIVE")
item_form = {
    "name": "Cetirizine 10 mg tablet", "generic_name": "Cetirizine", "brand_name": "",
    "category": "Medicine", "drug_class": DRUG_CLASSES[0], "dosage_strength": "10 mg",
    "dosage_form": DOSAGE_FORMS[0], "unit": UNITS[0], "stock_quantity": "100",
    "low_stock_threshold": "20", "expiry_date": "2029-12-31", "date_received": "2026-09-01",
    "batch_number": "AUD-001", "manufacturer": "", "supplier": "", "unit_cost": "",
    "storage_location": "", "notes": "", "status": "Active",
}
start = mark()
staff.post("/staff/add_edit_medicine", data=dict(item_form, name=""))
none_written("an item refused by validation writes nothing", start)
start = mark()
staff.post("/staff/add_edit_medicine", data=item_form)
iid = q("SELECT id FROM inventory_items WHERE batch_number = 'AUD-001'")[0][0]
one_entry("adding an item writes one entry", start, A.ACTION_INVENTORY_ADDED,
          A.MODULE_INVENTORY, STAFF_ID, f"{item_ref(iid)}, stock 100.")
start = mark()
staff.post(f"/staff/add_edit_medicine/{iid}", data=dict(item_form, stock_quantity="90",
                                                      batch_number="AUD-002"))
one_entry("a stock change writes 'Adjusted stock quantity' with before and after", start,
          A.ACTION_STOCK_ADJUSTED, A.MODULE_INVENTORY, STAFF_ID,
          f"{item_ref(iid)} — Stock: 100 → 90; Also changed: Batch number")
start = mark()
staff.post(f"/staff/add_edit_medicine/{iid}", data=dict(item_form, stock_quantity="90",
                                                      batch_number="AUD-003"))
one_entry("any other edit writes 'Edited inventory item' with the field names", start,
          A.ACTION_INVENTORY_EDITED, A.MODULE_INVENTORY, STAFF_ID,
          f"{item_ref(iid)} — Changed: Batch number")
start = mark()
staff.post(f"/staff/add_edit_medicine/{iid}", data=dict(item_form, stock_quantity="90",
                                                      batch_number="AUD-003"))
none_written("saving an item with nothing changed writes nothing", start)
start = mark()
staff.post("/staff/medicine_inventory/archive", data={"item_id": str(iid), "status": "Inactive"})
one_entry("archiving writes one entry", start, A.ACTION_INVENTORY_ARCHIVED, A.MODULE_INVENTORY,
          STAFF_ID, f"{item_ref(iid)} — Status: Active → Inactive")
start = mark()
staff.post("/staff/medicine_inventory/archive", data={"item_id": str(iid), "status": "Inactive"})
none_written("archiving it again writes nothing", start)
start = mark()
staff.post("/staff/medicine_inventory/archive", data={"item_id": str(iid), "status": "Active"})
one_entry("returning it to service writes one entry", start, A.ACTION_INVENTORY_RESTORED,
          A.MODULE_INVENTORY, STAFF_ID, f"{item_ref(iid)} — Status: Inactive → Active")

# ===========================================================================
section("7. NO NEW ENTRY CARRIES CLINICAL OR PRIVATE TEXT")
NEW_ACTIONS = {v for k, v in vars(A).items() if k.startswith("ACTION_") and v in {
    A.ACTION_PATIENT_REGISTERED, A.ACTION_PATIENT_UPDATED, A.ACTION_PATIENT_STATUS_CHANGED,
    A.ACTION_PATIENT_DECLARED_DECEASED, A.ACTION_PATIENT_DEATH_REVERSED,
    A.ACTION_CONSULTATION_RECORDED, A.ACTION_EPI_DOSES_RECORDED,
    A.ACTION_REPORTED_DOSES_RECORDED, A.ACTION_OTHER_VACCINATIONS_RECORDED,
    A.ACTION_MEDICINE_DISPENSED, A.ACTION_INVENTORY_ADDED, A.ACTION_INVENTORY_EDITED,
    A.ACTION_STOCK_ADJUSTED, A.ACTION_INVENTORY_ARCHIVED, A.ACTION_INVENTORY_RESTORED,
    A.ACTION_PATIENT_CHECKED_IN, A.ACTION_CONSULTATION_STARTED,
    A.ACTION_CONSULTATION_COMPLETED}}
written = [r for r in since(SUITE_START) if r["action"] in NEW_ACTIONS]
check(f"every new kind of entry was exercised ({len(NEW_ACTIONS)} kinds)",
      {r["action"] for r in written} == NEW_ACTIONS,
      sorted(NEW_ACTIONS - {r["action"] for r in written}))
leaks = [r["details"] for r in written
         if any(s.lower() in (r["details"] or "").lower() for s in SECRET_TEXTS)
         or reason in (r["details"] or "")
         or re.search(r"(?<!\d)09\d{9}(?!\d)", r["details"] or "")]
check("none contains diagnosis, treatment, complaint or remark text, a visit reason "
      "or a contact number", written and not leaks, leaks)
sealed = q("SELECT * FROM consultations WHERE id = ?", (cid,))[0]
sealed_values = [str(sealed[k]) for k in sealed.keys()
                 if k in ("chief_complaint", "diagnosis", "treatment_plan", "remarks")
                 and sealed[k]]
check("the sealed consultation is sealed, and no new entry holds any of its text",
      sealed["is_restricted"] == 1 and sealed_values and not [
          r for r in written for v in sealed_values if v in (r["details"] or "")])
check("each new entry is one short line (at most 200 characters, no line breaks)",
      all(len(r["details"]) <= 200 and "\n" not in r["details"] for r in written),
      max((r["details"] for r in written), key=len))

# ===========================================================================
section("8. THE AUDIT LOGS SCREEN AND ITS EXPORT")
page = admin.get("/admin/audit_logs").get_data(as_text=True)
check("the screen lists the death declaration and the dispensing entry",
      A.ACTION_PATIENT_DECLARED_DECEASED in page and A.ACTION_MEDICINE_DISPENSED in page)
check("the module filter offers the modules the new entries use",
      all(f'value="{m}"' in page for m in (A.MODULE_PATIENTS, A.MODULE_INVENTORY,
                                           A.MODULE_APPOINTMENTS, A.MODULE_CONSULTATIONS)))
page = admin.get(f"/admin/audit_logs?module={A.MODULE_PATIENTS}").get_data(as_text=True)
check("filtering by Patient Records shows the death declaration and its reversal",
      A.ACTION_PATIENT_DECLARED_DECEASED in page and A.ACTION_PATIENT_DEATH_REVERSED in page
      and A.ACTION_MEDICINE_DISPENSED not in page)
check("the death declaration has its own icon", ">warning<" in page)
r = admin.get("/admin/audit_logs/export.xlsx")
cells = " ".join(str(v) for ws in load_workbook(io.BytesIO(r.data)).worksheets
                 for row in ws.iter_rows(values_only=True) for v in row if v is not None)
check("the Excel export carries the new entries",
      r.status_code == 200 and all(a in cells for a in (
          A.ACTION_PATIENT_DECLARED_DECEASED, A.ACTION_STOCK_ADJUSTED,
          A.ACTION_PATIENT_CHECKED_IN)))
r = admin.get("/admin/audit_logs/export.pdf")
check("the PDF export still works", r.status_code == 200 and r.data[:4] == b"%PDF")
reports = admin.get("/admin/reports_analytics").get_data(as_text=True)
check("M6: Reports no longer says the trail records only three things",
      "records three things" not in reports
      and "Audit Logs records changes to patient, clinical, stock and account records" in reports)

# ===========================================================================
section("9. EVERY WRITE PATH HAS AN AUDIT ENTRY (structural)")
# Functions that write but are deliberately not audited, and why.
EXEMPT = {
    # The audit trail itself.
    "log_action": "writes audit_logs",
    # A new install, before any account exists, so no one could be named.
    "seed_demo_users": "first install only",
}
# Calls the call graph cannot see: a function reached through a table. Each
# maps to the function that calls it and writes the audit entry.
LOGGED_BY = {
    "_apply_epi": "process_vaccination_correction",
    "_apply_general": "process_vaccination_correction",
}
SQL_WRITE = re.compile(r"\b(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
                       re.I)
files = sorted(p for d in ("models", "routes", "utils", "database")
               for p in (REPO / d).glob("*.py"))
functions = {}
for path in files:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef):
            functions.setdefault(node.name, []).append((path.name, node))


def called_names(node):
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            names.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", None))
    return names


def writes_sql(node):
    for sub in ast.walk(node):
        text = sub.value if isinstance(sub, ast.Constant) and isinstance(sub.value, str) else (
            "".join(v.value for v in sub.values if isinstance(v, ast.Constant))
            if isinstance(sub, ast.JoinedStr) else "")
        if SQL_WRITE.search(text):
            return True
    return False


def logs(name, depth=0):
    """Whether a function writes an audit entry: itself, a _log_ helper, a
    LOGGED_BY entry, or every one of its callers."""
    if name in LOGGED_BY:
        return logs(LOGGED_BY[name], depth + 1)
    for _, node in functions.get(name, []):
        calls = called_names(node)
        if "log_action" in calls or any(c and c.startswith("_log") for c in calls):
            return True
    callers = [fn for fn, defs in functions.items()
               for _, node in defs if name in called_names(node)]
    return depth < 4 and bool(callers) and all(logs(c, depth + 1) for c in callers)


writers = sorted(name for name, defs in functions.items()
                 if any(writes_sql(node) for _, node in defs))
problems = []
for writer in writers:
    call_sites = [(fn, sub) for fn, defs in functions.items() for _, node in defs
                  for sub in ast.walk(node) if isinstance(sub, ast.Call)
                  and (getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)) == writer]
    if writer in EXEMPT:
        if EXEMPT[writer] == "no caller" and call_sites:
            problems.append(f"{writer}: exempt as unused, but now called by "
                            + ", ".join(sorted({fn for fn, _ in call_sites})))
        continue
    node = functions[writer][0][1]
    if "log_action" in called_names(node):
        continue
    params = [a.arg for a in node.args.args + node.args.kwonlyargs]
    if "audit" in params and "audit" not in called_names(node):
        problems.append(f"{writer}: takes `audit` but never calls it")
    if not call_sites:
        problems.append(f"{writer}: writes, has no caller, and is not in EXEMPT")
    for fn, call in call_sites:
        passes = any(k.arg == "audit" and not (isinstance(k.value, ast.Constant)
                                               and k.value.value is None)
                     for k in call.keywords)
        if not passes and not logs(fn):
            problems.append(f"{writer} called by {fn} with no audit entry")
print(f"       write functions found: {len(writers)} (exempt: {len(EXEMPT)})")
check("every write path writes an audit entry, or is listed in EXEMPT with a reason",
      writers and not problems, "\n".join(problems))
check("the check sees the paths this task added",
      all(w in writers for w in ("set_patient_status", "record_dispensing",
                                 "create_inventory_item", "check_in_patient",
                                 "create_consultation")))

# ===========================================================================
section("10. THE ENTRY AND THE CHANGE COMMIT TOGETHER")
from models.inventory import create_inventory_item, set_item_status  # noqa: E402
from models.patients import set_patient_status  # noqa: E402


def failing_audit(*args):
    """Writes an entry on the writer's connection, then fails, as a broken
    audit write would."""
    A.log_action(ADMIN_ID, "Test entry that must roll back", A.MODULE_INVENTORY,
                 "rollback test", conn=args[0])
    raise RuntimeError("audit write failed")


def raises(call):
    try:
        call()
    except RuntimeError:
        return True
    return False


start = mark()
failed = raises(lambda: create_inventory_item(dict(item_form, batch_number="AUD-ROLLBACK"),
                                              audit=failing_audit))
check("if the entry cannot be written, the new item is not saved either",
      failed and not q("SELECT 1 FROM inventory_items WHERE batch_number = 'AUD-ROLLBACK'"))
failed = raises(lambda: set_item_status(iid, "Inactive", audit=failing_audit))
failed_patient = raises(lambda: set_patient_status([14], "Inactive", audit=failing_audit))
check("the same holds for a status change, on items and on patients",
      failed and failed_patient
      and q("SELECT status FROM inventory_items WHERE id = ?", (iid,))[0][0] == "Active"
      and q("SELECT status FROM patients WHERE id = 14")[0][0] == "Active")
none_written("and none of those half-written entries remains", start)

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print("  FAILED:", name)
print("=" * 78)
sys.exit(0 if not failed else 1)

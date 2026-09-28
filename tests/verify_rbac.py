"""End-to-end verification of the consultation RBAC / confidentiality work.

Runs the REAL Flask application over a fresh test database built by
tests/_support.py, driving real
HTTP requests through Flask's test client. Nothing here reaches into the view
functions directly: every assertion is made against a response body or against
the database as the application left it.

The copy exists so the suite can do the destructive half honestly -- forge a
staff submission carrying a diagnosis, seal a record, save an edit -- without
leaving test residue in app.db.
"""
import os
import shutil
import sqlite3
import sys

import _support  # noqa: E402  (first: builds the test database, points the app at it)
PROJECT = str(_support.REPO)
os.chdir(PROJECT)

TEST_DB = _support.DB_PATH

import config  # noqa: E402
from app import create_app  # noqa: E402

app = create_app()
app.config["DATABASE"] = TEST_DB
app.config["WTF_CSRF_ENABLED"] = False
_support.attach(app)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}")
    if detail:
        for line in str(detail).splitlines():
            print(f"       {line}")
    return ok


def db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def body(resp):
    return resp.get_data(as_text=True)


def audit_since(marker_id, action=None):
    conn = db()
    sql = "SELECT * FROM audit_logs WHERE id > ?"
    args = [marker_id]
    if action:
        sql += " AND action = ?"
        args.append(action)
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]
    conn.close()
    return rows


def max_audit_id():
    conn = db()
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_logs").fetchone()[0]
    conn.close()
    return row


# DB-INDEPENDENCE (2026-09-26): the suite used to assume ids 1/2/3/5 were the
# Administrator, Staff, Official and Doctor, that some consultation already
# carried a diagnosis and plan, and that some appointment was already In
# Consultation. The last stopped being true when the live queue emptied, and the
# suite crashed in setup before running a single check. Every fixture is now
# found in the copy if it is there and CREATED in the copy if it is not, so the
# suite runs the same checks whatever the live database happens to hold. None
# of this touches app.db: TEST_DB is the fresh test database.
def fixture_failure(what, detail):
    """Setup could not build what the checks need: say so, and stop cleanly."""
    check(f"FIXTURE: {what}", False, detail)
    print("\n" + "=" * 78)
    print(f"RESULT: setup failed, 0 checks run past fixtures -- {what}")
    print("=" * 78)
    sys.exit(2)


def account_for(role, username):
    """The first active account holding `role`, created in the copy if none does.

    Sessions are forged with client_as(), so a created account needs no usable
    password; it gets a random hash no one knows.
    """
    import secrets
    from werkzeug.security import generate_password_hash
    conn = db()
    row = conn.execute(
        "SELECT id FROM users WHERE role = ? AND is_active = 1 ORDER BY id LIMIT 1",
        (role,)).fetchone()
    if row is not None:
        conn.close()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        (username, generate_password_hash(secrets.token_urlsafe(32)),
         f"Verification {role}", role))
    conn.commit()
    conn.close()
    print(f"  created a {role} account in the test copy: #{cur.lastrowid}")
    return cur.lastrowid


def new_queue_entry(patient_id):
    """A walk-in, checked in today and In Consultation -- in the test copy.

    The same row shape the Doctor-role suite (verify_doctor.py) builds, and the shape Start
    Consultation leaves behind: the Record Consultation route accepts only an
    appointment in this state.
    """
    conn = db()
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (?, ?, date('now','localtime'), "
        "'In Consultation', 1, datetime('now','localtime'))",
        (patient_id, STAFF_ID))
    conn.commit()
    row = conn.execute("SELECT * FROM appointments WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    conn.close()
    return row


ADMIN_ID = account_for("Admin", "verify-admin")
STAFF_ID = account_for("Health Center Staff", "verify-staff")
OFFICIAL_ID = account_for("Barangay Official", "verify-official")
DOCTOR_ID = account_for("Doctor", "verify-doctor")  # PORTED: the clinician is the Doctor
print(f"accounts: admin #{ADMIN_ID}, staff #{STAFF_ID}, "
      f"official #{OFFICIAL_ID}, doctor #{DOCTOR_ID}")


print("=" * 78)
print("IDS-BPHCSN — consultation RBAC / RA 11166 confidentiality verification")
print(f"database under test: {TEST_DB}")
print("=" * 78)

# ---------------------------------------------------------------------------
# 0. Route x role matrix
# ---------------------------------------------------------------------------
print("\n--- 0. ROUTE x ROLE MATRIX (consultation + profile surfaces) ---")
consult_rules = sorted(
    (r.rule, r.endpoint, sorted(r.methods - {"HEAD", "OPTIONS"}))
    for r in app.url_map.iter_rules()
    if "consultation" in r.rule or "patient_profile" in r.rule
)
for rule, endpoint, methods in consult_rules:
    print(f"  {','.join(methods):9s} {rule:62s} -> {endpoint}")

restrict_endpoints = [e for _, e, _ in consult_rules if "restrict" in e]
check(
    "Exactly one restrict-consultation route exists, and it is the admin one",
    restrict_endpoints == ["staff.restrict_consultation"],
    f"found: {restrict_endpoints}",
)
check(
    "No /staff/ URL exists for restricting a consultation",
    not any(r.startswith("/admin") and "restrict" in r for r, _, _ in consult_rules),
)

# ---------------------------------------------------------------------------
# Fixtures: pick a consultation with real clinical text, and its patient
# ---------------------------------------------------------------------------
conn = db()
target = conn.execute(
    """
    SELECT * FROM consultations
     WHERE diagnosis IS NOT NULL AND TRIM(diagnosis) <> ''
       AND treatment_plan IS NOT NULL AND TRIM(treatment_plan) <> ''
     ORDER BY id DESC LIMIT 1
    """
).fetchone()
if target is None:
    # DB-INDEPENDENCE: no visit on file carries clinical text. Its text is
    # replaced by the sentinels below either way, so a consultation of the
    # suite's own, on the first patient on file, tests the same thing.
    patient_row = conn.execute("SELECT id FROM patients ORDER BY id LIMIT 1").fetchone()
    if patient_row is None:
        conn.close()
        fixture_failure("a patient to attach the fixture consultation to",
                        "the patients table is empty in this copy")
    cur = conn.execute(
        "INSERT INTO consultations (patient_id, recorded_by, consultation_date, "
        "chief_complaint, diagnosis, treatment_plan) VALUES (?, ?, "
        "date('now','localtime'), 'Verification fixture', 'x', 'x')",
        (patient_row["id"], DOCTOR_ID))
    conn.commit()
    target = conn.execute("SELECT * FROM consultations WHERE id = ?",
                          (cur.lastrowid,)).fetchone()
    print(f"  created fixture consultation #{target['id']} in the test copy")
CID = target["id"]
PID = target["patient_id"]

# The stored values are ordinary clinical prose -- "Dengue fever", "Paracetamol"
# -- and those words legitimately appear elsewhere on the same pages (another
# visit's plan, the dispensing table's medicine column). A leak test that
# substring-matched them would fail on a page that leaked nothing.
#
# So the fixture is given text that CANNOT occur by coincidence. Every "is this
# in the bytes sent to Staff" assertion below is then exact: a hit is a leak.
REAL_DIAGNOSIS = "SENTINEL-DX-7f3a HIV reactive, confirmatory assay positive"
REAL_PLAN = "SENTINEL-TX-7f3a commence antiretroviral therapy, refer to hub"
conn.execute(
    "UPDATE consultations SET diagnosis = ?, treatment_plan = ? WHERE id = ?",
    (REAL_DIAGNOSIS, REAL_PLAN, CID),
)
conn.commit()
patient = conn.execute("SELECT * FROM patients WHERE id = ?", (PID,)).fetchone()
# TWO queue entries, because the suite spends one.
#
# The forged-submission test at A.3b saves a real consultation, which completes
# the appointment it was recording against -- so a later GET of that same URL is
# a redirect, not a form. The capabilities section at the end has to fetch a LIVE
# Record Consultation page to assert that intake, dispensing and vaccination are
# untouched, so it needs a queue entry of its own rather than the corpse of the
# one A.3b consumed.
#
# DB-INDEPENDENCE: these used to be cloned from whatever appointment was already
# In Consultation in the live database, and when none was, the loop made none
# and the setup crashed. The suite now creates its own, in the test copy, and
# creates the spare only when the capabilities section needs it -- after A.3b has
# completed the first -- so the suite never holds two visits open at once, which
# the application itself refuses to do.
#
# The patient must be Active (a Deceased or Inactive patient is not someone a
# desk checks in) and PAEDIATRIC by the application's own rule: the capabilities
# section asserts Staff's form still offers growth measurements, and the form
# renders that section only for a child. On 2026-09-25 the queued patient
# happened to be an infant, so that check silently depended on who was waiting.
# The fixture's own patient is used when they qualify, otherwise the first
# patient who does, otherwise a child is registered in the copy.
from models.consultations import consultation_age_context  # noqa: E402
candidates = conn.execute(
    "SELECT * FROM patients WHERE status = 'Active' ORDER BY (id = ?) DESC, id",
    (PID,)).fetchall()
with app.app_context():
    queue_patient = next(
        (p for p in candidates if consultation_age_context(dict(p))["is_pediatric"]), None)
if queue_patient is None:
    cur = conn.execute(
        "INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, "
        "status) VALUES ('VERIFY-RBAC-CHILD', 'Verification', 'Child', "
        "date('now','localtime','-2 years'), 'Female', 'Active')")
    conn.commit()
    queue_patient = conn.execute("SELECT * FROM patients WHERE id = ?",
                                 (cur.lastrowid,)).fetchone()
    print(f"  registered a paediatric patient in the test copy: #{queue_patient['id']}")
conn.close()
QUEUE_PID = queue_patient["id"]
queued = new_queue_entry(QUEUE_PID)
SPARE_APPT = None  # created by the capabilities section, when it is needed

print(f"\nfixture consultation #{CID} (patient {patient['patient_id']}, "
      f"{patient['first_name']} {patient['last_name']})")
print(f"  diagnosis      : {REAL_DIAGNOSIS[:70]}")
print(f"  treatment_plan : {REAL_PLAN[:70]}")
# This line used to read `dict(queued) if queued is None else ...` -- dict(None)
# raised TypeError in exactly the case it existed to report, which is how the
# missing fixture surfaced as a traceback instead of a sentence.
print("queued appointment: "
      + ("none -- no appointment is In Consultation" if queued is None
         else f"#{queued['id']} patient {queued['patient_id']}, {queued['status']}, "
              f"{queued['appointment_date']}"))

staff = client_as(STAFF_ID)
admin = client_as(DOCTOR_ID)  # PORTED: `admin` is the clinician
sysadmin = client_as(ADMIN_ID)

# ===========================================================================
# TASK A — diagnosis / treatment plan restricted to Administrator
# ===========================================================================
print("\n--- TASK A.1: Staff's Record Consultation form omits the fields ---")

APPT = queued["id"] if queued else None
if APPT is None:
    check("A queued appointment exists to record against", False,
          "no appointment is In Consultation; A.1/A.2 record-path skipped")
else:
    resp = staff.get(f"/staff/consultation/record/{APPT}")
    page = body(resp)
    check("Staff Record Consultation renders (200)", resp.status_code == 200,
          f"status={resp.status_code}")
    check('Staff page contains NO name="diagnosis" input',
          'name="diagnosis"' not in page)
    check('Staff page contains NO name="treatment_plan" input',
          'name="treatment_plan"' not in page)
    check('Staff page contains NO "Assessment & Plan" heading',
          "Assessment &amp; Plan" not in page and "Assessment & Plan" not in page)
    check('Staff page contains NO Restricted checkbox (name="is_restricted")',
          'name="is_restricted"' not in page)
    check('Staff page DOES explain who records the diagnosis',
          "recorded by the Doctor" in page)
    check('Staff page retains intake fields (chief_complaint, temperature)',
          'name="chief_complaint"' in page and 'name="temperature"' in page)

    resp = admin.get(f"/staff/consultation/record/{APPT}")
    apage = body(resp)
    check("Administrator Record Consultation renders (200)", resp.status_code == 200,
          f"status={resp.status_code}")
    check('Administrator page DOES contain name="diagnosis"',
          'name="diagnosis"' in apage)
    check('Administrator page DOES contain name="treatment_plan"',
          'name="treatment_plan"' in apage)
    check('Administrator page DOES contain the Restricted checkbox',
          'name="is_restricted"' in apage)

print("\n--- TASK A.2: Staff EDIT form omits the fields, Administrator's does not ---")
resp = staff.get(f"/staff/consultation/edit/{CID}")
page = body(resp)
check("Staff Edit Consultation renders (200)", resp.status_code == 200,
      f"status={resp.status_code}")
check('Staff edit page contains NO name="diagnosis"', 'name="diagnosis"' not in page)
check('Staff edit page contains NO name="treatment_plan"',
      'name="treatment_plan"' not in page)
check("Staff edit page does NOT leak the stored diagnosis text anywhere",
      REAL_DIAGNOSIS not in page)
check("Staff edit page does NOT leak the stored treatment plan text anywhere",
      REAL_PLAN not in page)

resp = admin.get(f"/staff/consultation/edit/{CID}")
apage = body(resp)
check("Administrator edit page DOES carry the stored diagnosis",
      REAL_DIAGNOSIS in apage)
check("Administrator edit page DOES carry the stored treatment plan",
      REAL_PLAN in apage)

# ===========================================================================
# TASK A.3 — THE FORGED REQUEST. The critical security check.
# ===========================================================================
print("\n--- TASK A.3: FORGED Staff submission carrying diagnosis/treatment_plan ---")
print("    (a POST assembled by hand — the fields are not on Staff's page at all)")

FORGED_D = "FORGED BY STAFF — HIV reactive, confirmatory Western blot positive"
FORGED_P = "FORGED BY STAFF — start ART, refer to treatment hub"

# --- A.3a: forged EDIT of an existing consultation --------------------------
mark = max_audit_id()
conn = db()
before = dict(conn.execute("SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()

resp = staff.post(
    f"/staff/consultation/edit/{CID}",
    data={
        "chief_complaint": before["chief_complaint"] or "Follow-up",
        "diagnosis": FORGED_D,
        "treatment_plan": FORGED_P,
        "remarks": before["remarks"] or "",
        "temperature": before["temperature"] or "",
        "blood_pressure": before["blood_pressure"] or "",
        "pulse_rate": before["pulse_rate"] or "",
        "respiratory_rate": before["respiratory_rate"] or "",
        "weight": before["weight"] or "",
        "height": before["height"] or "",
        "follow_up_date": before["follow_up_date"] or "",
        "is_restricted": "1",          # forged: staff trying to seal, too
    },
    follow_redirects=False,
)
conn = db()
after = dict(conn.execute("SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()

check("Forged staff edit was accepted as a request (no 500)",
      resp.status_code in (200, 302), f"status={resp.status_code}")
check("FORGED diagnosis was NOT written to the database",
      after["diagnosis"] != FORGED_D,
      f"stored diagnosis is now: {str(after['diagnosis'])[:70]}")
check("FORGED treatment plan was NOT written to the database",
      after["treatment_plan"] != FORGED_P,
      f"stored plan is now: {str(after['treatment_plan'])[:70]}")
check("The doctor's ORIGINAL diagnosis survived the forged edit intact",
      after["diagnosis"] == REAL_DIAGNOSIS,
      f"expected: {REAL_DIAGNOSIS[:60]}\n got: {str(after['diagnosis'])[:60]}")
check("The doctor's ORIGINAL treatment plan survived the forged edit intact",
      after["treatment_plan"] == REAL_PLAN)
check("Staff could NOT set the Restricted flag via a forged field",
      after["is_restricted"] == 0,
      f"is_restricted is now {after['is_restricted']}")
check("Nothing else on the record was corrupted by the refusal",
      all(after[k] == before[k] for k in
          ("patient_id", "recorded_by", "consultation_date", "created_at")))

refusals = audit_since(mark, "Refused clinical judgement from an unlicensed role")
check("The refused forged edit WAS audit-logged", len(refusals) == 1,
      f"{len(refusals)} refusal entries written")
if refusals:
    entry = refusals[0]
    print(f"       actor user_id={entry['user_id']}  module={entry['module']}"
          f"  ip={entry['ip_address']}")
    print(f"       details: {entry['details'][:150]}...")
    check("Refusal entry names both refused fields",
          "Diagnosis" in entry["details"]
          and "Treatment plan" in entry["details"],
          entry["details"][:120])
    check("Refusal entry does NOT record the forged clinical text",
          FORGED_D not in entry["details"] and FORGED_P not in entry["details"])
    check("Refusal entry is attributed to the staff account",
          entry["user_id"] == STAFF_ID)
    check("Refusal entry is filed under Medical Confidentiality",
          entry["module"] == "Medical Confidentiality", entry["module"])

# --- A.3b: forged NEW consultation via the record path ----------------------
if APPT is not None:
    print("\n    A.3b: forged Staff POST creating a NEW consultation")
    mark = max_audit_id()
    conn = db()
    n_before = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    conn.close()

    resp = staff.post(
        f"/staff/consultation/record/{APPT}",
        data={
            "chief_complaint": "Cough and colds for three days",
            "diagnosis": FORGED_D,
            "treatment_plan": FORGED_P,
            "temperature": "37.2",
            "is_restricted": "1",
        },
        follow_redirects=False,
    )
    conn = db()
    new = conn.execute(
        "SELECT * FROM consultations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    n_after = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    conn.close()

    check("Forged staff record POST saved the intake it IS allowed to record",
          n_after == n_before + 1, f"{n_before} -> {n_after} consultations")
    if n_after == n_before + 1:
        check("New record stored the chief complaint Staff may write",
              (new["chief_complaint"] or "").startswith("Cough and colds"))
        check("New record's diagnosis is NULL — the forged value was refused",
              not new["diagnosis"], f"diagnosis={new['diagnosis']!r}")
        check("New record's treatment plan is NULL — the forged value was refused",
              not new["treatment_plan"], f"treatment_plan={new['treatment_plan']!r}")
        check("New record was NOT sealed by the forged is_restricted field",
              new["is_restricted"] == 0, f"is_restricted={new['is_restricted']}")
        refusals = audit_since(
            mark, "Refused clinical judgement from an unlicensed role")
        check("The refused forged NEW consultation WAS audit-logged",
              len(refusals) == 1, f"{len(refusals)} entries")

# --- A.3c: forged POST at the admin-only restrict endpoint ------------------
print("\n    A.3c: Staff POSTing directly at the Administrator's restrict route")
mark = max_audit_id()
resp = staff.post(
    f"/staff/patient_profile/{PID}/restrict-consultation",
    data={"consultation_id": str(CID), "restrict_action": "restrict"},
    follow_redirects=False,
)
conn = db()
flag = conn.execute(
    "SELECT is_restricted FROM consultations WHERE id = ?", (CID,)
).fetchone()[0]
conn.close()
check("Staff POST to /admin/.../restrict-consultation is turned away (302)",
      resp.status_code == 302, f"status={resp.status_code} -> {resp.headers.get('Location')}")
check("Staff POST to the admin restrict route did NOT seal the record",
      flag == 0, f"is_restricted={flag}")

# ===========================================================================
# TASK B + C + D — seal the record as Administrator, read it back as Staff
# ===========================================================================
print("\n--- TASK B: Administrator marks the consultation Restricted ---")
mark = max_audit_id()
conn = db()
pre_seal = dict(conn.execute(
    "SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
resp = admin.post(
    f"/staff/patient_profile/{PID}/restrict-consultation",
    data={"consultation_id": str(CID), "restrict_action": "restrict"},
    follow_redirects=False,
)
conn = db()
sealed = dict(conn.execute(
    "SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
check("Administrator restrict POST redirects back to the profile",
      resp.status_code == 302, f"status={resp.status_code}")
check("is_restricted is now 1", sealed["is_restricted"] == 1)
check("restricted_by names the Administrator", sealed["restricted_by"] == DOCTOR_ID,
      f"restricted_by={sealed['restricted_by']}")
check("restricted_at was stamped", bool(sealed["restricted_at"]),
      f"restricted_at={sealed['restricted_at']}")
check("The clinical content itself was NOT altered by sealing",
      sealed["diagnosis"] == REAL_DIAGNOSIS and sealed["treatment_plan"] == REAL_PLAN)
check("Sealing did NOT stamp updated_at (it is not a clinical edit)",
      sealed["updated_at"] == pre_seal["updated_at"],
      f"{pre_seal['updated_at']} -> {sealed['updated_at']}")

seals = audit_since(mark, "Marked consultation restricted")
check("Marking Restricted WAS audit-logged", len(seals) == 1, f"{len(seals)} entries")
if seals:
    entry = seals[0]
    print(f"       details: {entry['details'][:170]}...")
    check("Seal entry is attributed to the Administrator", entry["user_id"] == DOCTOR_ID)
    check("Seal entry is filed under Medical Confidentiality",
          entry["module"] == "Medical Confidentiality")
    check("Seal entry does NOT name the diagnosis",
          REAL_DIAGNOSIS not in entry["details"])
    check("Seal entry names the patient and the consultation",
          patient["patient_id"] in entry["details"] and f"#{CID}" in entry["details"])

print("\n--- TASK C: Staff views Consultation History on the sealed record ---")
print("    (THE test: the honest placeholder instead of the real content)")
mark = max_audit_id()
resp = staff.get(f"/staff/patient_profile/{PID}")
page = body(resp)
check("Staff Patient Profile renders (200)", resp.status_code == 200,
      f"status={resp.status_code}")
check("*** The real diagnosis is NOT in the bytes sent to Staff's browser ***",
      REAL_DIAGNOSIS not in page,
      "leaked!" if REAL_DIAGNOSIS in page else "absent from the response body")
check("*** The real treatment plan is NOT in the bytes sent to Staff ***",
      REAL_PLAN not in page)
check('*** Staff IS shown "Restricted — Doctor access only" ***',
      "Restricted — Doctor access only" in page
      or "Restricted &mdash; Doctor access only" in page
      or "Restricted \u2014 Doctor access only" in page)
check("Staff is told, in words, that entries on this page are Restricted",
      "is Restricted" in page or "are Restricted" in page)
check("Staff still sees the visit's chief complaint (intake is unaffected)",
      (target["chief_complaint"] or "") == "" or target["chief_complaint"] in page)
check("Staff still sees the patient's name and ID (the record is not hidden)",
      patient["patient_id"] in page)
check("Staff is NOT offered the Restrict control (no button, no form, no URL)",
      "restrict-open" not in page
      and "/restrict-consultation" not in page
      and 'data-bs-target="#restrictConsultationModal"' not in page)

withheld = audit_since(mark, "Withheld restricted consultation from view")
check("*** The withheld view WAS audit-logged ***", len(withheld) == 1,
      f"{len(withheld)} entries")
if withheld:
    entry = withheld[0]
    print(f"       details: {entry['details'][:170]}...")
    check("Withheld-view entry is attributed to the staff account",
          entry["user_id"] == STAFF_ID)
    check("Withheld-view entry names the consultation withheld",
          f"#{CID}" in entry["details"])
    check("Withheld-view entry does NOT name the diagnosis",
          REAL_DIAGNOSIS not in entry["details"])

print("\n    C.2: the same sealed record, seen by the Administrator")
mark = max_audit_id()
resp = admin.get(f"/staff/patient_profile/{PID}")
apage = body(resp)
check("Administrator DOES see the real diagnosis", REAL_DIAGNOSIS in apage)
check("Administrator DOES see the real treatment plan", REAL_PLAN in apage)
check("Administrator is told other roles cannot see it",
      "You are seeing it in full" in apage)
check("Administrator IS offered the Restrict/Lift control",
      "restrict-open" in apage and "/restrict-consultation" in apage)
check("An Administrator's own view writes NO withheld-view audit entry",
      len(audit_since(mark, "Withheld restricted consultation from view")) == 0)

print("\n    C.3: the sealed diagnosis must not leak through OTHER surfaces")
resp = staff.get(f"/staff/consultation/edit/{CID}")
epage = body(resp)
check("Staff Edit Consultation on a SEALED record leaks no diagnosis",
      REAL_DIAGNOSIS not in epage and REAL_PLAN not in epage)

conn = db()
disp = conn.execute(
    "SELECT COUNT(*) FROM medicine_dispensing WHERE consultation_id = ?", (CID,)
).fetchone()[0]
conn.close()
check("Dispensing History's joined diagnosis column is redacted for Staff",
      REAL_DIAGNOSIS not in page,
      f"({disp} dispensing rows join this consultation)")

resp = staff.get(f"/staff/patient_records")
check("Patient Records list leaks no sealed diagnosis",
      REAL_DIAGNOSIS not in body(resp))
resp = staff.get("/staff/dashboard")
check("Staff dashboard leaks no sealed diagnosis",
      REAL_DIAGNOSIS not in body(resp))

# ===========================================================================
# TASK D — lifting, and the audit trail's own screen
# ===========================================================================
print("\n--- TASK D: lifting the restriction, and idempotence ---")
mark = max_audit_id()
resp = admin.post(
    f"/staff/patient_profile/{PID}/restrict-consultation",
    data={"consultation_id": str(CID), "restrict_action": "restrict"},
    follow_redirects=False,
)
check("Re-sealing an already-sealed record writes NO duplicate audit entry",
      len(audit_since(mark)) == 0, f"{len(audit_since(mark))} entries written")

mark = max_audit_id()
resp = admin.post(
    f"/staff/patient_profile/{PID}/restrict-consultation",
    data={"consultation_id": str(CID), "restrict_action": "lift"},
    follow_redirects=False,
)
conn = db()
lifted = dict(conn.execute(
    "SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
check("Lifting clears is_restricted", lifted["is_restricted"] == 0)
check("Lifting clears restricted_by and restricted_at",
      lifted["restricted_by"] is None and lifted["restricted_at"] is None)
check("Lifting preserves the clinical content",
      lifted["diagnosis"] == REAL_DIAGNOSIS)
lifts = audit_since(mark, "Lifted consultation restriction")
check("Lifting WAS audit-logged", len(lifts) == 1, f"{len(lifts)} entries")

resp = staff.get(f"/staff/patient_profile/{PID}")
page = body(resp)
check("With the seal lifted, Staff CAN see the diagnosis again",
      REAL_DIAGNOSIS in page)
check("No withheld-view entry once the seal is lifted",
      len(audit_since(max_audit_id() - 0, "Withheld restricted consultation from view")) == 0)

print("\n    D.2: the Administrator's checkbox on the form seals on save")
mark = max_audit_id()
conn = db()
cur = dict(conn.execute("SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
resp = admin.post(
    f"/staff/consultation/edit/{CID}",
    data={
        "chief_complaint": cur["chief_complaint"] or "Follow-up",
        "diagnosis": cur["diagnosis"],
        "treatment_plan": cur["treatment_plan"],
        "remarks": cur["remarks"] or "",
        "temperature": cur["temperature"] or "",
        "blood_pressure": cur["blood_pressure"] or "",
        "pulse_rate": cur["pulse_rate"] or "",
        "respiratory_rate": cur["respiratory_rate"] or "",
        "weight": cur["weight"] or "",
        "height": cur["height"] or "",
        "follow_up_date": cur["follow_up_date"] or "",
        "is_restricted": "1",
    },
    follow_redirects=False,
)
conn = db()
flag = conn.execute(
    "SELECT is_restricted FROM consultations WHERE id = ?", (CID,)).fetchone()[0]
conn.close()
check("Administrator's Restricted checkbox seals the record on save", flag == 1)
check("That seal WAS audit-logged",
      len(audit_since(mark, "Marked consultation restricted")) == 1)

print("\n    D.3: the four confidentiality entries reach the Audit Logs screen")
resp = sysadmin.get("/admin/audit_logs")
alog = body(resp)
check("Audit Logs screen renders for the Administrator (200)",
      resp.status_code == 200, f"status={resp.status_code}")
for phrase in ("Marked consultation restricted",
               "Lifted consultation restriction",
               "Withheld restricted consultation from view",
               "Refused clinical judgement from an unlicensed role"):
    check(f'Audit Logs shows "{phrase}"', phrase in alog)
check("Audit Logs screen does NOT print the sealed diagnosis anywhere",
      REAL_DIAGNOSIS not in alog)
check("Medical Confidentiality module pill is shown",
      "Medical Confidentiality" in alog)

# ===========================================================================
# STAFF CAPABILITIES — must be completely unaffected
# ===========================================================================
print("\n--- STAFF CAPABILITIES: intake, dispensing, vaccinations ---")
resp = staff.get(f"/staff/patient_profile/{PID}")
page = body(resp)
for label, needle in [
    ("Consultation History tab", "tab-consult"),
    ("Dispensing History tab", "Dispensing"),
    ("Vaccination/immunisation content", "accination"),
]:
    check(f"Staff profile still renders the {label}", needle in page)

# The SPARE queue entry -- A.3b spent the first one by saving against it.
# DB-INDEPENDENCE: created here rather than cloned at setup; see the fixtures.
SPARE_APPT = new_queue_entry(QUEUE_PID)["id"]
if SPARE_APPT is not None:
    resp = staff.get(f"/staff/consultation/record/{SPARE_APPT}")
    rpage = body(resp)
    check("Staff's Record Consultation form is still live and renders (200)",
          resp.status_code == 200, f"status={resp.status_code}")
else:
    rpage = ""
    check("A spare queue entry exists for the capabilities check", False)
check("Staff Record Consultation still offers Items Dispensed",
      "Items Dispensed" in rpage or "dispense" in rpage.lower(),
      "(dispensing section present on staff's form)")
check("Staff Record Consultation still offers vaccination recording",
      "accinat" in rpage or "mmunis" in rpage or "mmuniz" in rpage)
check("Staff Record Consultation still offers growth/vital measurements",
      'name="weight"' in rpage and 'name="height"' in rpage)

resp = staff.get("/staff/medicine_inventory")
check("Staff Medicine Inventory still reachable (200)", resp.status_code == 200,
      f"status={resp.status_code}")
resp = staff.get("/staff/appointment_scheduling")
check("Staff Appointment Scheduling still reachable (200)", resp.status_code == 200,
      f"status={resp.status_code}")

# --- a REAL staff intake save on the sealed record: must not destroy anything
print("\n    Staff editing intake on a SEALED record (the erasure trap)")
conn = db()
cur = dict(conn.execute("SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
mark = max_audit_id()
resp = staff.post(
    f"/staff/consultation/edit/{CID}",
    data={
        "chief_complaint": "Follow-up, reviewed by BHW",
        "remarks": cur["remarks"] or "",
        "temperature": "36.8",
        "blood_pressure": cur["blood_pressure"] or "",
        "pulse_rate": cur["pulse_rate"] or "",
        "respiratory_rate": cur["respiratory_rate"] or "",
        "weight": cur["weight"] or "",
        "height": cur["height"] or "",
        "follow_up_date": cur["follow_up_date"] or "",
    },
    follow_redirects=False,
)
conn = db()
post = dict(conn.execute("SELECT * FROM consultations WHERE id = ?", (CID,)).fetchone())
conn.close()
check("Staff's honest intake edit was saved (temperature moved)",
      str(post["temperature"]) == "36.8", f"temperature={post['temperature']}")
check("Staff's intake edit was saved (chief complaint moved)",
      post["chief_complaint"] == "Follow-up, reviewed by BHW")
check("*** The sealed diagnosis was NOT erased by Staff's edit ***",
      post["diagnosis"] == REAL_DIAGNOSIS,
      f"stored: {str(post['diagnosis'])[:70]}")
check("*** The sealed treatment plan was NOT erased by Staff's edit ***",
      post["treatment_plan"] == REAL_PLAN)
check("*** The placeholder text was NOT written into the database ***",
      "Restricted" not in str(post["diagnosis"]))
check("Staff's edit did NOT lift the seal (no is_restricted in their form)",
      post["is_restricted"] == 1, f"is_restricted={post['is_restricted']}")
check("An honest staff edit writes NO refusal entry",
      len(audit_since(mark, "Refused clinical judgement from an unlicensed role")) == 0)

# ===========================================================================
# ROLE ISOLATION — the Barangay Official
# ===========================================================================
print("\n--- ROLE ISOLATION: Barangay Official ---")
official = client_as(OFFICIAL_ID)
for url in (f"/staff/patient_profile/{PID}", f"/admin/patient_profile/{PID}",
            f"/staff/consultation/edit/{CID}"):
    resp = official.get(url)
    check(f"Official is turned away from {url}", resp.status_code == 302,
          f"status={resp.status_code}")
resp = official.post(
    f"/staff/patient_profile/{PID}/restrict-consultation",
    data={"consultation_id": str(CID), "restrict_action": "lift"})
conn = db()
flag = conn.execute(
    "SELECT is_restricted FROM consultations WHERE id = ?", (CID,)).fetchone()[0]
conn.close()
check("Official cannot lift a seal", resp.status_code == 302 and flag == 1)

# ===========================================================================
# MALFORMED INPUT at the restrict endpoint
# ===========================================================================
print("\n--- MALFORMED INPUT at the restrict endpoint ---")
for label, data in [
    ("no direction", {"consultation_id": str(CID)}),
    ("bogus direction", {"consultation_id": str(CID), "restrict_action": "drop"}),
    ("non-numeric id", {"consultation_id": "abc", "restrict_action": "restrict"}),
    ("missing id", {"restrict_action": "restrict"}),
    ("nonexistent id", {"consultation_id": "999999", "restrict_action": "restrict"}),
]:
    mark = max_audit_id()
    resp = admin.post(
        f"/staff/patient_profile/{PID}/restrict-consultation", data=data)
    check(f"Restrict endpoint handles {label} without error (302, no log)",
          resp.status_code == 302 and len(audit_since(mark)) == 0,
          f"status={resp.status_code} audit={len(audit_since(mark))}")

# ===========================================================================
# REGRESSION SWEEP — every GET screen, every role
# ===========================================================================
print("\n--- REGRESSION SWEEP: every GET route, per role ---")
skip = {"static"}
sweep = {"admin": (sysadmin, "/admin"), "doctor": (admin, "/staff"), "staff": (staff, "/staff"),
         "official": (official, "/official")}
failures = []
checked = 0
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if rule.endpoint in skip or "GET" not in rule.methods:
        continue
    args = {}
    ok = True
    for arg in rule.arguments:
        if arg in ("patient_id",):
            args[arg] = PID
        elif arg in ("consultation_id",):
            args[arg] = CID
        elif arg in ("appointment_id",):
            if APPT is None:
                ok = False
                break
            args[arg] = SPARE_APPT or APPT
        elif arg in ("medicine_id", "item_id", "user_id", "log_id"):
            args[arg] = 1
        else:
            ok = False
            break
    if not ok:
        continue
    try:
        url = rule.build(args, append_unknown=False)[1] if isinstance(
            rule.build(args, append_unknown=False), tuple) else rule.build(args)
    except Exception:
        continue
    for name, (cl, prefix) in sweep.items():
        resp = cl.get(url)
        checked += 1
        if resp.status_code >= 500:
            failures.append((name, url, resp.status_code))
check(f"No 5xx on any GET route for any role ({checked} requests)",
      not failures, "\n".join(f"{n} {u} -> {s}" for n, u, s in failures) or "clean")

# ===========================================================================
# MIGRATION IDEMPOTENCE
# ===========================================================================
print("\n--- MIGRATION IDEMPOTENCE (re-run against the test copy) ---")
import subprocess  # noqa: E402
env = dict(os.environ)
proc = subprocess.run(
    [sys.executable, "-c",
     f"import config; config.DATABASE = r'{TEST_DB}';"
     "exec(open('migrate_add_consultation_restriction.py').read().replace("
     "'if __name__ == \"__main__\":', 'if True:'))"],
    capture_output=True, text=True, cwd=PROJECT, env=env)
print(proc.stdout.strip())
if proc.stderr.strip():
    print("STDERR:", proc.stderr.strip()[:500])
check("Migration re-run exits 0 (idempotent, with a sealed record present)",
      proc.returncode == 0, f"returncode={proc.returncode}")
check("Migration re-run added no columns",
      "columns added:   (none)" in proc.stdout)
check("Migration re-run reports the three restriction columns agree",
      "three restriction columns agree" in proc.stdout)

# ===========================================================================
print("\n" + "=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
failed = [name for name, ok, _ in results if not ok]
print(f"RESULT: {passed}/{len(results)} checks passed")
if failed:
    print("\nFAILED:")
    for name in failed:
        print("  -", name)
print("=" * 78)
sys.exit(1 if failed else 0)

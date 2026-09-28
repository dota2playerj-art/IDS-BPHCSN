"""End-to-end verification of the Doctor role and the clinical-authority move.

Runs the REAL application code over a fresh test database built by
tests/_support.py. Every assertion is made against an HTTP response body or
the database as the application left it. Nothing reaches into a view function.

Section H needs a seal set by the Administrator under the previous code.
It used to run that code from a git worktree. tests/ uses no worktrees, so
the same row state is written directly. The new code must then keep it
sealed from the Administrator.

usage: python tests/verify_doctor.py
"""
import io
import os
import re
import shutil
import sqlite3
import sys
import zlib

import _support  # noqa: E402  (first: builds the test database, points the app at it)
PROJECT = str(_support.REPO)
os.chdir(PROJECT)

TEST_DB = _support.DB_PATH

from openpyxl import load_workbook  # noqa: E402

from app import create_app  # noqa: E402

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


def q1(sql, args=()):
    conn = db()
    row = conn.execute(sql, args).fetchone()
    conn.close()
    return row


def snapshot():
    conn = sqlite3.connect(TEST_DB)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    snap = {t: sorted(conn.execute(f'SELECT * FROM "{t}"').fetchall()) for t in tables}
    conn.close()
    return snap


def snap_diff(before, after):
    """{table: (removed_rows, added_rows)} for every table that differs."""
    out = {}
    for table in set(before) | set(after):
        b, a = before.get(table, []), after.get(table, [])
        if b != a:
            sb, sa = set(b), set(a)
            out[table] = (sorted(sb - sa), sorted(sa - sb))
    return out


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
    return c


def body(resp):
    return resp.get_data(as_text=True)


def url(endpoint, **values):
    with app.test_request_context():
        from flask import url_for
        return url_for(endpoint, **values)


def pdf_text(data):
    out = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        chunk = match.group(1)
        try:
            out.append(zlib.decompress(chunk).decode("latin-1"))
        except Exception:
            out.append(chunk.decode("latin-1", "replace"))
    return "\n".join(out)


def xlsx_text(data):
    book = load_workbook(io.BytesIO(data), data_only=True)
    out = []
    for sheet in book.worksheets:
        for row in sheet.iter_rows(values_only=True):
            out.extend(str(cell) for cell in row if cell is not None)
    return "\n".join(out)


ADMIN_ID, STAFF_ID, OFFICIAL_ID = 1, 2, 3
DOCTOR_ID = q1("SELECT id FROM users WHERE username = 'doctor'")["id"]
PLACEHOLDER = "Restricted — Doctor access only"
DOCTOR_PASSWORD = _support.PASSWORDS["doctor"]

print("=" * 78)
print("IDS-BPHCSN — Doctor role / clinical authority verification")
print(f"database under test: {TEST_DB}")
print("=" * 78)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Distinctive text that cannot occur by coincidence, so "absent from the body"
# is exact: a hit is a leak.
HIST_DX = "SENTINEL-HIST-DX-4c1e written and sealed under the Administrator"
HIST_TX = "SENTINEL-HIST-TX-4c1e plan sealed under the Administrator"
DOC_DX = "SENTINEL-DOC-DX-9b2d HIV reactive, confirmatory assay positive"
DOC_TX = "SENTINEL-DOC-TX-9b2d start antiretroviral therapy, refer to hub"
CTRL_DX = "CONTROLDX7a1 ordinary unsealed finding"
CID_HIST, CID_DOC, CID_CTRL = 34, 36, 37
conn = db()
for cid, dx, tx in ((CID_HIST, HIST_DX, HIST_TX), (CID_DOC, DOC_DX, DOC_TX),
                    (CID_CTRL, CTRL_DX, "ordinary plan")):
    conn.execute("UPDATE consultations SET diagnosis=?, treatment_plan=? WHERE id=?",
                 (dx, tx, cid))
conn.commit()
PID_HIST = conn.execute("SELECT patient_id FROM consultations WHERE id=?", (CID_HIST,)).fetchone()[0]
PID_DOC = conn.execute("SELECT patient_id FROM consultations WHERE id=?", (CID_DOC,)).fetchone()[0]
PID_CTRL = conn.execute("SELECT patient_id FROM consultations WHERE id=?", (CID_CTRL,)).fetchone()[0]
conn.close()
print(f"historic-seal consultation #{CID_HIST} (patient id {PID_HIST}), "
      f"doctor-seal #{CID_DOC} (patient id {PID_DOC}), control #{CID_CTRL}")


def new_queue_entry(patient_id):
    conn = db()
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (?, 2, date('now','localtime'), "
        "'In Consultation', 1, datetime('now'))", (patient_id,))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


# ===========================================================================
section("H. A SEAL SET BY THE ADMINISTRATOR UNDER THE PREVIOUS CODE")
# MOVED INTO tests/ (2026-09-28): this step ran the PREVIOUS code from a git
# worktree, so the Administrator could seal through the old /admin route.
# tests/ uses no worktrees. The row that route wrote is written directly:
# sealed, with restricted_by = the Administrator. The one check that tested
# the old route itself is not run here.
conn = db()
conn.execute("UPDATE consultations SET is_restricted = 1, restricted_by = ?, "
             "restricted_at = '2026-09-20 10:00:00' WHERE id = ?",
             (ADMIN_ID, CID_HIST))
conn.commit()
conn.close()
hist = q1("SELECT * FROM consultations WHERE id=?", (CID_HIST,))
hist_row_before = tuple(hist)

admin, staff, official = client_as(ADMIN_ID), client_as(STAFF_ID), client_as(OFFICIAL_ID)

# ===========================================================================
section("D1. DOCTOR SIGNS IN THROUGH THE REAL FORM")
doctor = app.test_client()
r = doctor.post("/login", data={"username": "doctor", "password": DOCTOR_PASSWORD})
check("doctor sign-in redirects to the clinical dashboard",
      r.status_code == 302 and r.headers["Location"].endswith("/staff/dashboard"),
      f"{r.status_code} {r.headers.get('Location')}")
page = body(doctor.get("/staff/dashboard"))
check("dashboard is titled Doctor Dashboard, names the account and role",
      "Doctor Dashboard" in page and "RHU Physician (demo)" in page and ">Doctor<" in page)
check("sidebar: no Reports & Analytics, User Management, Audit Logs or Settings link",
      not any(link in page for link in ('href="/admin/reports_analytics"',
              'href="/admin/user_management"', 'href="/admin/audit_logs"',
              'href="/admin/settings"', 'href="/official/reports_analytics"')))

# ===========================================================================
section("D2. DOCTOR REACHES EXACTLY THE DESIGN-POINT-1 SCREENS")
with app.test_request_context():
    from routes.user_views import accessible_screens
    doc_screens = accessible_screens("Doctor")
    staff_screens = accessible_screens("Health Center Staff")
print("  doctor screens:", doc_screens)
# UPDATED FOR 445554e (2026-09-25): the team granted the Doctor Reports &
# Analytics, so the Doctor's list is now Health Center Staff's plus exactly the
# three labels that screen carries for the Administrator and the Barangay
# Official (the page and its two exports) -- and nothing else.
REPORTS_LABELS = {"Reports & Analytics", "Export Reports Analytics Excel",
                  "Export Reports Analytics Pdf"}
check("accessible_screens(Doctor) == Health Center Staff's + Reports & Analytics (3 labels)",
      set(doc_screens) == set(staff_screens) | REPORTS_LABELS
      and not (set(staff_screens) & REPORTS_LABELS)
      and len(doc_screens) == len(staff_screens) + 3, f"{doc_screens}\n{staff_screens}")
expected = {"Dashboard", "Patient Records", "Patient Profile", "Register Patient",
            "Appointment Scheduling", "Medicine Inventory", "Add / Edit Medicine",
            "Record Consultation", "Edit Consultation", "SMS Notifications"}
check("every design-point-1 screen is in the Doctor's list",
      expected <= set(doc_screens), sorted(expected - set(doc_screens)))
for path in ("/staff/patient_records", f"/staff/patient_profile/{PID_DOC}",
             "/staff/register-patient", "/staff/appointment_scheduling",
             "/staff/medicine_inventory", "/staff/sms_notifications",
             f"/staff/consultation/edit/{CID_CTRL}"):
    r = doctor.get(path)
    check(f"doctor GET {path} -> 200", r.status_code == 200, r.status_code)
sms = body(doctor.get("/staff/sms_notifications"))
check("SMS Notifications as staff sees it: no send/compose endpoint for Doctor",
      "/sms_notifications/send" not in sms)
for path in ("/admin/user_management", "/admin/audit_logs", "/admin/settings",
             "/admin/reports_analytics", "/admin/dashboard", "/official/dashboard",
             "/official/reports_analytics", "/admin/settings/backup.db",
             "/admin/audit_logs/export.xlsx"):
    r = doctor.get(path)
    check(f"doctor refused {path}", r.status_code == 302
          and r.headers["Location"].endswith("/dashboard"),
          f"{r.status_code} {r.headers.get('Location')}")
before = snapshot()
r = doctor.post("/admin/user_management/add", data={
    "full_name": "Should Not Exist", "username": "shouldnot", "role": "Admin",
    "password": "Morning-rounds-77", "confirm_password": "Morning-rounds-77"})
r2 = doctor.post("/admin/settings/maintenance", data={"action": "enable"})
r3 = doctor.post("/admin/settings/general", data={"name": "X"})
check("doctor's forged POSTs to Add User / Maintenance / Settings refused, nothing written",
      all(x.status_code == 302 and x.headers["Location"].endswith("/dashboard")
          for x in (r, r2, r3)) and snap_diff(before, snapshot()) == {},
      snap_diff(before, snapshot()))

# ===========================================================================
section("D3. WHO IS OFFERED THE DIAGNOSIS FIELDS ON RECORD CONSULTATION")
appt = new_queue_entry(PID_CTRL)
for who, client, prefix, should in (("doctor", doctor, "/staff", True),
                                    ("staff", staff, "/staff", False),
                                    ("admin", admin, "/admin", False)):
    page = body(client.get(f"{prefix}/consultation/record/{appt}"))
    has = 'name="diagnosis"' in page and 'name="treatment_plan"' in page
    seal = 'name="is_restricted"' in page
    check(f"{who}: diagnosis/treatment fields {'drawn' if should else 'absent'}, "
          f"seal box {'drawn' if should else 'absent'}",
          has == should and seal == should, f"fields={has} seal={seal}")
    if not should:
        check(f"{who}: form says the Doctor records the assessment",
              "recorded by the Doctor" in page)

# ===========================================================================
section("D4. DOCTOR RECORDS A DIAGNOSIS (record path, with the seal ticked)")
REC_DX = "SENTINEL-REC-DX-51f0 recorded by the doctor and sealed at once"
r = doctor.post(f"/staff/consultation/record/{appt}", data={
    "chief_complaint": "cough for three days", "diagnosis": REC_DX,
    "treatment_plan": "SENTINEL-REC-TX-51f0 rest", "is_restricted": "1"})
rec = q1("SELECT * FROM consultations WHERE appointment_id=?", (appt,))
check("doctor record saved (302 to profile)", r.status_code == 302, r.status_code)
check("stored diagnosis and plan are exactly the doctor's",
      rec is not None and rec["diagnosis"] == REC_DX
      and rec["treatment_plan"] == "SENTINEL-REC-TX-51f0 rest" and rec["recorded_by"] == DOCTOR_ID,
      dict(rec) if rec else None)
check("sealed from the form, restricted_by = Doctor",
      rec is not None and rec["is_restricted"] == 1 and rec["restricted_by"] == DOCTOR_ID)
CID_REC = rec["id"]

# ===========================================================================
section("D5. DOCTOR EDITS A DIAGNOSIS (edit path)")


def edit_form(cid, **overrides):
    row = dict(q1("SELECT * FROM consultations WHERE id=?", (cid,)))
    form = {}
    for field in ("chief_complaint", "diagnosis", "treatment_plan", "remarks",
                  "temperature", "blood_pressure", "pulse_rate", "respiratory_rate",
                  "weight", "height", "head_circumference", "follow_up_date"):
        value = row.get(field)
        if value is None:
            form[field] = ""
        elif isinstance(value, float):
            form[field] = f"{value:g}"
        else:
            form[field] = str(value)
    if row.get("is_restricted"):
        form["is_restricted"] = "1"
    form.update(overrides)
    return form


NEW_CTRL = CTRL_DX + " revised"
r = doctor.post(f"/staff/consultation/edit/{CID_CTRL}", data=edit_form(CID_CTRL, diagnosis=NEW_CTRL))
check("doctor edit stored the new diagnosis",
      q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_CTRL,))[0] == NEW_CTRL,
      f"{r.status_code} {q1('SELECT diagnosis FROM consultations WHERE id=?', (CID_CTRL,))[0]}")
CTRL_DX = NEW_CTRL

# ===========================================================================
section("D6. DOCTOR SEALS AND UNSEALS FROM THE PATIENT PROFILE")
prof = body(doctor.get(f"/staff/patient_profile/{PID_DOC}"))
check("doctor's profile offers the Restrict control", 'id="restrictConsultationModal"' in prof)
for who, client, prefix in (("admin", admin, "/admin"), ("staff", staff, "/staff")):
    p = body(client.get(f"{prefix}/patient_profile/{PID_DOC}"))
    check(f"{who}'s profile has no Restrict control", 'id="restrictConsultationModal"' not in p)
restrict_url = f"/staff/patient_profile/{PID_DOC}/restrict-consultation"
audit_mark = q1("SELECT MAX(id) FROM audit_logs")[0]
r = doctor.post(restrict_url, data={"consultation_id": str(CID_DOC), "restrict_action": "restrict"})
row = q1("SELECT * FROM consultations WHERE id=?", (CID_DOC,))
check("doctor sealed it", row["is_restricted"] == 1 and row["restricted_by"] == DOCTOR_ID,
      f"{r.status_code} {dict(row)}")
entries = db().execute("SELECT details FROM audit_logs WHERE id>?", (audit_mark,)).fetchall()
check("seal audited, without the sealed text",
      any("Marked Restricted" in e[0] for e in entries)
      and not any("SENTINEL-DOC" in e[0] for e in entries))
r = doctor.post(restrict_url, data={"consultation_id": str(CID_DOC), "restrict_action": "lift"})
check("doctor lifted it", q1("SELECT is_restricted FROM consultations WHERE id=?", (CID_DOC,))[0] == 0)
p = body(admin.get(f"/admin/patient_profile/{PID_DOC}"))
check("unsealed: the Administrator now sees the text (the flag, not the text, governs)",
      "SENTINEL-DOC-DX-9b2d" in p)
doctor.post(restrict_url, data={"consultation_id": str(CID_DOC), "restrict_action": "restrict"})
check("doctor re-sealed it", q1("SELECT is_restricted FROM consultations WHERE id=?", (CID_DOC,))[0] == 1)

# ===========================================================================
section("S. SEALED CONTENT: PLACEHOLDER FOR ADMIN AND STAFF, FULL FOR DOCTOR")
cases = (
    ("doctor-sealed", PID_DOC, CID_DOC, ("SENTINEL-DOC-DX-9b2d", "SENTINEL-DOC-TX-9b2d")),
    ("admin-sealed under old code", PID_HIST, CID_HIST, ("SENTINEL-HIST-DX-4c1e", "SENTINEL-HIST-TX-4c1e")),
    ("sealed at record time", PID_CTRL, CID_REC, ("SENTINEL-REC-DX-51f0", "SENTINEL-REC-TX-51f0")),
)
for label, pid, cid, sentinels in cases:
    for who, client, prefix in (("admin", admin, "/admin"), ("staff", staff, "/staff")):
        p = body(client.get(f"{prefix}/patient_profile/{pid}"))
        check(f"[{label}] {who} profile: placeholder shown, sealed text absent from raw body",
              PLACEHOLDER in p and not any(s in p for s in sentinels),
              [s for s in sentinels if s in p])
        e = client.get(f"{prefix}/consultation/edit/{cid}")
        eb = body(e)
        check(f"[{label}] {who} edit form: sealed text absent from raw body",
              e.status_code == 200 and not any(s in eb for s in sentinels),
              f"{e.status_code} {[s for s in sentinels if s in eb]}")
    p = body(doctor.get(f"/staff/patient_profile/{pid}"))
    check(f"[{label}] doctor profile: sealed text shown in full",
          all(s in p for s in sentinels), [s for s in sentinels if s not in p])
    e = body(doctor.get(f"/staff/consultation/edit/{cid}"))
    check(f"[{label}] doctor edit form: sealed text present to edit",
          sentinels[0] in e)
hist_after = q1("SELECT * FROM consultations WHERE id=?", (CID_HIST,))
check("historic seal row byte-identical after every role viewed it",
      tuple(hist_after) == hist_row_before)
withheld = db().execute(
    "SELECT COUNT(*) FROM audit_logs WHERE action = 'Withheld restricted consultation from view' "
    "AND user_id = ? AND details LIKE ?", (ADMIN_ID, f"%#{CID_DOC}%")).fetchone()[0]
check("an Administrator view that withheld the sealed record is audited", withheld >= 1)

# Dispensing History joins the diagnosis in; the consultation there has dispensing.
p = body(admin.get(f"/admin/patient_profile/{PID_DOC}?tab=medicine"))
check("Dispensing History: sealed diagnosis absent for admin (join redacted too)",
      "SENTINEL-DOC" not in p)

# ===========================================================================
section("F. FORGED REQUESTS FROM ADMINISTRATOR AND STAFF")
FORGED_DX = "FORGED-DX-e3a7 unlicensed guess"
FORGED_TX = "FORGED-TX-e3a7 unlicensed plan"

for who, client, prefix, uid in (("Administrator", admin, "/admin", ADMIN_ID),
                                 ("Staff", staff, "/staff", STAFF_ID)):
    print(f"\n  == {who} ==")
    # (a)/(b) on a SEALED record and on an UNSEALED one, via the edit path.
    for target in (CID_DOC, CID_CTRL):
        for field, forged in (("diagnosis", FORGED_DX), ("treatment_plan", FORGED_TX)):
            before_row = dict(q1("SELECT * FROM consultations WHERE id=?", (target,)))
            before = snapshot()
            form = edit_form(target)
            # A role that may not diagnose is never given the stored sealed text
            # to echo back; a forger replaying the form would not have it either.
            form.pop("diagnosis", None); form.pop("treatment_plan", None)
            form.pop("is_restricted", None)
            form[field] = forged
            r = client.post(f"{prefix}/consultation/edit/{target}", data=form)
            after_row = dict(q1("SELECT * FROM consultations WHERE id=?", (target,)))
            moved = sorted(k for k in before_row if before_row[k] != after_row[k])
            diff = snap_diff(before, snapshot())
            other_tables = sorted(t for t in diff if t not in ("audit_logs", "sqlite_sequence"))
            seq_moved = [row[0] for row in diff.get("sqlite_sequence", ([], []))[1]]
            refusal = [row for row in diff.get("audit_logs", ([], []))[1]
                       if "Refused clinical judgement" in str(row)]
            check(f"{who} forged {field} on #{target}: refused, "
                  f"{field} byte-identical ({FORGED_DX[:9]} absent)",
                  after_row[field] == before_row[field]
                  and after_row["diagnosis"] == before_row["diagnosis"]
                  and after_row["treatment_plan"] == before_row["treatment_plan"]
                  and FORGED_DX not in str(after_row) and FORGED_TX not in str(after_row),
                  f"{r.status_code} moved={moved}")
            check(f"{who} forged {field} on #{target}: consultation row byte-identical, "
                  "no clinical table touched; the only write is one refusal audit row "
                  "(and its AUTOINCREMENT counter), which does not contain the forged text",
                  moved == [] and not other_tables and seq_moved in ([], ["audit_logs"])
                  and len(refusal) == 1 and len(diff.get("audit_logs", ([], []))[1]) == 1
                  and "FORGED" not in str(refusal),
                  f"moved={moved} tables={sorted(diff)} seq={seq_moved} refusal={len(refusal)}")
            print(f"        (row columns that moved: {moved or 'none'})")

    # (a) via the record path: a NEW visit carries a forged diagnosis.
    appt_f = new_queue_entry(PID_CTRL)
    before = snapshot()
    r = client.post(f"{prefix}/consultation/record/{appt_f}", data={
        "chief_complaint": "forged record probe", "diagnosis": FORGED_DX,
        "treatment_plan": FORGED_TX, "is_restricted": "1"})
    new = q1("SELECT * FROM consultations WHERE appointment_id=?", (appt_f,))
    check(f"{who} forged record: intake saved, diagnosis/plan NULL, not sealed",
          new is not None and new["diagnosis"] is None and new["treatment_plan"] is None
          and new["is_restricted"] == 0 and FORGED_DX not in str(dict(new)),
          dict(new) if new else r.status_code)

    # (c) seal: the Doctor's route, the removed /admin route, and the edit checkbox.
    for sealed_target, pid, action in ((CID_CTRL, PID_CTRL, "restrict"),
                                       (CID_DOC, PID_DOC, "lift")):
        before = snapshot()
        r1 = client.post(f"/staff/patient_profile/{pid}/restrict-consultation",
                         data={"consultation_id": str(sealed_target), "restrict_action": action})
        r2 = client.post(f"/admin/patient_profile/{pid}/restrict-consultation",
                         data={"consultation_id": str(sealed_target), "restrict_action": action})
        diff = snap_diff(before, snapshot())
        check(f"{who} forged seal ({action}) on #{sealed_target}: both URLs refused, "
              "database byte-identical",
              r1.status_code == 302 and r1.headers["Location"].endswith("/dashboard")
              and r2.status_code in (404, 405) and diff == {},
              f"doctor-route {r1.status_code} {r1.headers.get('Location')}; "
              f"old-admin-route {r2.status_code}; diff={sorted(diff)}")
    seal_cols = "is_restricted, restricted_by, restricted_at"
    for target, box in ((CID_CTRL, {"is_restricted": "1"}), (CID_DOC, {})):
        before_seal = tuple(q1(f"SELECT {seal_cols} FROM consultations WHERE id=?", (target,)))
        form = edit_form(target)
        form.pop("diagnosis", None); form.pop("treatment_plan", None)
        form.pop("is_restricted", None)
        form.update(box)
        client.post(f"{prefix}/consultation/edit/{target}", data=form)
        after_seal = tuple(q1(f"SELECT {seal_cols} FROM consultations WHERE id=?", (target,)))
        check(f"{who} edit form {'ticking' if box else 'unticking'} the seal on #{target}: "
              "seal columns byte-identical", before_seal == after_seal,
              f"{before_seal} -> {after_seal}")

    # (d) Deceased: set it, and reverse it.
    active_pid = q1("SELECT id FROM patients WHERE status='Active' ORDER BY id LIMIT 1")[0]
    deceased_pid = q1("SELECT id FROM patients WHERE status='Deceased' ORDER BY id LIMIT 1")[0]
    for pid, status in ((active_pid, "Deceased"), (deceased_pid, "Active"),
                        (deceased_pid, "Inactive")):
        before = snapshot()
        r = client.post(f"{prefix}/patient_records/archive",
                        data={"single_patient_id": str(pid), "status": status})
        diff = snap_diff(before, snapshot())
        flashed = ""
        with client.session_transaction() as sess:
            flashed = str(sess.get("_flashes", ""))
        check(f"{who} forged status {status} on patient {pid}: refused, database byte-identical",
              diff == {} and "Only the Doctor" in flashed, f"diff={sorted(diff)} flash={flashed[:160]}")
    # bulk path too
    before = snapshot()
    client.post(f"{prefix}/patient_records/archive",
                data={"patient_ids": [str(active_pid)], "status": "Deceased"})
    check(f"{who} forged bulk Deceased: database byte-identical", snap_diff(before, snapshot()) == {})
    # Active <-> Inactive still works for this role.
    client.post(f"{prefix}/patient_records/archive",
                data={"single_patient_id": str(active_pid), "status": "Inactive"})
    ok1 = q1("SELECT status FROM patients WHERE id=?", (active_pid,))[0] == "Inactive"
    client.post(f"{prefix}/patient_records/archive",
                data={"single_patient_id": str(active_pid), "status": "Active"})
    ok2 = q1("SELECT status FROM patients WHERE id=?", (active_pid,))[0] == "Active"
    check(f"{who} can still move Active -> Inactive -> Active", ok1 and ok2)
    page = body(client.get(f"{prefix}/patient_records"))
    check(f"{who}'s status dialog draws no Mark Deceased button",
          'value="Deceased"' not in page and 'id="archiveDoctorOnly"' in page)

# Positive control: the SAME forged-shape request from the Doctor does write,
# which is what shows the refusals above are the permission and not the harness.
form = edit_form(CID_CTRL)
form.pop("is_restricted", None)
form["diagnosis"] = CTRL_DX + " by doctor"
doctor.post(f"/staff/consultation/edit/{CID_CTRL}", data=form)
check("control: the same edit from the Doctor writes the diagnosis",
      q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_CTRL,))[0] == CTRL_DX + " by doctor")
CTRL_DX = CTRL_DX + " by doctor"

# ===========================================================================
section("D7. DOCTOR SETS AND REVERSES DECEASED")
page = body(doctor.get("/staff/patient_records"))
check("doctor's status dialog draws Mark Deceased", 'value="Deceased"' in page)
active_pid = q1("SELECT id FROM patients WHERE status='Active' ORDER BY id LIMIT 1")[0]
doctor.post("/staff/patient_records/archive", data={"single_patient_id": str(active_pid), "status": "Deceased"})
check("doctor marked patient Deceased", q1("SELECT status FROM patients WHERE id=?", (active_pid,))[0] == "Deceased")
doctor.post("/staff/patient_records/archive", data={"single_patient_id": str(active_pid), "status": "Active"})
check("doctor reversed Deceased -> Active", q1("SELECT status FROM patients WHERE id=?", (active_pid,))[0] == "Active")

# ===========================================================================
section("A. AUDIT TRAIL NEVER QUOTES SEALED TEXT TO THE ADMINISTRATOR")
EDIT_DX = "SENTINEL-EDIT-DX-77aa revised sealed assessment"
mark = q1("SELECT MAX(id) FROM audit_logs")[0]
doctor.post(f"/staff/consultation/edit/{CID_DOC}", data=edit_form(CID_DOC, diagnosis=EDIT_DX))
check("doctor's edit of the sealed diagnosis stored",
      q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_DOC,))[0] == EDIT_DX)
entry = q1("SELECT details FROM audit_logs WHERE id>? AND action='Updated consultation record' "
           "ORDER BY id DESC", (mark,))
if entry is None:
    entry = q1("SELECT details FROM audit_logs WHERE id>? ORDER BY id DESC", (mark,))
check("edit entry names the change but quotes neither old nor new sealed text",
      entry is not None and "[withheld — Restricted]" in entry[0]
      and "SENTINEL" not in entry[0], entry[0] if entry else None)
audit_page = body(admin.get("/admin/audit_logs"))
x = admin.get("/admin/audit_logs/export.xlsx").data
pdf = admin.get("/admin/audit_logs/export.pdf").data
xt, pt = xlsx_text(x), pdf_text(pdf)
check("control: the unsealed diagnosis edit IS quoted in page, xlsx and pdf (extraction works)",
      "CONTROLDX7a1" in audit_page and "CONTROLDX7a1" in xt and "CONTROLDX7a1" in pt,
      f"page={'CONTROLDX7a1' in audit_page} xlsx={'CONTROLDX7a1' in xt} pdf={'CONTROLDX7a1' in pt}")
check("no sealed sentinel in Audit Logs page, xlsx or pdf",
      not any("SENTINEL" in s for s in (audit_page, xt, pt)))

# ===========================================================================
section("R. TOP-DIAGNOSES AGGREGATE NEVER REVEALS SEALED TEXT")
conn = db()
conn.execute("UPDATE consultations SET consultation_date='2026-08-28' WHERE id IN (?,?,?)",
             (CID_DOC, CID_HIST, CID_CTRL))
conn.commit(); conn.close()
rng = "?from=2026-08-28&to=2026-08-28"
surfaces = [
    ("admin Reports", admin, "/admin/reports_analytics" + rng),
    ("admin Reports xlsx", admin, url("admin.export_reports_analytics_excel") + rng),
    ("admin Reports pdf", admin, url("admin.export_reports_analytics_pdf") + rng),
    ("official Reports", official, "/official/reports_analytics" + rng),
    ("official Community Reports", official, url("official.community_reports") + rng),
    ("official Community xlsx", official, url("official.export_community_reports_excel") + rng),
]
for label, client, path in surfaces:
    resp = client.get(path)
    data = resp.data
    text = (xlsx_text(data) if path.split("?")[0].endswith(".xlsx")
            else pdf_text(data) if path.split("?")[0].endswith(".pdf") else body(resp))
    low = text.lower()
    check(f"{label}: control diagnosis ranked, no sealed sentinel",
          resp.status_code == 200 and "controldx7a1" in low and "sentinel" not in low,
          f"{resp.status_code} control={'controldx7a1' in low} sealed={'sentinel' in low}")

# ===========================================================================
section("M. MAINTENANCE MODE BLOCKS THE DOCTOR, NOT THE ADMINISTRATOR")
admin.post("/admin/settings/maintenance", data={"action": "enable"})
r = doctor.get("/staff/dashboard")
check("doctor gets the 503 maintenance page", r.status_code == 503, r.status_code)
fresh = app.test_client()
r = fresh.post("/login", data={"username": "doctor", "password": DOCTOR_PASSWORD})
check("doctor cannot sign in during maintenance",
      not (r.status_code == 302 and r.headers.get("Location", "").endswith("/staff/dashboard")),
      f"{r.status_code} {r.headers.get('Location')}")
check("administrator unaffected", admin.get("/admin/dashboard").status_code == 200)
admin.post("/admin/settings/maintenance", data={"action": "disable"})
check("doctor back after maintenance is lifted", doctor.get("/staff/dashboard").status_code == 200)

# ===========================================================================
section("P. ADMINISTRATOR KEEPS EVERY SYSTEM-ADMINISTRATION POWER")
for path in ("/admin/user_management", "/admin/audit_logs", "/admin/settings",
             "/admin/reports_analytics", "/admin/dashboard"):
    check(f"admin GET {path} -> 200", admin.get(path).status_code == 200)
b = admin.get("/admin/settings/backup.db")
check("admin backup download is a real SQLite file",
      b.status_code == 200 and b.data[:15] == b"SQLite format 3")
r = admin.post("/admin/user_management/add", data={
    "full_name": "Second Physician", "username": "drsecond", "role": "Doctor",
    "password": "Morning-rounds-77", "confirm_password": "Morning-rounds-77"})
new_doc = q1("SELECT id, role FROM users WHERE username='drsecond'")
check("admin Add User creates a Doctor", new_doc is not None and new_doc["role"] == "Doctor")
admin.post("/admin/user_management/edit", data={"user_id": new_doc["id"],
           "full_name": "Second Physician", "role": "Health Center Staff"})
check("admin Edit User changes the role",
      q1("SELECT role FROM users WHERE id=?", (new_doc["id"],))[0] == "Health Center Staff")
admin.post("/admin/user_management/reset_password", data={"user_id": new_doc["id"],
           "password": "Evening-rounds-88", "confirm_password": "Evening-rounds-88"})
t = app.test_client()
rr = t.post("/login", data={"username": "drsecond", "password": "Evening-rounds-88"})
check("admin Reset Password works (new password signs in)", rr.status_code == 302
      and rr.headers["Location"].endswith("/staff/dashboard"))
admin.post("/admin/user_management/status", data={"user_id": new_doc["id"], "action": "deactivate"})
d1 = q1("SELECT is_active FROM users WHERE id=?", (new_doc["id"],))[0]
admin.post("/admin/user_management/status", data={"user_id": new_doc["id"], "action": "reactivate"})
d2 = q1("SELECT is_active FROM users WHERE id=?", (new_doc["id"],))[0]
check("admin can deactivate and reactivate", d1 == 0 and d2 == 1)
before = snapshot()
admin.post("/admin/user_management/status", data={"user_id": ADMIN_ID, "action": "deactivate"})
admin.post("/admin/user_management/edit", data={"user_id": ADMIN_ID,
           "full_name": "Kagawad Antonio Acido", "role": "Doctor"})
after_admin = q1("SELECT role, is_active FROM users WHERE id=?", (ADMIN_ID,))
check("last-Administrator guard: cannot deactivate or demote (not even to Doctor)",
      tuple(after_admin) == ("Admin", 1)
      and "users" not in snap_diff(before, snapshot()), tuple(after_admin))

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print("  FAILED:", name)
print("=" * 78)
sys.exit(0 if not failed else 1)

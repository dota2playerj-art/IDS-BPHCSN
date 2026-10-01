"""Sealed record privacy (H4, L2; RA 11166 Section 44, RA 10173).

Checks that a sealed consultation's diagnosis and treatment plan are encrypted
in the database, that only the Doctor's screens ever show them, that no export,
print, report, audit entry or backup carries them, and that a wrong key fails
with a plain message instead of a crash.

Runs on a fresh test database built by tests/_support.py, with a test-only key.
Every "absent" check has a positive control: an unsealed sentinel that must be
found by the same extraction. Sentinels are single tokens, so a PDF line break
cannot split one and hide a leak.
"""
import ast
import base64
import contextlib
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zlib
from pathlib import Path

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
REPO = Path(_support.REPO)
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5
UNOPENABLE = "This sealed record cannot be opened on this computer."
PLACEHOLDER = "Restricted — Doctor access only"

DX_REC, TX_REC = "ZZSEALREC1DX", "ZZSEALREC1TX"
DX_LATE, TX_LATE = "ZZSEALLATE2DX", "ZZSEALLATE2TX"
DX_LATE_EDIT = "ZZSEALLATE2EDITDX"
DX_CTRL = "ZZOPENCTRL3DX"
SEALED_SENTINELS = (DX_REC, TX_REC, DX_LATE, TX_LATE, DX_LATE_EDIT)

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


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def body(response):
    return response.get_data(as_text=True)


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


def readable(response):
    """Everything a person could read in a response: page text, workbook, PDF."""
    data = response.data
    kind = response.headers.get("Content-Type", "")
    if "spreadsheetml" in kind:
        return xlsx_text(data)
    if "pdf" in kind:
        return pdf_text(data) + data.decode("latin-1")
    return data.decode("utf-8", "replace")


def leaks(text):
    return [s for s in SEALED_SENTINELS if s in text]


def new_queue_entry(patient_id):
    conn = db()
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_date, "
        "status, is_walkin, checked_in_at) VALUES (?, ?, date('now','localtime'), "
        "'In Consultation', 1, datetime('now','localtime'))", (patient_id, STAFF_ID))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def edit_form(cid, **overrides):
    row = dict(q1("SELECT * FROM consultations WHERE id=?", (cid,)))
    form = {}
    for field in ("chief_complaint", "diagnosis", "treatment_plan", "remarks",
                  "temperature", "blood_pressure", "pulse_rate", "respiratory_rate",
                  "weight", "height", "head_circumference", "follow_up_date"):
        value = row.get(field)
        form[field] = "" if value is None else (f"{value:g}" if isinstance(value, float)
                                                 else str(value))
    if row.get("is_restricted"):
        form["is_restricted"] = "1"
    form.update(overrides)
    return form


def audit_max():
    return q1("SELECT COALESCE(MAX(id), 0) FROM audit_logs")[0]


admin, staff, official, doctor = (client_as(i) for i in
                                  (ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID))
from utils import sealed_crypto as sc  # noqa: E402

print("=" * 78)
print("IDS-BPHCSN — sealed record privacy (H4, L2)")
print("=" * 78)

# ===========================================================================
section("1. THE ENCRYPTION MODULE")
token = sc.encrypt("Sample sealed text", 7, "diagnosis")
check("a value encrypts to the versioned format enc:v1:", token.startswith("enc:v1:"))
check("and decrypts back for the same row and field",
      sc.decrypt(token, 7, "diagnosis") == "Sample sealed text")
raw = base64.b64decode(token[len("enc:v1:"):])
check("the stored value holds a 96-bit nonce, the text and a 16-byte tag",
      len(raw) == 12 + len("Sample sealed text".encode()) + 16, len(raw))
check("the same text encrypts differently each time (fresh nonce)",
      sc.encrypt("Sample sealed text", 7, "diagnosis") != token)


def refuses(call):
    try:
        call()
    except sc.SealedDataError:
        return True
    return False


check("a value moved to another row does not decrypt",
      refuses(lambda: sc.decrypt(token, 8, "diagnosis")))
check("a value moved to another field does not decrypt",
      refuses(lambda: sc.decrypt(token, 7, "treatment_plan")))
check("a damaged value does not decrypt",
      refuses(lambda: sc.decrypt(token[:-6] + "AAAAAA", 7, "diagnosis")))
check("None and empty text are left as they are",
      sc.encrypt(None, 7, "diagnosis") is None and sc.encrypt("", 7, "diagnosis") == "")
check("key_problem() refuses a missing, non-base64 or 16-byte key",
      sc.key_problem("") and sc.key_problem("not base64!!")
      and sc.key_problem(base64.b64encode(os.urandom(16)).decode()))
check("key_problem() accepts a 32-byte key", sc.key_problem(sc.new_key()) is None)

# ===========================================================================
section("2. STARTUP, setup_env.py AND export_sealed_key.py")


def start_app(env_changes):
    env = dict(os.environ)
    env.update(env_changes)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, "-c", "import app; print('STARTED')"],
                          cwd=REPO, env=env, capture_output=True, text=True,
                          encoding="utf-8")
    return proc.returncode, proc.stdout + proc.stderr


for label, value in (("missing", ""),
                     ("16 bytes", base64.b64encode(os.urandom(16)).decode()),
                     ("not base64", "%%%%")):
    code, out = start_app({"SEALED_DATA_KEY": value})
    check(f"the app refuses to start when SEALED_DATA_KEY is {label}",
          code != 0 and "STARTED" not in out and "cannot start" in out
          and "SEALED_DATA_KEY" in out, out[-300:])
code, out = start_app({"SEALED_DATA_KEY": sc.new_key()})
check("the app starts with a proper 32-byte key", code == 0 and "STARTED" in out, out[-300:])

import setup_env  # noqa: E402

env_path = Path(_support.work_path("existing.env"))
old_secret = "f" * 64
env_path.write_text(f"# old file\nSECRET_KEY={old_secret}\nIDS_DEBUG=0\n", encoding="utf-8")
setup_env.ENV_FILE = env_path
printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    setup_env.main()
written = env_path.read_text(encoding="utf-8")
key_line = re.search(r"^SEALED_DATA_KEY=(\S+)$", written, re.M)
check("setup_env.py adds SEALED_DATA_KEY to an existing .env",
      key_line is not None and sc.key_problem(key_line.group(1)) is None, written)
check("and leaves SECRET_KEY and the rest exactly as they were",
      written.startswith(f"# old file\nSECRET_KEY={old_secret}\nIDS_DEBUG=0\n"))
check("and never prints the key",
      key_line is not None and key_line.group(1) not in printed.getvalue())
again = io.StringIO()
with contextlib.redirect_stdout(again):
    setup_env.main()
check("a second run changes nothing", env_path.read_text(encoding="utf-8") == written
      and "Nothing was changed" in again.getvalue())
new_path = Path(_support.work_path("new.env"))
setup_env.ENV_FILE = new_path
with contextlib.redirect_stdout(io.StringIO()):
    setup_env.main()
fresh = new_path.read_text(encoding="utf-8")
check("a new .env gets both keys",
      re.search(r"^SECRET_KEY=[0-9a-f]{64}$", fresh, re.M) is not None
      and re.search(r"^SEALED_DATA_KEY=\S+$", fresh, re.M) is not None)
example = (REPO / ".env.example").read_text(encoding="utf-8")
check(".env.example names SEALED_DATA_KEY with no value",
      re.search(r"^SEALED_DATA_KEY=\s*$", example, re.M) is not None)

import export_sealed_key  # noqa: E402

export_sealed_key.ENV_FILE = env_path
the_key = key_line.group(1) if key_line else "missing"
folder = sorted(os.listdir(env_path.parent))
shown = io.StringIO()
with contextlib.redirect_stdout(shown):
    refused = export_sealed_key.main(read=lambda _prompt: "no")
check("export_sealed_key.py shows nothing unless YES is typed",
      refused == 1 and the_key not in shown.getvalue())
shown = io.StringIO()
with contextlib.redirect_stdout(shown):
    accepted = export_sealed_key.main(read=lambda _prompt: "YES")
check("after YES it prints the key with the envelope instructions",
      accepted == 0 and the_key in shown.getvalue() and "envelope" in shown.getvalue()
      and "Doctor" in shown.getvalue())
check("and writes nothing to disk", sorted(os.listdir(env_path.parent)) == folder)

# ===========================================================================
section("3. SEALING, UNSEALING AND EDITING THROUGH THE REAL ROUTES")
P_REC = 9
appt = new_queue_entry(P_REC)
r = doctor.post(f"/staff/consultation/record/{appt}", data={
    "chief_complaint": "Follow-up visit", "temperature": "36.9", "weight": "60",
    "diagnosis": DX_REC, "treatment_plan": TX_REC, "is_restricted": "1"})
CID_REC = q1("SELECT id FROM consultations WHERE appointment_id = ?", (appt,))[0]
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_REC,))
check("sealed at record time: both fields are stored encrypted",
      row["is_restricted"] == 1 and row["restricted_by"] == DOCTOR_ID
      and sc.is_encrypted(row["diagnosis"]) and sc.is_encrypted(row["treatment_plan"]),
      dict(row))
check("and they decrypt to what the Doctor typed",
      sc.decrypt(row["diagnosis"], CID_REC, "diagnosis") == DX_REC
      and sc.decrypt(row["treatment_plan"], CID_REC, "treatment_plan") == TX_REC)
profile = body(doctor.get(f"/staff/patient_profile/{P_REC}"))
check("L2: the seal message says the text is hidden from everyone except the Doctor",
      "hidden from everyone except the Doctor" in profile, profile[:200])
check("the Doctor's profile shows the sealed text", DX_REC in profile and TX_REC in profile)

CID_LATE = 10
P_LATE = q1("SELECT patient_id FROM consultations WHERE id = ?", (CID_LATE,))[0]
doctor.post(f"/staff/consultation/edit/{CID_LATE}",
            data=edit_form(CID_LATE, diagnosis=DX_LATE, treatment_plan=TX_LATE))
check("before sealing, an ordinary record holds plain text",
      q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_LATE,))[0] == DX_LATE)
restrict_url = f"/staff/patient_profile/{P_LATE}/restrict-consultation"
doctor.post(restrict_url, data={"consultation_id": str(CID_LATE), "restrict_action": "restrict"})
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_LATE,))
first_cipher = row["diagnosis"]
check("sealing encrypts both fields in the database",
      row["is_restricted"] == 1 and sc.is_encrypted(row["diagnosis"])
      and sc.is_encrypted(row["treatment_plan"]) and DX_LATE not in row["diagnosis"])
doctor.post(restrict_url, data={"consultation_id": str(CID_LATE), "restrict_action": "lift"})
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_LATE,))
check("lifting the seal restores the plain text",
      row["is_restricted"] == 0 and row["diagnosis"] == DX_LATE
      and row["treatment_plan"] == TX_LATE, dict(row))
doctor.post(restrict_url, data={"consultation_id": str(CID_LATE), "restrict_action": "restrict"})
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_LATE,))
check("sealing again encrypts again, with a new nonce",
      sc.is_encrypted(row["diagnosis"]) and row["diagnosis"] != first_cipher)

plan_before = row["treatment_plan"]
doctor.post(f"/staff/consultation/edit/{CID_LATE}",
            data=edit_form(CID_LATE, diagnosis=DX_LATE_EDIT, treatment_plan=TX_LATE))
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_LATE,))
check("a Doctor edit of a sealed record stays encrypted",
      row["is_restricted"] == 1 and sc.is_encrypted(row["diagnosis"])
      and sc.decrypt(row["diagnosis"], CID_LATE, "diagnosis") == DX_LATE_EDIT)
check("a field the Doctor left alone keeps its stored ciphertext",
      row["treatment_plan"] == plan_before)
sealed_now = (row["diagnosis"], row["treatment_plan"])
staff.post(f"/staff/consultation/edit/{CID_LATE}",
           data={k: v for k, v in edit_form(CID_LATE, temperature="37.5").items()
                 if k not in ("diagnosis", "treatment_plan", "is_restricted")})
row = q1("SELECT * FROM consultations WHERE id = ?", (CID_LATE,))
check("a staff edit of a sealed record leaves both encrypted fields byte for byte",
      (row["diagnosis"], row["treatment_plan"]) == sealed_now and row["is_restricted"] == 1
      and row["temperature"] == 37.5)

CID_CTRL = 11
P_CTRL = q1("SELECT patient_id FROM consultations WHERE id = ?", (CID_CTRL,))[0]
doctor.post(f"/staff/consultation/edit/{CID_CTRL}", data=edit_form(CID_CTRL, diagnosis=DX_CTRL))
check("control: an unsealed record keeps plain text",
      q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_CTRL,))[0] == DX_CTRL)

# ===========================================================================
section("4. ONLY THE DOCTOR'S SCREENS SHOW SEALED TEXT")
plain_gets = sorted({rule.rule for rule in app.url_map.iter_rules()
                     if "GET" in rule.methods and not rule.arguments
                     and not rule.rule.startswith("/static")
                     and rule.rule not in ("/logout",)})
check("the crawl covers the app's GET screens and exports", len(plain_gets) > 40,
      len(plain_gets))
for who, client, prefix in (("Administrator", admin, "/admin"), ("Health Center Staff", staff, "/staff"),
                            ("Barangay Official", official, "/official"), ("Doctor", doctor, "/staff")):
    found = []
    for url in plain_gets:
        response = client.get(url)
        hits = leaks(readable(response))
        if hits:
            found.append(f"{url}: {hits}")
    check(f"{who}: no sealed text on any screen, export or download without an id",
          not found, "\n".join(found))
    if who in ("Barangay Official",):
        continue
    for pid in (P_REC, P_LATE):
        for url in (f"{prefix}/patient_profile/{pid}", f"{prefix}/patient_profile/{pid}?print=1"):
            page = body(client.get(url))
            if who == "Doctor":
                screen_only = re.sub(r'<span class="no-print">.*?</span>', "", page, flags=re.S)
                check(f"Doctor: {url} shows sealed text on screen, never on paper",
                      leaks(page) and not leaks(screen_only)
                      and f'<span class="print-only">{PLACEHOLDER}</span>' in page,
                      leaks(screen_only))
            else:
                check(f"{who}: {url} shows the placeholder, not the text",
                      not leaks(page) and PLACEHOLDER in page, leaks(page))
    for cid in (CID_REC, CID_LATE):
        page = body(client.get(f"{prefix}/consultation/edit/{cid}"))
        if who == "Doctor":
            check(f"Doctor: the edit form for #{cid} shows the sealed text to edit",
                  any(s in page for s in SEALED_SENTINELS))
        else:
            check(f"{who}: the edit form for #{cid} carries no sealed text",
                  not leaks(page), leaks(page))
    for kind in ("xlsx", "pdf"):
        response = client.post(f"{prefix}/patient_records/export-selection.{kind}",
                               data={"patient_ids": [str(P_REC), str(P_LATE)]})
        check(f"{who}: the selection export ({kind}) carries no sealed text",
              not leaks(readable(response)), response.status_code)
r = doctor.post("/session/keep-alive", headers={"X-Requested-With": "fetch"})
check("the keep-alive (JSON) response carries no sealed text", not leaks(body(r)))
page = body(admin.get(f"/admin/patient_profile/{P_CTRL}"))
check("control: an unsealed diagnosis is shown to the Administrator", DX_CTRL in page)

# ===========================================================================
section("5. THE KEY TEST: THE BACKUP DOWNLOAD HOLDS NO SEALED TEXT")
response = admin.get("/admin/settings/backup.db")
data = response.data
check("the Administrator's backup route answers with a database file",
      response.status_code == 200 and data[:16] == b"SQLite format 3\x00", response.status_code)
check("control: the unsealed sentinel IS found in the backup bytes", DX_CTRL.encode() in data)
check("*** no sealed sentinel appears anywhere in the backup bytes ***",
      not [s for s in SEALED_SENTINELS if s.encode() in data],
      [s for s in SEALED_SENTINELS if s.encode() in data])
restored = Path(_support.work_path("restored.db"))
restored.write_bytes(data)
conn = sqlite3.connect(restored)
row = conn.execute("SELECT diagnosis, is_restricted FROM consultations WHERE id = ?",
                   (CID_REC,)).fetchone()
conn.close()
check("the backup restores fully: the sealed row is there, encrypted, and opens with the key",
      row is not None and row[1] == 1 and sc.decrypt(row[0], CID_REC, "diagnosis") == DX_REC)
live = Path(TEST_DB).read_bytes()
check("the database file itself holds no sealed text either (secure_delete)",
      not [s for s in SEALED_SENTINELS if s.encode() in live])
settings_page = body(admin.get("/admin/settings"))
check("Settings → Backup says sealed records stay encrypted",
      "Sealed records stay encrypted in the backup. They can only be opened on a "
      "computer that has this system&#39;s key." in settings_page
      or "Sealed records stay encrypted in the backup. They can only be opened on a "
      "computer that has this system's key." in settings_page)

# ===========================================================================
section("6. NO AUDIT ENTRY HOLDS DIAGNOSIS OR TREATMENT TEXT")
details = [r[0] or "" for r in db().execute("SELECT details FROM audit_logs")]
check("no entry quotes a sealed diagnosis or treatment plan",
      not [d for d in details if leaks(d)])
check("no entry quotes an unsealed diagnosis either (D2)",
      not [d for d in details if DX_CTRL in d])
edit_entry = q1("SELECT details FROM audit_logs WHERE action = 'Updated consultation record' "
                "AND details LIKE ? ORDER BY id DESC", (f"Consultation #{CID_CTRL} %",))
check("an edit entry names the field instead: Changed: Diagnosis",
      edit_entry is not None and "Changed: Diagnosis" in edit_entry[0],
      edit_entry[0] if edit_entry else None)

import migrate_redact_clinical_audit_text as migration  # noqa: E402

copy = Path(_support.work_path("migrate.db"))
shutil.copyfile(TEST_DB, copy)
OLD_DX, OLD_TX, OLD_SEALED = "ZZOLDAUDIT9DX", "ZZOLDAUDIT9TX", "ZZOLDSEALED8DX"
conn = sqlite3.connect(copy)
conn.execute("INSERT INTO audit_logs (user_id, action, module, details, created_at) VALUES "
             "(1, 'Updated consultation record', 'Consultation Records', ?, '2026-08-01 01:00:00')",
             (f'Consultation #3 for X (PAT-003). 2 fields changed — Temperature: 36 °C → 37 °C; '
              f'Diagnosis: "{OLD_DX} a; b" → "{OLD_DX} c"; Treatment plan / medicines given: '
              f'not recorded → "{OLD_TX}"; Additional notes: "x" → "y"',))
conn.execute("UPDATE consultations SET diagnosis = ?, is_restricted = 1, restricted_by = 5, "
             "restricted_at = '2026-08-01 02:00:00' WHERE id = 12", (OLD_SEALED,))
conn.commit()
before_entries = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
conn.close()
backups = Path(_support.work_path("migration-backups"))
with contextlib.redirect_stdout(io.StringIO()):
    first = migration.run(copy, backup_dir=backups)
conn = sqlite3.connect(copy)
texts = [r[0] or "" for r in conn.execute("SELECT details FROM audit_logs")]
records = conn.execute("SELECT user_id, details FROM audit_logs WHERE action = ?",
                       (migration.ACTION,)).fetchall()
sealed_12 = conn.execute("SELECT diagnosis FROM consultations WHERE id = 12").fetchone()[0]
kept = conn.execute("SELECT details FROM audit_logs WHERE details LIKE "
                    "'Consultation #3 for X (PAT-003)%'").fetchone()[0]
after_entries = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
conn.close()
check("the migration made a backup first, in the backups folder",
      first["backup"] and Path(first["backup"]).exists()
      and Path(first["backup"]).parent == backups, first)
check("it removed the old clinical text from the entries",
      first["entries_redacted"] >= 1 and not [t for t in texts if OLD_DX in t or OLD_TX in t],
      first)
check("and left who, what changed and the other fields in place",
      "Temperature: 36 °C → 37 °C" in kept and "Diagnosis: (clinical text removed)" in kept
      and "Treatment plan / medicines given: (clinical text removed)" in kept
      and 'Additional notes: "x" → "y"' in kept, kept)
check("it encrypted the already-sealed record",
      first["records_encrypted"] == 1 and sc.is_encrypted(sealed_12)
      and sc.decrypt(sealed_12, 12, "diagnosis") == OLD_SEALED)
check("it wrote exactly one record of itself, with the reason and no clinical text",
      len(records) == 1 and after_entries == before_entries + 1
      and "RA 11166" in records[0][1] and "RA 10173" in records[0][1]
      and OLD_DX not in records[0][1], records)
check("after VACUUM the file holds none of the removed text",
      not [s for s in (OLD_DX, OLD_TX, OLD_SEALED) if s.encode() in copy.read_bytes()])
with contextlib.redirect_stdout(io.StringIO()):
    second = migration.run(copy, backup_dir=backups)
conn = sqlite3.connect(copy)
records_after = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = ?",
                             (migration.ACTION,)).fetchone()[0]
conn.close()
check("running it twice changes nothing and makes no second backup or record",
      second["backup"] is None and records_after == 1, second)

# ===========================================================================
section("7. REPORTS COUNT SEALED VISITS UNDER CONFIDENTIAL")
with app.app_context():
    from models.consultations import get_consultation_stats
    stats = get_consultation_stats()
sealed_total = q1("SELECT COUNT(*) FROM consultations WHERE is_restricted = 1")[0]
confidential = [d for d in stats["top_diagnoses"] if d["label"] == "Confidential"]
check("the all-time ranking has one Confidential row counting every sealed visit",
      len(confidential) == 1 and confidential[0]["count"] == sealed_total,
      (confidential, sealed_total))
check("and the total still includes them",
      stats["total"] == q1("SELECT COUNT(*) FROM consultations")[0])
day = q1("SELECT substr(consultation_date, 1, 10) FROM consultations WHERE id=?", (CID_REC,))[0]
RANGE = f"?from={day}&to={day}"
for who, client, url in (("Administrator", admin, "/admin/reports_analytics"),
                         ("Doctor", doctor, "/staff/reports_analytics"),
                         ("Barangay Official", official, "/official/reports_analytics"),
                         ("Barangay Official", official, "/official/community-reports")):
    page = body(client.get(url + RANGE))
    check(f"{who}: {url} shows Confidential and no sealed text",
          "Confidential" in page and not leaks(page))
for who, client, url in (("Administrator", admin, "/admin/reports_analytics/export.xlsx"),
                         ("Doctor", doctor, "/staff/reports_analytics/export.pdf"),
                         ("Barangay Official", official, "/official/community-reports/export.xlsx")):
    text = readable(client.get(url + RANGE))
    check(f"{who}: {url} lists Confidential and no sealed text",
          "Confidential" in text and not leaks(text))

# ===========================================================================
section("8. A WRONG OR MISSING KEY GIVES A PLAIN MESSAGE, NOT A CRASH")
right_key = os.environ["SEALED_DATA_KEY"]
stored = q1("SELECT diagnosis, treatment_plan FROM consultations WHERE id=?", (CID_REC,))
for label, value in (("a wrong key", sc.new_key()), ("no key", None)):
    if value is None:
        os.environ.pop("SEALED_DATA_KEY")
    else:
        os.environ["SEALED_DATA_KEY"] = value
    mark = audit_max()
    response = doctor.get(f"/staff/patient_profile/{P_REC}")
    page = body(response)
    entries = db().execute("SELECT action, details FROM audit_logs WHERE id > ?",
                           (mark,)).fetchall()
    check(f"with {label}: the Doctor's profile still opens and says so plainly",
          response.status_code == 200 and UNOPENABLE in page and not leaks(page),
          response.status_code)
    check(f"with {label}: one audit entry, without clinical text",
          sum(1 for e in entries if e[0] == "Could not open sealed consultation") == 1
          and not any(leaks(e[1] or "") for e in entries), [tuple(e) for e in entries])
    page = body(doctor.get(f"/staff/consultation/edit/{CID_REC}"))
    check(f"with {label}: the edit form shows the line and no diagnosis box",
          UNOPENABLE in page and 'name="diagnosis"' not in page)
    form = {k: v for k, v in edit_form(CID_REC, temperature="37.1").items()
            if k not in ("diagnosis", "treatment_plan")}
    form["is_restricted"] = "1"
    doctor.post(f"/staff/consultation/edit/{CID_REC}", data=form)
    doctor.post(f"/staff/patient_profile/{P_REC}/restrict-consultation",
                data={"consultation_id": str(CID_REC), "restrict_action": "lift"})
    after = q1("SELECT diagnosis, treatment_plan, is_restricted FROM consultations "
               "WHERE id=?", (CID_REC,))
    check(f"with {label}: saving or lifting cannot overwrite or unseal the record",
          (after[0], after[1]) == (stored[0], stored[1]) and after[2] == 1)
os.environ["SEALED_DATA_KEY"] = right_key
check("with the right key back, the Doctor reads the record again",
      DX_REC in body(doctor.get(f"/staff/patient_profile/{P_REC}")))

# ===========================================================================
section("9. ONE PLACE DECRYPTS, AND IT REFUSES EVERY ROLE BUT THE DOCTOR")
calls = []
for path in sorted(list((REPO / "models").glob("*.py")) + list((REPO / "routes").glob("*.py"))
                   + list((REPO / "utils").glob("*.py")) + [REPO / "app.py"]):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                # The AES call inside sealed_crypto.decrypt() is the primitive
                # itself, not a caller of it.
                if name == "decrypt" and not (path.name == "sealed_crypto.py"
                                              and func.name == "decrypt"):
                    calls.append(f"{path.name}:{func.name}")
check("decrypt() is called from exactly one function: open_sealed_value()",
      sorted(set(calls)) == ["consultations.py:open_sealed_value"], calls)
from models.consultations import open_sealed_value, set_consultation_restriction  # noqa: E402

cipher = q1("SELECT diagnosis FROM consultations WHERE id=?", (CID_REC,))[0]
for role in ("admin", "health staff", "barangay official", None):
    try:
        open_sealed_value(cipher, CID_REC, "diagnosis", role)
        refused = False
    except PermissionError:
        refused = True
    check(f"open_sealed_value() refuses the role {role!r}", refused)
check("open_sealed_value() opens it for the Doctor",
      open_sealed_value(cipher, CID_REC, "diagnosis", "doctor") == (DX_REC, True))
with app.app_context():
    try:
        set_consultation_restriction(CID_REC, False, ADMIN_ID, "admin")
        raised = False
    except PermissionError:
        raised = True
check("the model refuses to unseal for a role that may not decrypt, and nothing changes",
      raised and q1("SELECT is_restricted FROM consultations WHERE id=?", (CID_REC,))[0] == 1)

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print("  FAILED:", name)
print("=" * 78)
sys.exit(0 if not failed else 1)

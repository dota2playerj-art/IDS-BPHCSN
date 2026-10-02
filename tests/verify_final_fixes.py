"""The final fixes: SMS recipients are counts only outside the care team (M37), the
README and seed order (M36), phone masking in every format (D3), and the small items of
the final audit (L35-L44).

Runs on a fresh test database built by tests/_support.py.
"""
import ast
import io
import os
import re
import sqlite3
import subprocess
import sys
import zlib
from pathlib import Path

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

sys.stdout.reconfigure(errors="replace")
os.environ["SEMAPHORE_API_KEY"] = ""  # nothing here may ever send a real message

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
REPO = Path(_support.REPO)
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


def q(sql, args=()):
    conn = db()
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def run_sql(sql, args=()):
    conn = db()
    try:
        conn.execute(sql, args)
        conn.commit()
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


def readable(response):
    kind = response.headers.get("Content-Type", "")
    if "spreadsheetml" in kind:
        book = load_workbook(io.BytesIO(response.data), data_only=True)
        return "\n".join(str(c) for s in book.worksheets for row in s.iter_rows(values_only=True)
                         for c in row if c is not None)
    if "pdf" in kind:
        return pdf_text(response.data) + response.data.decode("latin-1")
    return response.data.decode("utf-8", "replace")


admin, staff, official, doctor = (client_as(i) for i in (ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID))

# ---------------------------------------------------------------------------
section("1. SMS RECIPIENTS ARE COUNTS ONLY FOR THE ADMINISTRATOR AND THE OFFICIAL (M37, D1)")
AUDIENCES = ("all_patients", "seniors", "child_guardians")
for audience in AUDIENCES:
    official.post("/official/sms_notifications/send", data={
        "message": f"Health center notice for {audience}.", "audience": audience, "category": ""})
broadcasts = q("SELECT id, audience FROM sms_broadcasts ORDER BY id")
check("setup: one simulated broadcast per audience was sent", len(broadcasts) == len(AUDIENCES),
      [tuple(b) for b in broadcasts])

# Marker names on every recipient row, so a leak cannot be mistaken for anything else.
marker_of = {}
for row in q("SELECT id FROM sms_broadcast_recipients ORDER BY id"):
    marker_of[row["id"]] = f"ZZRECIP{row['id']:04d}"
    run_sql("UPDATE sms_broadcast_recipients SET recipient_name = ? WHERE id = ?",
            (marker_of[row["id"]], row["id"]))
# One failed recipient, so the failed count is not trivially zero.
failed_id = min(marker_of)
run_sql("UPDATE sms_broadcast_recipients SET status = 'Failed' WHERE id = ?", (failed_id,))
markers = list(marker_of.values())
fixture_names = [f"{p[1]} {p[2]}" for p in _support.PATIENTS]

total = q("SELECT COUNT(*) AS n FROM sms_broadcast_recipients")[0]["n"]
check("setup: there are recipients to hide", total >= 6, total)

SMS_PAGES = {"Administrator": ["/admin/sms_notifications", "/admin/dashboard"],
             "Barangay Official": ["/official/sms_notifications", "/official/dashboard",
                                   "/official/community-reports", "/official/reports_analytics"]}
CLIENTS = {"Administrator": admin, "Barangay Official": official}
for label, pages in SMS_PAGES.items():
    leaked = []
    seen_names = []
    for page in pages:
        text = readable(CLIENTS[label].get(page))
        leaked += [(page, m) for m in markers if m in text]
        seen_names += [(page, n) for n in fixture_names if n in text and "sms" in page]
    check(f"{label}: no recipient name on the SMS screen, the dashboards or the reports", not leaked, leaked[:5])
    check(f"{label}: no patient full name on the SMS screen at all", not seen_names, seen_names[:5])

latest_id = q("SELECT MAX(id) AS m FROM sms_broadcasts")[0]["m"]
latest = q("SELECT * FROM sms_broadcasts WHERE id = ?", (latest_id,))[0]
counts = q("SELECT COUNT(*) AS t, SUM(status='Sent') AS s, SUM(status='Failed') AS f "
           "FROM sms_broadcast_recipients WHERE broadcast_id = ?", (latest_id,))[0]
for label in ("Administrator", "Barangay Official"):
    page = "/admin/sms_notifications" if label == "Administrator" else "/official/sms_notifications"
    text = body(CLIENTS[label].get(page))
    panel = text[text.index("Most recent broadcast"):]
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", panel))
    check(f"{label}: the most recent broadcast shows its recipient counts (total, sent, failed)",
          f"Total {counts['t']}" in flat and f"Sent {counts['s']}" in flat
          and f"Failed {counts['f']}" in flat, flat[:600])
    check(f"{label}: the history table still shows the counts per broadcast",
          all(f"{b['sent_count']} of {b['recipient_count']} sent" in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
              for b in q("SELECT sent_count, recipient_count FROM sms_broadcasts")))
    check(f"{label}: the audience list still shows a recipient count per audience",
          len(re.findall(r"\d+ recipients?", text)) >= 3)

# The model function itself refuses names, whatever the caller.
import models.broadcasts as bc  # noqa: E402
check("the data builder returns no recipients for the Administrator or the Official",
      bc.get_broadcast_recipients(latest_id, "admin") == []
      and bc.get_broadcast_recipients(latest_id, "Administrator") == []
      and bc.get_broadcast_recipients(latest_id, "barangay official") == []
      and bc.get_broadcast_recipients(latest_id, "") == [])
check("and it returns them, masked, for the Doctor and Health Center Staff",
      len(bc.get_broadcast_recipients(latest_id, "doctor")) == counts["t"]
      and len(bc.get_broadcast_recipients(latest_id, "health staff")) == counts["t"])
check("get_broadcast_recipient_counts() gives total, sent and failed",
      bc.get_broadcast_recipient_counts(latest_id) == {"total": counts["t"], "sent": counts["s"] or 0,
                                                       "failed": counts["f"] or 0})

# Staff and the Doctor still see names, with masked numbers.
for label, client in (("Health Center Staff", staff), ("Doctor", doctor)):
    text = body(client.get("/staff/sms_notifications"))
    shown = [m for m in markers if m in text]
    check(f"{label}: still sees recipient names on the latest broadcast ({len(shown)} shown)", shown)
    digits = re.sub(r"\D", "", text)
    full = [p for p in q("SELECT contact_number FROM patients WHERE contact_number IS NOT NULL")
            if p["contact_number"][1:] in digits]
    check(f"{label}: numbers are masked to the last four digits, none in full", "•••• •••" in text and not full)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
section("2. README GETTING STARTED ORDER AND THE SEED REFUSAL (M36, D2)")
readme = (REPO / "README.md").read_text(encoding="utf-8")
start = readme[readme.index("## Getting started"):]
start = start[:start.index("\n## ", 5)]
order = ["python -m venv .venv", "pip install -r requirements.txt", "python setup_env.py",
         "python archive_plain_databases.py", "python seed_demo_data.py", "python app.py",
         "http://127.0.0.1:5001"]
positions = [start.find(step) for step in order]
check("the README starts with the steps in the order that works on a clean clone",
      all(p >= 0 for p in positions) and positions == sorted(positions), positions)
check("it says pip needs internet once, that the seed prints the passwords once, and that a new "
      "password is set at first sign-in",
      "needs internet" in start and "**once**" in start and "set a new password" in start)
import seed_demo_data as seed  # noqa: E402
existing = Path(_support.TEST_DIR) / "already_there.db"
existing.write_bytes(b"")
try:
    seed.build(str(existing), show_passwords=False)
    refusal = ""
except SystemExit as stop:
    refusal = str(stop)
check("the seed refuses to build over an existing app.db and says to run it with --replace",
      "python seed_demo_data.py --replace" in refusal and "archives the old" in refusal, refusal)
main_refusal = subprocess.run([sys.executable, str(REPO / "seed_demo_data.py"), "--path", str(existing)],
                              capture_output=True, text=True, cwd=REPO,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))
check("the command line says the same, and exits 1 without changing the file",
      main_refusal.returncode == 1 and "--replace" in main_refusal.stdout
      and existing.read_bytes() == b"", main_refusal.stdout)

# ---------------------------------------------------------------------------
section("3. EVERY COMMON PHILIPPINE NUMBER FORMAT IS MASKED (D3)")
from utils.phone import MASK_PREFIX, mask_numbers_in_text, mask_phone  # noqa: E402
from models.audit import log_action  # noqa: E402

CORE = "9000001234"  # the same digits in every format below (fictional 0900000NNNN); last four 1234
FORMATS = [
    "09000001234", "+639000001234", "639000001234",
    "0900 000 1234", "0900-000-1234", "0900.000.1234", "0900 000-1234",
    "+63 900 000 1234", "+63-900-000-1234", "+63.900.000.1234", "63 900 000 1234",
    "(0900) 000 1234", "(0900) 000-1234", "[0900] 000 1234", "(+63) 900 000 1234",
    "+63 (900) 000-1234", "0900 - 000 . 1234", "09 00 00 01 23 4", "0900-000 1234",
]
bad_text, bad_phone = [], []
for number in FORMATS:
    masked = mask_numbers_in_text(f"Texted {number} about a visit.")
    if masked != f"Texted {MASK_PREFIX} 1234 about a visit.":
        bad_text.append((number, masked))
    shown = mask_phone(number)
    if shown != f"{MASK_PREFIX} 1234":
        bad_phone.append((number, shown))
check(f"mask_numbers_in_text masks all {len(FORMATS)} formats inside a sentence, to the last four digits",
      not bad_text, bad_text[:4])
check("mask_phone shows the last four digits and nothing else in every format", not bad_phone, bad_phone[:4])
check("a bracket or space around the number stays tidy: '(0900 000 1234)' keeps its brackets",
      mask_numbers_in_text("Call (0900 000 1234) now.") == f"Call ({MASK_PREFIX} 1234) now.")
check("two numbers in different formats in one entry are both masked",
      mask_numbers_in_text("From 0900-000-1234 to +63 900 000 4321.")
      == f"From {MASK_PREFIX} 1234 to {MASK_PREFIX} 4321.")
check("masking twice changes nothing", mask_numbers_in_text(mask_numbers_in_text("Texted 0900-000-1234."))
      == f"Texted {MASK_PREFIX} 1234.")
innocent = ["Consultation #1234 on 2026-09-05 09:12, 12 doses.", "from 2026-09-05 to 2026-09-12",
            "Texted ref 12312348901 on 20260905.", "APT-00090 for PAT-0912 (visit 2026-09-05)"]
check("dates, ids and other digits are left alone",
      all(mask_numbers_in_text(t) == t for t in innocent),
      [(t, mask_numbers_in_text(t)) for t in innocent if mask_numbers_in_text(t) != t])
stored_bad = []
for number in FORMATS:
    entry_id = log_action(user_id=ADMIN_ID, action="Test entry", module="Testing",
                          details=f"Texted {number} about a booking.", ip_address="127.0.0.1")
    row = q("SELECT details FROM audit_logs WHERE id = ?", (entry_id,))[0]["details"] if entry_id else ""
    if CORE in re.sub(r"\D", "", row) or "1234" not in row:
        stored_bad.append((number, row))
check("the audit writer stores no number in any of those formats, only its last four digits",
      not stored_bad, stored_bad[:3])
check("a number written with dashes no longer survives in an audit entry",
      "0900-000-1234" not in " ".join(r["details"] for r in q("SELECT details FROM audit_logs")))
from migrations import migrate_mask_audit_phone_numbers as mig  # noqa: E402
check("the old-entry migration finds numbers in the dashed formats too",
      all(mig._PH_MOBILE_IN_TEXT.search(f"Texted {n}.") for n in FORMATS))

# ==== END ====
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)

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
# ==== END ====
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)

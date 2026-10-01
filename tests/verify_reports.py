"""Verification: a sealed diagnosis must not reach the top-diagnoses ranking.

Runs the REAL Flask application over a fresh test database built by
tests/_support.py, driving real
HTTP requests, and reads the ACTUAL BYTES of freshly generated .xlsx and .pdf
exports rather than trusting the builders that made them.

THE POSITIVE CONTROL IS THE POINT OF THE DESIGN.
Every "the sealed value is absent" assertion is paired with "an ordinary value
with the same shape is present, extracted the same way". Without that pair, a
broken extractor -- a PDF whose text this suite cannot decompress, a workbook
read from the wrong sheet -- reports absence for everything and passes while
proving nothing. Two sentinels are planted for exactly this reason:

    SEALED   on a restricted consultation. Must appear NOWHERE.
    CONTROL  on an ordinary one.           Must appear EVERYWHERE the ranking does.

Both are single unhyphenated tokens so PDF word-wrap cannot split them across
text runs and turn a leak into a false pass.
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

from app import create_app  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

app = create_app()
app.config["DATABASE"] = TEST_DB
_support.attach(app)

ADMIN_ID, STAFF_ID, OFFICIAL_ID = 1, 2, 3

SEALED = "ZZSEALEDDX"
CONTROL = "ZZCONTROLDX"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
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


def pdf_text(data):
    """Every FlateDecode stream in a PDF, decompressed and concatenated.

    fpdf2 compresses page content by default, so the sentinels are not in the raw
    bytes. This pulls each stream out and inflates it; anything that will not
    inflate is kept as-is, since an uncompressed document is also possible.
    """
    out = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        chunk = match.group(1)
        try:
            out.append(zlib.decompress(chunk).decode("latin-1"))
        except Exception:
            out.append(chunk.decode("latin-1", "replace"))
    return "\n".join(out)


def xlsx_text(data):
    """Every cell value in every sheet of a workbook, as one string."""
    book = load_workbook(io.BytesIO(data), data_only=True)
    out = []
    for sheet in book.worksheets:
        out.append(sheet.title)
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    out.append(str(cell))
    return "\n".join(out)


print("=" * 78)
print("IDS-BPHCSN - sealed diagnosis must not reach the top-diagnoses ranking")
print("=" * 78)

# ---------------------------------------------------------------------------
# 0. Route x role matrix for every surface that prints this ranking
# ---------------------------------------------------------------------------
print("\n--- 0. ROUTE x ROLE MATRIX (ranking surfaces) ---")
ranking_rules = sorted(
    (r.rule, r.endpoint) for r in app.url_map.iter_rules()
    if "report" in r.rule
)
for rule, endpoint in ranking_rules:
    print(f"  {rule:56s} -> {endpoint}")
check("Both roles' Reports & Analytics surfaces are present",
      any(e == "admin.reports_analytics" for _, e in ranking_rules)
      and any(e == "official.official_reports_analytics" for _, e in ranking_rules))
check("Barangay Official has Community Reports too",
      any(e == "official.community_reports" for _, e in ranking_rules))

# ---------------------------------------------------------------------------
# Fixtures: two consultations, same date, distinctive single-token diagnoses
# ---------------------------------------------------------------------------
conn = db()
rows = conn.execute(
    """SELECT id, patient_id, consultation_date FROM consultations
        ORDER BY id DESC LIMIT 2"""
).fetchall()
SEALED_CID, CONTROL_CID = rows[0]["id"], rows[1]["id"]
VISIT_DATE = rows[0]["consultation_date"][:10]

# Both dated to the same day, so a single-day range holds both: that is the
# narrowest, most dangerous window a Barangay Official can select, and it is the
# one the ranking has to survive.
conn.execute(
    "UPDATE consultations SET diagnosis = ?, consultation_date = ?, "
    "is_restricted = 1, restricted_by = 1, restricted_at = '2026-09-05 09:00:00' "
    "WHERE id = ?",
    (f"{SEALED} reactive on confirmatory assay", VISIT_DATE, SEALED_CID),
)
conn.execute(
    "UPDATE consultations SET diagnosis = ?, consultation_date = ?, "
    "is_restricted = 0, restricted_by = NULL, restricted_at = NULL WHERE id = ?",
    (f"{CONTROL} ordinary unsealed finding", VISIT_DATE, CONTROL_CID),
)
conn.commit()
sealed_row = conn.execute(
    "SELECT * FROM consultations WHERE id = ?", (SEALED_CID,)).fetchone()
conn.close()

print(f"\nsealed  consultation #{SEALED_CID}: {sealed_row['diagnosis']}"
      f"  (is_restricted={sealed_row['is_restricted']})")
print(f"control consultation #{CONTROL_CID}: {CONTROL} ordinary unsealed finding")
print(f"both dated {VISIT_DATE}")

admin = client_as(ADMIN_ID)
doctor = client_as(5)  # PORTED: the clinician
official = client_as(OFFICIAL_ID)
staff = client_as(STAFF_ID)

RANGE = f"?from={VISIT_DATE}&to={VISIT_DATE}"

# ---------------------------------------------------------------------------
# 1. The model: the single shared calculation
# ---------------------------------------------------------------------------
print("\n--- 1. THE SHARED CALCULATION (models.consultations) ---")
with app.app_context():
    from models.consultations import get_consultation_stats
    from datetime import date
    day = date.fromisoformat(VISIT_DATE)
    stats = get_consultation_stats(months=6, start=day, end=day)

w = stats["window"]
labels = " | ".join(d["label"] for d in w["top_diagnoses"])
print(f"  window total          : {w['total']}")
print(f"  diagnoses_withheld    : {w['diagnoses_withheld']}")
print(f"  window top_diagnoses  : {labels}")

check("Sealed diagnosis is absent from the window ranking",
      not any(SEALED in d["label"] for d in w["top_diagnoses"]), labels)
check("Control diagnosis IS present in the window ranking (positive control)",
      any(CONTROL in d["label"] for d in w["top_diagnoses"]), labels)
check("Sealed diagnosis is absent from the all-time ranking",
      not any(SEALED in d["label"] for d in stats["top_diagnoses"]))
check("diagnoses_withheld reports the sealed consultation",
      w["diagnoses_withheld"] == 1, f"withheld={w['diagnoses_withheld']}")

check("The sealed VISIT is still counted in the range total",
      w["total"] == 2, f"total={w['total']} (expected both consultations)")
check("The sealed visit is still counted in patients_seen",
      w["patients_seen"] >= 1, f"patients_seen={w['patients_seen']}")
check("The sealed visit is still counted in the trend",
      sum(t["count"] for t in w["trend"]) == w["total"],
      f"trend sums to {sum(t['count'] for t in w['trend'])}, total {w['total']}")
check("The chief-complaint ranking is NOT filtered (the seal covers two fields)",
      len(w["top_complaints"]) >= 1,
      f"{len(w['top_complaints'])} complaints ranked from {w['total']} visits")

# ---------------------------------------------------------------------------
# 2. On-screen, both roles
# ---------------------------------------------------------------------------
print("\n--- 2. ON-SCREEN RANKING, BOTH ROLES ---")
screens = [
    ("Administrator Reports & Analytics", admin, f"/admin/reports_analytics{RANGE}"),
    ("Barangay Official Reports & Analytics", official,
     f"/official/reports_analytics{RANGE}"),
    ("Barangay Official Community Reports", official,
     f"/official/community-reports{RANGE}"),
]
for label, cl, url in screens:
    resp = cl.get(url)
    page = resp.get_data(as_text=True)
    check(f"{label} renders (200)", resp.status_code == 200,
          f"status={resp.status_code}")
    check(f"{label}: sealed diagnosis ABSENT from the page", SEALED not in page)
    check(f"{label}: control diagnosis PRESENT (positive control)",
          CONTROL in page)
    # Task 5 (D3): a sealed visit is now a "Confidential" row, for every role.
    check(f"{label}: counts the restricted consultation under Confidential",
          "Confidential" in page and "counted under Confidential" in page)

# ---------------------------------------------------------------------------
# 3. Freshly generated exports, both roles, both formats
# ---------------------------------------------------------------------------
print("\n--- 3. FRESHLY GENERATED EXPORTS (.xlsx and .pdf), BOTH ROLES ---")
exports = [
    ("Administrator Excel", admin, f"/admin/reports_analytics/export.xlsx{RANGE}", "xlsx"),
    ("Administrator PDF", admin, f"/admin/reports_analytics/export.pdf{RANGE}", "pdf"),
    ("Barangay Official Excel", official,
     f"/official/reports_analytics/export.xlsx{RANGE}", "xlsx"),
    ("Barangay Official PDF", official,
     f"/official/reports_analytics/export.pdf{RANGE}", "pdf"),
    ("Official Community Reports Excel", official,
     f"/official/community-reports/export.xlsx{RANGE}", "xlsx"),
    ("Official Community Reports PDF", official,
     f"/official/community-reports/export.pdf{RANGE}", "pdf"),
]
for label, cl, url, kind in exports:
    resp = cl.get(url)
    ok = check(f"{label} generated (200)", resp.status_code == 200,
               f"status={resp.status_code} bytes={len(resp.data)}")
    if not ok:
        continue
    text = xlsx_text(resp.data) if kind == "xlsx" else pdf_text(resp.data)
    # The extractor must be shown to work before its silence means anything.
    control_found = CONTROL in text
    check(f"{label}: extractor verified — control diagnosis FOUND in the file",
          control_found,
          f"extracted {len(text)} chars; if this fails the absence below proves nothing")
    check(f"{label}: *** sealed diagnosis ABSENT from the generated file ***",
          SEALED not in text,
          "LEAKED" if SEALED in text else "absent from every stream/cell")
    check(f"{label}: raw bytes carry no sealed diagnosis either",
          SEALED.encode() not in resp.data)

# ---------------------------------------------------------------------------
# 4. The seal still holds everywhere it did before (no regression)
# ---------------------------------------------------------------------------
print("\n--- 4. THE RESTRICTED FEATURE ITSELF, UNCHANGED ---")
pid = sealed_row["patient_id"]
resp = staff.get(f"/staff/patient_profile/{pid}")
page = resp.get_data(as_text=True)
check("Staff profile still withholds the sealed diagnosis", SEALED not in page)
check("Staff profile still shows the honest placeholder",
      "Restricted" in page and "Doctor access only" in page)
resp = doctor.get(f"/staff/patient_profile/{pid}")
check("Doctor (was: Administrator) profile still shows the sealed diagnosis in full",
      SEALED in resp.get_data(as_text=True))

resp = official.get(f"/admin/reports_analytics{RANGE}")
check("Barangay Official is still turned away from the admin route",
      resp.status_code == 302, f"status={resp.status_code}")
resp = staff.get(f"/official/reports_analytics{RANGE}")
check("Staff cannot reach Reports & Analytics at all",
      resp.status_code == 302, f"status={resp.status_code}")

# ---------------------------------------------------------------------------
# 5. Unsealing restores it — the exclusion tracks the flag, not the text
# ---------------------------------------------------------------------------
print("\n--- 5. LIFTING THE SEAL RESTORES THE RANKING ---")
resp = doctor.post(
    f"/staff/patient_profile/{pid}/restrict-consultation",
    data={"consultation_id": str(SEALED_CID), "restrict_action": "lift"})
check("Administrator lifted the seal", resp.status_code == 302)
resp = admin.get(f"/admin/reports_analytics{RANGE}")
page = resp.get_data(as_text=True)
check("Once unsealed, the diagnosis DOES appear in the ranking", SEALED in page,
      "confirms the exclusion follows is_restricted, not the text itself")
resp = official.get(f"/official/reports_analytics{RANGE}")
check("Once unsealed, the Official's ranking shows it too",
      SEALED in resp.get_data(as_text=True))

# re-seal for the whole-range checks below
doctor.post(f"/staff/patient_profile/{pid}/restrict-consultation",
           data={"consultation_id": str(SEALED_CID), "restrict_action": "restrict"})

# ---------------------------------------------------------------------------
# 6. Default (unranged) view, and the whole-history ranking
# ---------------------------------------------------------------------------
print("\n--- 6. DEFAULT VIEW, NO RANGE SELECTED ---")
for label, cl, url in [
    ("Administrator Reports & Analytics", admin, "/admin/reports_analytics"),
    ("Barangay Official Reports & Analytics", official, "/official/reports_analytics"),
    ("Barangay Official Community Reports", official, "/official/community-reports"),
    ("Barangay Official dashboard", official, "/official/dashboard"),
    ("Administrator dashboard", admin, "/admin/dashboard"),
]:
    resp = cl.get(url)
    page = resp.get_data(as_text=True)
    check(f"{label} (default): renders and leaks no sealed diagnosis",
          resp.status_code == 200 and SEALED not in page,
          f"status={resp.status_code}")

# ---------------------------------------------------------------------------
# 7. Regression sweep across every GET route and role
# ---------------------------------------------------------------------------
print("\n--- 7. REGRESSION SWEEP ---")
failures, leaks, checked = [], [], 0
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if rule.endpoint == "static" or "GET" not in rule.methods:
        continue
    args, ok = {}, True
    for arg in rule.arguments:
        if arg == "patient_id":
            args[arg] = pid
        elif arg == "consultation_id":
            args[arg] = SEALED_CID
        elif arg in ("medicine_id", "item_id", "user_id", "log_id", "appointment_id"):
            args[arg] = 1
        else:
            ok = False
            break
    if not ok:
        continue
    built = rule.build(args)
    url = built[1] if isinstance(built, tuple) else built
    for name, cl in (("admin", admin), ("staff", staff), ("official", official)):
        resp = cl.get(url)
        checked += 1
        if resp.status_code >= 500:
            failures.append((name, url, resp.status_code))
        # Staff and the Official must never receive the sealed text on ANY route.
        if name in ("staff", "official") and SEALED.encode() in resp.data:
            leaks.append((name, url))
check(f"No 5xx on any GET route for any role ({checked} requests)", not failures,
      "\n".join(f"{n} {u} -> {s}" for n, u, s in failures) or "clean")
check("Sealed diagnosis reaches NO route for Staff or the Barangay Official",
      not leaks, "\n".join(f"{n} {u}" for n, u in leaks) or "clean across every GET")

# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
failed = [n for n, ok, _ in results if not ok]
print(f"RESULT: {passed}/{len(results)} checks passed")
if failed:
    print("\nFAILED:")
    for n in failed:
        print("  -", n)
print("=" * 78)
sys.exit(1 if failed else 0)

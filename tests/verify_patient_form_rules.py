"""Register / Edit Patient: civil status follows the age, and the address follows the place lists (Task 22).

D1. Civil status. "Minor" is gone (it is an age, not a civil status). Under 18 by calculate_age(),
    the one age rule, the only civil status is Single (RA 11596); 18 and over, the adult list.
    The page offers exactly that; the server enforces it on Register and Edit.
D2. Address, chosen Province -> City/Municipality -> Barangay from models/places.py: Surigao del
    Norte (21 LGUs; San Francisco's 11 barangays) or Other province (all typed). The server
    enforces the pairing on Register and Edit and keeps every typed value on a refusal.
D3. Records saved under the old rules open on Edit with their stored values and the fields to
    correct marked.
D4. migrate_civil_status_minor_to_single.py changes "Minor" to "Single" and nothing else, and
    migrate_add_patient_barangay.py adds one empty column; both back up first and are safe twice.
D5. Nothing uses "Minor" to mean a child: the demo data and every child rule use the age.
"""
import html
import json
import re
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
REPO = Path(_support.REPO)
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5
DAY = date(2026, 10, 22)   # the frozen "today" every POST below is made on

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


def field_errors(page):
    return [html.unescape(m) for m in re.findall(r'invalid-feedback d-block">([^<]+)<', page)]


def select_options(page, select_id):
    """[(value, text, selected)] of one <select> on the page."""
    match = re.search(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', page, re.S)
    if not match:
        return None
    return [(html.unescape(v), html.unescape(t).strip(), " selected" in attrs)
            for v, attrs, t in re.findall(r'<option value="([^"]*)"([^>]*)>([^<]*)</option>',
                                          match.group(1))]


def tag_of(page, element_id):
    match = re.search(rf'<(?:input|div|select)[^>]*id="{element_id}"[^>]*>', page)
    return match.group(0) if match else ""


staff, doctor, admin, official = (client_as(i) for i in (STAFF_ID, DOCTOR_ID, ADMIN_ID, OFFICIAL_ID))
REGISTER = "/staff/register-patient"
_tag = [0]


SYLLABLES = ("ka", "lo", "mi", "nu", "pe", "ri", "so", "tu", "va", "we")


def _word(number):
    """A made-up name, far enough from every other one that the duplicate check stays quiet."""
    return "Zq" + "".join(SYLLABLES[(number // 10 ** k) % 10] for k in range(3))


def form(**overrides):
    """A complete, valid registration for a fresh fictional person (unique name each time)."""
    _tag[0] += 1
    data = {
        "first_name": _word(_tag[0]), "last_name": _word(_tag[0] * 7 + 500), "birth_date": "1990-05-05",
        "sex": "Female", "civil_status": "Single", "address": "Purok 3",
        "province": "Surigao del Norte", "municipality": "San Francisco", "barangay": "Poblacion",
        "zip_code": "8401", "emergency_contact_name": "Test Relative",
        "emergency_contact_relationship": "Sibling", "emergency_contact_number": "09000000777",
    }
    data.update(overrides)
    return data


def post(path, data, client=None):
    with _support.frozen_today(DAY):
        return (client or staff).post(path, data=data)


def saved(response):
    return response.status_code == 302 and "/patient_profile/" in (response.headers.get("Location") or "")


def newest():
    return q1("SELECT * FROM patients ORDER BY id DESC LIMIT 1")


from models.patients import (  # noqa: E402
    ADULT_AGE, CIVIL_STATUSES, MINOR_CIVIL_STATUS_HINT, calculate_age, civil_statuses_for,
)
from models import places  # noqa: E402

print("=" * 78)
print("IDS-BPHCSN — civil status by age, and the address place lists (Task 22)")
print("=" * 78)

# ---------------------------------------------------------------------------
section("1. Civil status follows the age (calculate_age, the one age rule)")
ADULT = ("Single", "Married", "Widowed", "Separated")
check("the civil statuses are Single, Married, Widowed, Separated: no Minor", CIVIL_STATUSES == ADULT)
check("the adult age is 18 (RA 11596)", ADULT_AGE == 18)
AGES = [
    ("0 (born today)", "2026-10-22", 0, ("Single",)),
    ("17 years and 364 days", "2008-10-23", 17, ("Single",)),
    ("exactly 18 today", "2008-10-22", 18, ADULT),
    ("60", "1966-10-22", 60, ADULT),
    ("70", "1956-10-22", 70, ADULT),
]
for label, born, years, allowed in AGES:
    check(f"age {label}: calculate_age = {years}, allowed = {allowed}",
          calculate_age(born, DAY) == years and civil_statuses_for(born, DAY) == allowed,
          (calculate_age(born, DAY), civil_statuses_for(born, DAY)))
check("no usable birth date: the adult list (the age is unknown)",
      civil_statuses_for(None, DAY) == ADULT and civil_statuses_for("nonsense", DAY) == ADULT)
check("a birthday on February 29 turns 18 on March 1 in a common year, as the age display does",
      civil_statuses_for("2008-02-29", date(2026, 2, 28)) == ("Single",)
      and civil_statuses_for("2008-02-29", date(2026, 3, 1)) == ADULT)

# ---------------------------------------------------------------------------
section("2. Register: the server enforces the civil status on the day of registration")
for label, born, years, allowed in AGES:
    for status in ADULT:
        response = post(REGISTER, form(birth_date=born, civil_status=status))
        should_save = status in allowed
        check(f"age {label}, {status}: {'saved' if should_save else 'refused'}",
              saved(response) == should_save, field_errors(body(response)))
    if allowed == ("Single",):
        page = body(post(REGISTER, form(birth_date=born, civil_status="Married",
                                        address="Purok 9, Zzkeptstreet")))
        check(f"age {label}, Married: the plain message, and every typed value kept",
              "Patients under 18 are recorded as Single (Republic Act No. 11596)." in field_errors(page)[0]
              and 'value="Purok 9, Zzkeptstreet"' in page
              and f'value="{born}"' in page, field_errors(page))
for status in ("Minor", "minor", "Annulled", "Live-in"):
    for born in ("2020-01-01", "1980-01-01"):
        response = post(REGISTER, form(birth_date=born, civil_status=status))
        check(f"'{status}' is refused (birth date {born})", not saved(response)
              and "Choose a civil status from the list." in field_errors(body(response)))
check("an empty civil status is refused", not saved(post(REGISTER, form(civil_status=""))))

# ---------------------------------------------------------------------------
section("3. Edit: the same rule, and a refusal changes nothing")
child = run_sql("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, civil_status, "
                "address, municipality, province, barangay, contact_number, status) VALUES "
                "('TST-01', 'Zzchild', 'Rulemark', '2012-04-04', 'Male', 'Single', 'Purok 2', "
                "'San Francisco', 'Surigao del Norte', 'Poblacion', '09000000901', 'Active')")
EDIT_CHILD = f"{REGISTER}/{child}"
from routes.patient_views import patient_to_form  # noqa: E402
from models.patients import get_patient_by_id  # noqa: E402

CONTACT = {"emergency_contact_name": "Test Relative", "emergency_contact_relationship": "Mother",
           "emergency_contact_number": "09000000778"}


def stored_form(row_id):
    """Edit Patient's form for a stored record, with the emergency contact the fixtures lack."""
    return {**patient_to_form(get_patient_by_id(row_id)), **CONTACT}


before = dict(q1("SELECT * FROM patients WHERE id = ?", (child,)))
edit = stored_form(child)
response = post(EDIT_CHILD, {**edit, "civil_status": "Married", "address": "Purok 2, Zzeditkept"})
page = body(response)
check("Edit: a 14-year-old cannot be made Married; the typed values come back",
      not saved(response) and MINOR_CIVIL_STATUS_HINT in " ".join(field_errors(page))
      and 'value="Purok 2, Zzeditkept"' in page)
check("Edit: the refused save changed nothing", dict(q1("SELECT * FROM patients WHERE id = ?", (child,))) == before)
check("Edit: Minor is refused", not saved(post(EDIT_CHILD, {**edit, "civil_status": "Minor"})))
check("Edit: Single saves", saved(post(EDIT_CHILD, {**edit, "address": "Purok 2"})))
grown = run_sql("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, civil_status, "
                "address, municipality, province, barangay, contact_number, status) VALUES "
                "('TST-02', 'Zzgrown', 'Rulemark', '2008-10-22', 'Female', 'Single', 'Purok 2', "
                "'San Francisco', 'Surigao del Norte', 'Poblacion', '09000000902', 'Active')")
check("Edit: on the day she turns 18 she can be recorded as Married",
      saved(post(f"{REGISTER}/{grown}", {**stored_form(grown),
                                          "civil_status": "Married"}))
      and q1("SELECT civil_status FROM patients WHERE id = ?", (grown,))[0] == "Married")

# ---------------------------------------------------------------------------
section("4. The page: the civil status list for the birth date on the form")
with _support.frozen_today(DAY):
    fresh = body(staff.get(REGISTER))
check("a new form offers Select… and the four adult statuses, no Minor",
      [v for v, _, _ in select_options(fresh, "civilStatus")] == [""] + list(ADULT), select_options(fresh, "civilStatus"))
check("the under-18 hint is there but hidden on a new form",
      MINOR_CIVIL_STATUS_HINT in fresh and " hidden" in tag_of(fresh, "civilStatusHint"))
check("'Minor' appears nowhere on the form", "Minor" not in fresh)
minor_page = body(post(REGISTER, form(birth_date="2016-06-06", civil_status="", first_name="")))
check("redisplayed for a 10-year-old: only Single, selected, and the hint shown",
      select_options(minor_page, "civilStatus") == [("Single", "Single", True)]
      and " hidden" not in tag_of(minor_page, "civilStatusHint"), select_options(minor_page, "civilStatus"))
adult_page = body(post(REGISTER, form(birth_date="1956-10-22", civil_status="Widowed", first_name="")))
check("redisplayed for a 70-year-old: the adult list with Widowed kept selected",
      ("Widowed", "Widowed", True) in select_options(adult_page, "civilStatus")
      and len(select_options(adult_page, "civilStatus")) == 5)
data = json.loads(html.unescape(re.search(r'id="patientFormData">(.*?)</script>', fresh, re.S).group(1)))
check("the page's script gets the adult list and Single from the server (one copy)",
      data["adultCivilStatuses"] == list(ADULT) and data["minorCivilStatus"] == "Single")
source = (REPO / "templates" / "register_patient.html").read_text(encoding="utf-8")
check("the page's age box and civil status list read one whole-years function",
      source.count("function wholeYears(") == 1 and "var years = wholeYears(born, today);" in source
      and "wholeYears(born, IDSTime.clinicToday())" in source)  # the clinic's date (audit B23)
check("the page asks again when the birth date makes the choice invalid",
      "Please choose the civil status again for this birth date." in fresh)

# ---------------------------------------------------------------------------
section("5. The place lists")
LGUS = ("Alegria", "Bacuag", "Burgos", "Claver", "Dapa", "Del Carmen", "General Luna", "Gigaquit",
        "Mainit", "Malimono", "Pilar", "Placer", "San Benito", "San Francisco", "San Isidro",
        "Santa Monica", "Sison", "Socorro", "Surigao City", "Tagana-an", "Tubod")
BARANGAYS = ("Amontay", "Balite", "Banbanon", "Diaz", "Honrado", "Jubgan", "Linongganan", "Macopa",
             "Magtangale", "Oslao", "Poblacion")
check("exactly the 21 Surigao del Norte LGUs, in order and spelling",
      places.SURIGAO_DEL_NORTE_LGUS == LGUS and len(LGUS) == 21)
check("exactly the 11 barangays of San Francisco, in order and spelling",
      places.SAN_FRANCISCO_BARANGAYS == BARANGAYS and len(BARANGAYS) == 11)
check("the Province list is Surigao del Norte, then Other province",
      [v for v, _, _ in select_options(fresh, "provinceChoice")] == ["Surigao del Norte", "Other province"])
check("the page's City/Municipality dropdown is Select… and the 21, in order",
      [v for v, _, _ in select_options(fresh, "municipalitySelect")] == [""] + list(LGUS))
check("the page's Barangay dropdown is Select… and the 11, in order",
      [v for v, _, _ in select_options(fresh, "barangaySelect")] == [""] + list(BARANGAYS))
check("a new form opens on Surigao del Norte, San Francisco, Poblacion",
      ("Surigao del Norte", "Surigao del Norte", True) in select_options(fresh, "provinceChoice")
      and ("San Francisco", "San Francisco", True) in select_options(fresh, "municipalitySelect")
      and ("Poblacion", "Poblacion", True) in select_options(fresh, "barangaySelect"))
check("the typed boxes are hidden and disabled on a new form (never submitted)",
      all(" disabled" in tag_of(fresh, i) for i in ("provinceTyped", "municipalityTyped", "barangayTyped"))
      and " hidden" in tag_of(fresh, "provinceTypedWrap"))
check("'Surigao del Sur' is offered nowhere on the page", "Surigao del Sur" not in fresh)
check("the page's script reads the lists from models/places.py (page_data)",
      data["places"] == places.page_data())
check("one copy: no other file in the app spells out the 21 or the 11",
      not [str(p.relative_to(REPO)) for folder in ("models", "routes", "utils", "templates", "static/js")
           for p in (REPO / folder).rglob("*") if p.suffix in (".py", ".html", ".js")
           and p.name != "places.py" and ("Linongganan" in p.read_text(encoding="utf-8", errors="replace")
                                           or "Gigaquit" in p.read_text(encoding="utf-8", errors="replace"))])

# ---------------------------------------------------------------------------
section("6. The server enforces the pairing on Register")
cases = [
    ("San Francisco with Surigao del Sur (the old pairing)",
     {"province": "Surigao del Sur", "municipality": "San Francisco"}, False, "province"),
    ("Surigao del Sur typed under Other province, with San Francisco",
     {"province": "Other province", "province_other": "Surigao del Sur",
      "municipality_other": "San Francisco", "barangay_other": "Poblacion"}, False,
     "San Francisco is in Surigao del Norte, not Surigao del Sur."),
    ("'surigao  del norte' typed under Other province",
     {"province": "Other province", "province_other": " surigao  del NORTE ",
      "municipality_other": "Dapa", "barangay_other": "Osmena"}, False,
     "Surigao del Norte is on the list. Choose it from the Province list instead."),
    ("Other province with nothing typed: three fields required",
     {"province": "Other province"}, False, "Type the province."),
    ("a municipality not in Surigao del Norte (Bunawan)",
     {"municipality": "Bunawan"}, False, "Choose a city or municipality of Surigao del Norte from the list."),
    ("a San Francisco barangay not on the list",
     {"barangay": "Poblacion Norte"}, False, "Choose a barangay of San Francisco from the list."),
    ("San Francisco with no barangay", {"barangay": ""}, False, "Barangay is required."),
    ("no province", {"province": ""}, False, "Province is required."),
    ("Dapa with no typed barangay", {"municipality": "Dapa", "barangay": ""}, False, "Barangay is required."),
]
for label, overrides, ok, expect in cases:
    response = post(REGISTER, form(**overrides))
    errors = field_errors(body(response))
    check(f"refused: {label}", not saved(response) and (expect in errors or any(expect in e for e in errors)
                                                        or expect == "province"), errors)
page = body(post(REGISTER, form(province="Other province")))
check("Other province: province, city/municipality and barangay are each required",
      {"Type the province.", "Type the city or municipality.", "Type the barangay."} <= set(field_errors(page)))
page = body(post(REGISTER, form(province="Other province", province_other="Zzprovince Typed",
                                municipality_other="", barangay_other="Zzbarangay Typed")))
check("a refused Other province keeps what was typed, and shows the typed boxes",
      'value="Zzprovince Typed"' in page and 'value="Zzbarangay Typed"' in page
      and " disabled" not in tag_of(page, "provinceTyped") and " hidden" not in tag_of(page, "provinceTypedWrap")
      and ("Other province", "Other province", True) in select_options(page, "provinceChoice"))
response = post(REGISTER, form(province="Other province", province_other="Agusan del Sur",
                               municipality_other="San Francisco", barangay_other="Zzbrgy Uno"))
row = newest()
check("saved: Agusan del Sur / San Francisco typed (a real place) is stored as typed",
      saved(response) and (row["province"], row["municipality"], row["barangay"])
      == ("Agusan del Sur", "San Francisco", "Zzbrgy Uno"))
response = post(REGISTER, form(municipality="Dapa", barangay="Poblacion", barangay_other="Zzbrgy Dapa"))
row = newest()
check("saved: Dapa with a typed barangay; a value left in the hidden dropdown is ignored",
      saved(response) and (row["province"], row["municipality"], row["barangay"])
      == ("Surigao del Norte", "Dapa", "Zzbrgy Dapa"))
response = post(REGISTER, form(barangay="Diaz", barangay_other="Zzignored", province_other="Zzignored",
                               municipality_other="Zzignored"))
row = newest()
check("saved: San Francisco, Diaz; anything typed in the hidden boxes is ignored",
      saved(response) and (row["province"], row["municipality"], row["barangay"])
      == ("Surigao del Norte", "San Francisco", "Diaz") and "Zzignored" not in str(dict(row)))
profile = body(staff.get(f"/staff/patient_profile/{row['id']}"))
check("the profile shows the barangay in the address",
      "Purok 3, Diaz, San Francisco, Surigao del Norte, 8401" in html.unescape(profile))

# ---------------------------------------------------------------------------
section("7. Edit: the same pairing, and records saved under the old rules")
old_pair = run_sql("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, civil_status, "
                   "address, municipality, province, contact_number, status) VALUES "
                   "('TST-03', 'Zzoldpair', 'Rulemark', '1980-01-01', 'Female', 'Married', 'Purok 4', "
                   "'San Francisco', 'Surigao del Sur', '09000000903', 'Active')")
before = dict(q1("SELECT * FROM patients WHERE id = ?", (old_pair,)))
page = body(staff.get(f"{REGISTER}/{old_pair}"))
check("a stored San Francisco / Surigao del Sur record opens with the correction notice",
      'id="storedProblems"' in page and "Some details on file need correcting" in page)
check("... showing the stored values (Other province, Surigao del Sur, San Francisco typed)",
      ("Other province", "Other province", True) in select_options(page, "provinceChoice")
      and 'value="Surigao del Sur"' in tag_of(page, "provinceTyped")
      and 'value="San Francisco"' in tag_of(page, "municipalityTyped"))
check("... and saying what to correct",
      any("San Francisco is in Surigao del Norte, not Surigao del Sur." in e for e in field_errors(page)))
response = post(f"{REGISTER}/{old_pair}", stored_form(old_pair))
check("saving it unchanged is refused, and nothing changes",
      not saved(response) and dict(q1("SELECT * FROM patients WHERE id = ?", (old_pair,))) == before)
response = post(f"{REGISTER}/{old_pair}", {**stored_form(old_pair),
                                           "province": "Surigao del Norte", "municipality": "San Francisco",
                                           "barangay": "Balite"})
after = q1("SELECT province, municipality, barangay FROM patients WHERE id = ?", (old_pair,))
check("corrected to Surigao del Norte / San Francisco / Balite, it saves",
      saved(response) and tuple(after) == ("Surigao del Norte", "San Francisco", "Balite"))
entry = q1("SELECT details FROM audit_logs WHERE module = 'Patient Records' ORDER BY id DESC LIMIT 1")
check("the edit's audit entry names the fields that changed, Barangay among them",
      entry and "Barangay" in entry["details"] and "Province" in entry["details"], entry and entry["details"])
odd = run_sql("INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, civil_status, "
              "address, municipality, province, contact_number, status) VALUES "
              "('TST-04', 'Zzoddtown', 'Rulemark', '2015-01-01', 'Male', 'Minor', 'Purok 5', "
              "'Bunawan', 'Surigao del Norte', '09000000904', 'Active')")
page = body(staff.get(f"{REGISTER}/{odd}"))
check("a stored municipality not on the list is shown, marked, and selected",
      ("Bunawan", "Bunawan (not on the list)", True) in select_options(page, "municipalitySelect"))
check("a stored 'Minor' is shown, marked, and the plain message says to choose again",
      ("Minor", "Minor (not allowed)", True) in select_options(page, "civilStatus")
      and any("is not a civil status" in e for e in field_errors(page)))
legacy = staff.get("/staff/register-patient/1")
page = body(legacy)
check("an old record with no barangay asks for it, without inventing one",
      "No barangay is recorded for this patient. Choose it before saving." in field_errors(page)
      and not any(sel for _, _, sel in select_options(page, "barangaySelect")))
response = post("/staff/register-patient/1", {**stored_form(1),
                                              "province": "Surigao del Sur"})
check("Edit refuses San Francisco with Surigao del Sur too", not saved(response))
check("Edit Patient's GET leaves a valid record unflagged",
      'id="storedProblems"' not in body(staff.get(f"{REGISTER}/{child}")))

# ---------------------------------------------------------------------------
section("8. Save & Register Another keeps the whole address")
with _support.frozen_today(DAY):
    response = staff.post(REGISTER, data=form(barangay="Oslao", save_action="register_another"))
location = response.headers.get("Location") or ""
with _support.frozen_today(DAY):
    page = body(staff.get(location))
check("the fresh form keeps Surigao del Norte / San Francisco / Oslao and the purok",
      ("Oslao", "Oslao", True) in select_options(page, "barangaySelect")
      and 'value="Purok 3"' in page and "prefill_from" in location)

# ---------------------------------------------------------------------------
section("9. Who can use the form is unchanged")
for label, client in (("the Administrator", admin), ("the Barangay Official", official)):
    check(f"{label} still cannot open Register Patient", client.get(REGISTER).status_code != 200)
check("the Doctor still can", doctor.get(REGISTER).status_code == 200)

# ---------------------------------------------------------------------------
section("10. The migration: Minor becomes Single, and nothing else changes")
import migrations.migrate_civil_status_minor_to_single as minor_migration  # noqa: E402
import migrations.migrate_add_patient_barangay as barangay_migration  # noqa: E402

work = Path(_support.work_path("migrations"))
work.mkdir(parents=True, exist_ok=True)
copy = work / "minor.db"
shutil.copyfile(TEST_DB, copy)
con = sqlite3.connect(copy)
con.execute("UPDATE patients SET civil_status = 'Minor' WHERE id IN (15, 17)")
con.execute("UPDATE patients SET civil_status = 'Married' WHERE id = 2")
con.commit()
rows_before = {r[0]: r for r in con.execute("SELECT * FROM patients")}
minor_ids = sorted(r[0] for r in con.execute("SELECT id FROM patients WHERE civil_status = 'Minor'"))
audit_before = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
con.close()
result = minor_migration.run(copy, backup_dir=work / "backups")
backup = Path(result["backup"] or work / "missing")
check(f"the copy holds {len(minor_ids)} Minor records, two of them the fixture children 15 and 17",
      {15, 17} <= set(minor_ids))
check("it backs up first: the backup still holds every Minor row",
      backup.exists() and sqlite3.connect(backup).execute(
          "SELECT COUNT(*) FROM patients WHERE civil_status = 'Minor'").fetchone()[0] == len(minor_ids))
check("it reports how many records changed", result["changed"] == len(minor_ids)
      and not result["problems"], result)
con = sqlite3.connect(copy)
rows_after = {r[0]: r for r in con.execute("SELECT * FROM patients")}
names = [d[0] for d in con.execute("SELECT * FROM patients LIMIT 1").description]
status_at = names.index("civil_status")
diffs = [(row_id, names[i]) for row_id, row in rows_before.items() for i, v in enumerate(row)
         if rows_after[row_id][i] != v]
check("only civil_status of the Minor rows changed, to Single (not updated_at, not any other row)",
      sorted(diffs) == [(i, "civil_status") for i in minor_ids]
      and all(rows_after[i][status_at] == "Single" for i in minor_ids), diffs)
check("the Married adult was left alone", rows_after[2][status_at] == "Married")
entry = con.execute("SELECT action, details FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
check("one audit entry, with the count and no name",
      con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_before + 1
      and f"{len(minor_ids)} patient records" in entry[1] and "Sofia" not in entry[1]
      and "Paolo" not in entry[1], entry)
con.close()
again = minor_migration.run(copy, backup_dir=work / "backups")
check("a second run does nothing: no backup, no change, no second entry",
      again["backup"] is None and again["changed"] == 0
      and len(list((work / "backups").iterdir())) == 1
      and sqlite3.connect(copy).execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_before + 1)

section("11. The migration: patients get an empty barangay column")
old = work / "old.db"
shutil.copyfile(TEST_DB, old)
con = sqlite3.connect(old)
con.execute("ALTER TABLE patients DROP COLUMN barangay")
con.commit()
before_rows = [tuple(r) for r in con.execute("SELECT * FROM patients ORDER BY id")]
audit_before = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
con.close()
result = barangay_migration.run(old, backup_dir=work / "backups2")
con = sqlite3.connect(old)
columns = [r[1] for r in con.execute("PRAGMA table_info(patients)")]
check("it backs up first, then adds patients.barangay as the last column",
      result["backup"] and Path(result["backup"]).exists() and columns[-1] == "barangay"
      and "barangay" not in [r[1] for r in sqlite3.connect(result["backup"]).execute("PRAGMA table_info(patients)")])
check("no stored value changed, and every barangay is empty",
      [tuple(r)[:-1] for r in con.execute("SELECT * FROM patients ORDER BY id")] == before_rows
      and con.execute("SELECT COUNT(*) FROM patients WHERE barangay IS NOT NULL").fetchone()[0] == 0)
check("one audit entry", con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_before + 1)
con.close()
again = barangay_migration.run(old, backup_dir=work / "backups2")
check("a second run does nothing", again["backup"] is None
      and len(list((work / "backups2").iterdir())) == 1)
fresh_columns = [r[1] for r in sqlite3.connect(TEST_DB).execute("PRAGMA table_info(patients)")]
check("a fresh database (schema.sql) has the same columns in the same order as a migrated one",
      fresh_columns == columns)

# ---------------------------------------------------------------------------
section("12. Nothing uses 'Minor' to mean a child")
# "Minor" used as a value: compared, assigned, in a list, chosen in a condition, or in SQL.
# Comments are taken out first: a note that names the old value is not a use of it.
CODE_MINOR = re.compile(r"(==|!=|\bin\b|=|\(|,)\s*[\"']Minor[\"']|[\"']Minor[\"']\s*(,|\)|\bif\b)")
COMMENTS = {
    ".py": re.compile(r"#.*$|\"\"\".*?\"\"\"", re.M | re.S),
    ".html": re.compile(r"\{#.*?#\}|<!--.*?-->|//[^\n]*", re.S),
    ".js": re.compile(r"/\*.*?\*/|//[^\n]*", re.S),
    ".sql": re.compile(r"--[^\n]*"),
}


def minor_uses(path, label):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = COMMENTS[path.suffix].sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return [f"{label}:{number}" for number, line in enumerate(text.splitlines(), 1)
            if CODE_MINOR.search(line)]


hits = []
for folder in ("models", "routes", "utils", "templates", "static/js", "database"):
    for path in (REPO / folder).rglob("*"):
        if path.suffix in COMMENTS and "__pycache__" not in path.parts and not path.name.endswith(".min.js"):
            hits += minor_uses(path, str(path.relative_to(REPO)))
for path in (REPO / "app.py", REPO / "seed_demo_data.py", REPO / "schema.sql"):
    hits += minor_uses(path, path.name)
check("the check finds a real use: a list holding \"Minor\", a comparison, SQL",
      all(CODE_MINOR.search(line) for line in ('X = ("Single", "Minor")', 'if s == "Minor":',
                                               "WHERE civil_status = 'Minor'")))
check("no code compares or stores the civil status 'Minor' (only the migration names it)", not hits, hits)
import seed_demo_data as seed  # noqa: E402

person = {"first": "A", "middle": "B", "last": "C", "sex": "Female", "purok": 2, "conditions": [],
          "allergies": [], "contact": "09000000001", "emergency_name": "D E",
          "relationship": "Mother", "emergency_number": "09000000002"}
check("demo data: a child is Single, by age",
      seed.register_form({**person, "kind": "child", "birth": date(2015, 1, 1)}, DAY)["civil_status"] == "Single")
check("demo data: a 16-year-old in the 'adult' group is Single, by age, not Married",
      seed.register_form({**person, "kind": "adult", "birth": date(2010, 1, 1)}, DAY)["civil_status"] == "Single")
check("demo data: a 30-year-old woman is Married",
      seed.register_form({**person, "kind": "adult", "birth": date(1996, 1, 1)}, DAY)["civil_status"] == "Married")
check("demo data: the address is Purok N in Barangay Poblacion, San Francisco, Surigao del Norte",
      {k: seed.register_form({**person, "kind": "adult", "birth": date(1996, 1, 1)}, DAY)[k]
       for k in ("address", "barangay", "municipality", "province")}
      == {"address": "Purok 2", "barangay": "Poblacion", "municipality": "San Francisco",
          "province": "Surigao del Norte"})
broadcast_source = (REPO / "models" / "broadcasts.py").read_text(encoding="utf-8")
check("the SMS audience for children's parents is chosen by age (PEDIATRIC_AGE_YEARS)",
      "_patient_contacts(max_age=PEDIATRIC_AGE_YEARS)" in broadcast_source
      and "civil_status" not in broadcast_source)
check("no model or route reads civil_status to decide anything about a child",
      not [str(p.relative_to(REPO)) for folder in ("models", "routes", "utils") for p in (REPO / folder).rglob("*.py")
           if re.search(r"civil_status\s*(==|!=|in)\s", p.read_text(encoding="utf-8"))])

# ---------------------------------------------------------------------------
failed = [name for name, ok in results if not ok]
print("\n" + "=" * 78)
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
for name in failed:
    print(f"  FAILED: {name}")
print("=" * 78)
sys.exit(1 if failed else 0)

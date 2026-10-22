"""The possible-duplicate check on Register Patient and Edit Patient (Task 20).

Asked for by the RHU nurse at the user evaluation of 2026-10-12.
D1. One helper, models/patients.py find_possible_duplicates(), with normalized
    names and three rules: A exact, B similar spelling, C a mistyped birth date.
D2. It runs on registration, and on an edit that changes a name or the birth date.
    A match blocks the save until "This is a different person" is ticked, and the
    server checks the tick again against the records that match now.
D3. A save over a warning writes an audit entry holding patient IDs only.
D4. The warning shows demographic fields only, to the roles that already register
    and edit patients (Health Center Staff and the Doctor).
Every name, date and number below is made up.
"""
import re
import sqlite3
import sys

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
from models import audit as A  # noqa: E402
from models.consultations import set_consultation_restriction  # noqa: E402
from models.patients import (  # noqa: E402
    FIRST_NAME_SIMILARITY,
    LAST_NAME_SIMILARITY,
    MAX_DUPLICATE_MATCHES,
    find_possible_duplicates,
    get_patient_by_id,
    normalize_name,
)
from routes.patient_views import patient_to_form  # noqa: E402

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


def qall(sql, args=()):
    conn = db()
    try:
        return conn.execute(sql, args).fetchall()
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


def patient_count():
    return q1("SELECT COUNT(*) FROM patients")[0]


def last_audit_id():
    return q1("SELECT COALESCE(MAX(id), 0) FROM audit_logs")[0]


def audit_since(start):
    return qall("SELECT * FROM audit_logs WHERE id > ? ORDER BY id", (start,))


def warning_block(page):
    """The warning above the buttons, from its opening tag to the button bar."""
    start = page.find('id="duplicateWarning"')
    end = page.find("<!-- FORM ACTIONS -->", start)
    return page[start:end] if start != -1 and end != -1 else ""


def confirm_box_checked(page):
    tag = re.search(r'<input[^>]*id="confirmDuplicate"[^>]*>', page)
    return bool(tag) and " checked" in tag.group(0)


def seen_ids(page):
    return sorted(int(v) for v in re.findall(r'name="duplicate_seen" value="(\d+)"', page))


# Fictional patients for this suite, ids 101 and up. (id, code, first, middle,
# last, birth date, sex, address, status)
NEXT_ID = [101]


def add_patient(first, last, birth, middle=None, sex="Female", address="Purok 3, Barangay Poblacion",
                status="Active", **extra):
    patient_id = NEXT_ID[0]
    NEXT_ID[0] += 1
    columns = {
        "id": patient_id, "patient_id": f"PAT-{patient_id:03d}", "first_name": first,
        "middle_name": middle, "last_name": last, "birth_date": birth, "sex": sex,
        "civil_status": "Single", "address": address, "municipality": "San Francisco", "barangay": "Poblacion",
        "province": "Surigao del Norte", "status": status,
    }
    columns.update(extra)
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    run_sql(f"INSERT INTO patients ({names}) VALUES ({marks})", list(columns.values()))
    return patient_id


def code(patient_id):
    return f"PAT-{patient_id:03d}"


def found(first, last, birth, middle="", exclude=None):
    return find_possible_duplicates(first, middle, last, birth, exclude_patient_id=exclude)


def found_ids(*args, **kwargs):
    return [m["id"] for m in found(*args, **kwargs)]


def rule_for(patient_id, *args, **kwargs):
    for match in found(*args, **kwargs):
        if match["id"] == patient_id:
            return match["rule"]
    return None


# The record whose details must never reach the warning: conditions, allergies, a
# contact number, a blood type, an emergency contact, and a consultation (sealed).
CONTACT = "09000009911"
KIN = "Zzkin Fictional Relative"
DIAG = "ZZDIAG-SECRET-ALPHA"
PLAN = "ZZPLAN-SECRET-BRAVO"
COMPLAINT = "ZZCOMPLAINT-SECRET-CHARLIE"
SEALED_DIAG = "ZZSEALED-DIAG-DELTA"
CRISTINA = add_patient(
    "Maria Cristina", "De la Cruz", "1990-03-07", middle="Lopez",
    address="Purok 3, near the chapel",
    medical_conditions='["Asthma", "ZZCOND-ECHO"]', allergies='["ZZALLERGY-FOXTROT"]',
    contact_number=CONTACT, blood_type="AB-", emergency_contact_name=KIN,
    emergency_contact_number="09000009912",
)
for cid, diagnosis, restricted in ((901, DIAG, False), (902, SEALED_DIAG, True)):
    run_sql(
        "INSERT INTO consultations (id, patient_id, recorded_by, consultation_date, "
        "chief_complaint, diagnosis, treatment_plan) VALUES (?, ?, 5, '2026-07-01 09:00:00', ?, ?, ?)",
        (cid, CRISTINA, COMPLAINT, diagnosis, PLAN),
    )
    if restricted:
        set_consultation_restriction(cid, True, DOCTOR_ID, role="Doctor")
ROGELIO = add_patient("Rogelio", "Peña", "1975-11-20", sex="Male")
JOHN = add_patient("John", "Magbanua", "1988-05-12", sex="Male")
JUAN_CARLOS = add_patient("Juan Carlos", "Ybañez", "2001-08-15", sex="Male")
JUAN_SANTOS = add_patient("Juan", "Santos", "1980-01-15", sex="Male")
TEODORO = add_patient("Teodoro", "Alcantara", "1940-02-02", sex="Male", status="Deceased")
LUZ = add_patient("Luzviminda", "Ocampo", "1962-09-30", status="Inactive")
# Seven for one search: three exact (one with the same middle name), two similar,
# two with a mistyped date. Only five are listed.
ANA_A1 = add_patient("Ana", "Reyes", "2005-04-04")
ANA_A2 = add_patient("Ana", "Reyes", "2005-04-04", middle="Bautista")
ANA_A3 = add_patient("Ana", "Reyes", "2005-04-04")
ANA_B1 = add_patient("Anna", "Reyes", "2005-04-04")
ANA_B2 = add_patient("Anabel", "Reyes", "2005-04-04")
ANA_C1 = add_patient("Ana", "Reyes", "2005-04-05")
ANA_C2 = add_patient("Ana", "Reyes", "2005-04-14")
# The edit tests: two records that already match each other, and one that is alone.
NESTOR = add_patient("Nestor", "Gumapac", "1983-02-14", sex="Male")
NESTOR_TWIN = add_patient("Nestor", "Gumapac", "1983-02-14", sex="Male")
HERMINIO = add_patient("Herminio", "Sabado", "1955-06-06", sex="Male")

staff = client_as(STAFF_ID)
doctor = client_as(DOCTOR_ID)

# ===========================================================================
section("1. NAME NORMALIZATION")
check('"De la Cruz", "Dela Cruz", "Delacruz" and "DELA-CRUZ" are one name',
      {normalize_name(v) for v in ("De la Cruz", "Dela Cruz", "Delacruz", "DELA-CRUZ", " dela  cruz ")}
      == {"delacruz"})
check('"Ma. Cristina" and "Ma Cristina" read as "Maria Cristina" in a first name',
      normalize_name("Ma. Cristina", first_name=True) == normalize_name("Maria Cristina", first_name=True)
      == normalize_name("Ma Cristina", first_name=True) == "mariacristina")
check('"Ma" is only expanded at the start of a first name ("Mae" and a last name are left alone)',
      normalize_name("Mae", first_name=True) == "mae" and normalize_name("Ma") == "ma")
check('accents are removed: "Peña" -> "pena", "José" -> "jose", "Ybañez" -> "ybanez"',
      normalize_name("Peña") == "pena" and normalize_name("José", first_name=True) == "jose"
      and normalize_name("Ybañez") == "ybanez")
check("apostrophes and periods are removed", normalize_name("D'Angelo") == "dangelo"
      and normalize_name("Sta. Ana") == "staana")
check("suffixes typed in a name field are ignored (Jr, Sr, II, III, IV)",
      [normalize_name(v) for v in ("Juan Jr.", "Santos, Sr.", "Reyes II", "Dela Cruz III", "Lim IV")]
      == ["juan", "santos", "reyes", "delacruz", "lim"])
check("a name that is only a suffix is kept, never emptied", normalize_name("Jr") == "jr")
check("the thresholds are the agreed ones (last name 0.85, first name 0.80)",
      LAST_NAME_SIMILARITY == 0.85 and FIRST_NAME_SIMILARITY == 0.80 and MAX_DUPLICATE_MATCHES == 5)

# ===========================================================================
section("2. THE THREE RULES")
check('Rule A: the same name and birth date', rule_for(CRISTINA, "Maria Cristina", "De la Cruz", "1990-03-07") == "A")
check('Rule A after normalization: "Dela Cruz" finds "De la Cruz"',
      rule_for(CRISTINA, "Maria Cristina", "Dela Cruz", "1990-03-07") == "A")
check('... and "Delacruz"', rule_for(CRISTINA, "Maria Cristina", "Delacruz", "1990-03-07") == "A")
check('"Ma. Cristina" finds "Maria Cristina"', rule_for(CRISTINA, "Ma. Cristina", "Dela Cruz", "1990-03-07") == "A")
check('"Pena" finds "Peña"', rule_for(ROGELIO, "Rogelio", "Pena", "1975-11-20") == "A")
check("a suffix typed in the first name still finds the record",
      rule_for(ROGELIO, "Rogelio Jr.", "Peña", "1975-11-20") == "A")
check('Rule B: "Jhon" finds "John" (two neighbouring letters swapped), same birth date',
      rule_for(JOHN, "Jhon", "Magbanua", "1988-05-12") == "B")
check('Rule B: "Jhon Magbanwa" finds "John Magbanua" (last names 0.875 alike)',
      rule_for(JOHN, "Jhon", "Magbanwa", "1988-05-12") == "B")
check('Rule B: "Ma. Kristina" finds "Maria Cristina" (similar spelling)',
      rule_for(CRISTINA, "Ma. Kristina", "Dela Cruz", "1990-03-07") == "B")
check('Rule B: "Juan" finds "Juan Carlos" (one starts with the other, 3+ letters)',
      rule_for(JUAN_CARLOS, "Juan", "Ybanez", "2001-08-15") == "B")
check('Rule B needs 3 letters for the start-of-name test: "Ju" does not find "Juan Carlos"',
      JUAN_CARLOS not in found_ids("Ju", "Ybanez", "2001-08-15"))
check("Rule B needs the same birth date: Jhon born a day later is not Rule B",
      rule_for(JOHN, "Jhon", "Magbanua", "1988-05-13") is None)
check("Rule C: the day and month swapped (1990-07-03 for 1990-03-07)",
      rule_for(CRISTINA, "Maria Cristina", "Dela Cruz", "1990-07-03") == "C")
check("Rule C: one digit different in the day (1990-03-08)",
      rule_for(CRISTINA, "Ma. Cristina", "De la Cruz", "1990-03-08") == "C")
check("Rule C: one digit different in the month (1990-08-07)",
      rule_for(CRISTINA, "Maria Cristina", "De la Cruz", "1990-08-07") == "C")
check("Rule C needs the same year (1991-03-07 is not a match)",
      CRISTINA not in found_ids("Maria Cristina", "De la Cruz", "1991-03-07"))
check("Rule C needs the same name (a swapped date with a different first name is no match)",
      CRISTINA not in found_ids("Rosalinda", "De la Cruz", "1990-07-03"))
check("each match carries the plain reason the warning prints",
      [m["reason"] for m in found("Maria Cristina", "Dela Cruz", "1990-03-07")] == ["Same name and birth date"]
      and found("Jhon", "Magbanua", "1988-05-12")[0]["reason"] == "Similar name, same birth date"
      and found("Maria Cristina", "Dela Cruz", "1990-07-03")[0]["reason"] == "Same name, birth date may be mistyped")

# ===========================================================================
section("3. NO FALSE WARNINGS")
check("a clearly different first name with the same last name and birth date: no match",
      found("Pedro", "Magbanua", "1988-05-12") == [])
check("a clearly different last name with the same first name and birth date: no match",
      found("Juan", "Sanchez", "1980-01-15") == [])
check("the same common name with a clearly different birth date in the same year: no match",
      found("Juan", "Santos", "1980-06-28") == [])
check("the same common name born in another year: no match", found("Juan", "Santos", "1995-01-15") == [])
check("\"Juan\" and \"Joan\" (0.75) are not similar first names", found("Joan", "Santos", "1980-01-15") == [])
check("\"Reyes\" and \"Reyez\" (0.80) are not similar enough last names",
      ANA_A1 not in found_ids("Ana", "Reyez", "2005-04-04"))
check("a new name nobody has: no match", found("Zzwilfredo", "Zzmangubat", "1977-07-07") == [])
check("no birth date, or an invalid one: no match (nothing to compare)",
      found("Juan", "Santos", "") == [] and found("Juan", "Santos", "1980-13-45") == [])
check("the fixture patients do not match each other by accident",
      all(found(*row) == [] or all(m["id"] == pid for m in found(*row))
          for pid, *row in [(p[0], p[1], p[2], p[3]) for p in _support.PATIENTS]))

# ===========================================================================
section("4. ORDER, LIMIT, STATUS AND WHAT A MATCH HOLDS")
ana = found("Ana", "Reyes", "2005-04-04", middle="Bautista")
check(f"at most {MAX_DUPLICATE_MATCHES} are returned (7 match)", len(ana) == 5, len(ana))
check("strongest first: Rule A, then B; the Rule C matches are cut by the limit",
      [m["rule"] for m in ana] == ["A", "A", "A", "B", "B"], [m["rule"] for m in ana])
check("within Rule A, the record with the same middle name is first",
      ana[0]["id"] == ANA_A2, [m["patient_id"] for m in ana])
check("a Rule C match is listed when there is room for it",
      {m["rule"] for m in found("Ana", "Reyes", "2005-04-05")} >= {"A", "C"})
deceased = found("Teodoro", "Alcantara", "1940-02-02")
inactive = found("Luzviminda", "Ocampo", "1962-09-30")
check("a Deceased record is found and labelled Deceased",
      [(m["id"], m["status"]) for m in deceased] == [(TEODORO, "Deceased")]
      and deceased[0]["status_badge_class"] == "badge-archived")
check("an Inactive record is found and labelled Inactive",
      [(m["id"], m["status"]) for m in inactive] == [(LUZ, "Inactive")])
check("exclude_patient_id leaves out the record being edited",
      found_ids("Nestor", "Gumapac", "1983-02-14", exclude=NESTOR) == [NESTOR_TWIN]
      and found("Herminio", "Sabado", "1955-06-06", exclude=HERMINIO) == [])
match = found("Maria Cristina", "Dela Cruz", "1990-03-07")[0]
check("a match holds demographic fields only",
      set(match) == {"id", "patient_id", "full_name", "birth_date", "sex", "address", "status",
                     "status_badge_class", "rule", "reason"}, sorted(match))
check("... with the ID, full name, birth date, sex, address and status of the record",
      (match["patient_id"], match["full_name"], match["birth_date"], match["sex"], match["address"],
       match["status"]) == (code(CRISTINA), "Maria Cristina Lopez De la Cruz", "1990-03-07", "Female",
                            "Purok 3, near the chapel", "Active"), match)

# ===========================================================================
section("5. REGISTRATION: BLOCKED, KEPT, CONFIRMED, RE-CHECKED")
FORM = {
    "first_name": "Ma. Cristina", "middle_name": "", "last_name": "Dela Cruz", "birth_date": "1990-03-07",
    "sex": "Female", "civil_status": "Single", "address": "Purok 9, Zztypedaddress",
    "municipality": "San Francisco", "barangay": "Poblacion", "province": "Surigao del Norte", "zip_code": "8405",
    "contact_number": "09000003002", "emergency_contact_name": "Zztyped Kin",
    "emergency_contact_relationship": "Sibling", "emergency_contact_number": "09000003001",
    "medical_conditions_note": "Zztypednote",
}
before, start = patient_count(), last_audit_id()
r = staff.post("/staff/register-patient", data=FORM)
page = body(r)
check("a possible duplicate is not saved without confirmation",
      r.status_code == 200 and patient_count() == before and audit_since(start) == [])
check("the warning has the agreed title and text",
      "This patient may already be registered." in page
      and "Please check the records below. If one of them is the same person, open that record "
          "instead of creating a new one." in page)
block = warning_block(page)
check("the warning lists the match: ID, name, birth date, sex, address, status, reason",
      all(t in block for t in (code(CRISTINA), "Maria Cristina Lopez De la Cruz", "March 7, 1990",
                               "Female", "Purok 3, near the chapel", "Active", "Same name and birth date")), block[:600])
check("the table has the agreed headings and sits in a responsive wrapper",
      all(f">{h}</th>" in block for h in ("Patient ID", "Name", "Birth date", "Sex", "Purok / Address",
                                          "Status", "Reason")) and "table-responsive" in block)
check('each row has an "Open record" link to the profile, in a new tab',
      f'href="/staff/patient_profile/{CRISTINA}" target="_blank" rel="noopener">Open record</a>' in block, block[:900])
check('the "This is a different person" box is there and not ticked',
      "I checked these records. This is a different person." in block and not confirm_box_checked(page))
check("the page carries the ids of the records shown", seen_ids(page) == [CRISTINA], seen_ids(page))
check("every typed value is kept on the form",
      all(f'value="{FORM[k]}"' in page for k in ("first_name", "last_name", "birth_date", "address",
                                                 "contact_number", "emergency_contact_name",
                                                 "emergency_contact_number", "zip_code"))
      and "Zztypednote" in page)
check("the script that disables Save until the box is ticked is on the page",
      "getElementById('confirmDuplicate')" in page and "button.disabled" in page)
check("the old hidden auto-confirm field is gone",
      'type="hidden" name="confirm_duplicate"' not in page)

r = staff.post("/staff/register-patient", data=dict(FORM, confirm_duplicate="yes"))
check("server re-check: the tick alone, with no record ids, saves nothing",
      r.status_code == 200 and patient_count() == before and "may already be registered" in body(r))
r = staff.post("/staff/register-patient", data=dict(FORM, duplicate_seen=str(CRISTINA)))
check("server re-check: the record ids alone, without the tick, save nothing",
      r.status_code == 200 and patient_count() == before)
r = staff.post("/staff/register-patient", data=dict(FORM, confirm_duplicate="yes", duplicate_seen=str(ROGELIO)))
check("server re-check: a tick for some other record saves nothing",
      r.status_code == 200 and patient_count() == before)

# A matching record appears after the operator saw the warning.
LATE = add_patient("Maria Cristina", "De La Cruz", "1990-03-07")
r = staff.post("/staff/register-patient", data=dict(FORM, confirm_duplicate="yes", duplicate_seen=str(CRISTINA)))
page = body(r)
check("server re-check: a record that matches now but was not shown brings the warning back",
      r.status_code == 200 and patient_count() == before + 1  # only LATE, added by the suite
      and seen_ids(page) == sorted([CRISTINA, LATE]) and not confirm_box_checked(page))

start = last_audit_id()
r = staff.post("/staff/register-patient",
               data=dict(FORM, confirm_duplicate="yes", duplicate_seen=[str(CRISTINA), str(LATE)]))
new_row = q1("SELECT id, patient_id FROM patients WHERE address = 'Purok 9, Zztypedaddress'")
check("ticked, with every current match shown: the record is saved",
      r.status_code == 302 and new_row is not None and patient_count() == before + 2)
entries = audit_since(start)
dup = [e for e in entries if e["action"] == A.ACTION_PATIENT_DUPLICATE_CONFIRMED]
check("the save writes the usual 'Registered patient' entry and one possible-duplicate entry",
      [e["action"] for e in entries] == [A.ACTION_PATIENT_REGISTERED, A.ACTION_PATIENT_DUPLICATE_CONFIRMED],
      [e["action"] for e in entries])
# Both are Rule A with the same names, so they are listed in patient ID order.
expected = (f"Saved patient {new_row['patient_id'] if new_row else '?'} after a possible-duplicate "
            f"warning (matched {code(CRISTINA)}, {code(LATE)})")
check("the entry names patient IDs only, in the order the warning listed them",
      dup and dup[0]["details"] == expected, dup[0]["details"] if dup else "no entry")
check("the entry holds no name, no contact number and no clinical text",
      dup and not any(t.lower() in dup[0]["details"].lower() for t in
                      ("Cristina", "Cruz", "Zztyped", "0900000", DIAG, PLAN, COMPLAINT, SEALED_DIAG)))
check("the entry is attributed to the account that saved, in Patient Records",
      dup and dup[0]["user_id"] == STAFF_ID and dup[0]["module"] == A.MODULE_PATIENTS)

start, before = last_audit_id(), patient_count()
r = staff.post("/staff/register-patient", data=dict(
    FORM, first_name="Zzwilfredo", last_name="Zzmangubat", birth_date="1977-07-07",
    address="Purok 1, Zznewperson"))
check("a person with no match is saved at the first press, with no extra entry",
      r.status_code == 302 and patient_count() == before + 1
      and [e["action"] for e in audit_since(start)] == [A.ACTION_PATIENT_REGISTERED])

before = patient_count()
r = staff.post("/staff/register-patient", data=dict(
    FORM, emergency_contact_name="", confirm_duplicate="yes",
    duplicate_seen=[str(CRISTINA), str(LATE), str(new_row["id"])]))
page = body(r)
check("a validation error and a possible duplicate are shown together, and nothing is saved",
      r.status_code == 200 and patient_count() == before and "Emergency contact name is required." in page
      and "This patient may already be registered." in page)
check("... and a tick that covers every match stays ticked through the validation error",
      confirm_box_checked(page))

before = patient_count()
r = doctor.post("/staff/register-patient", data=dict(FORM, first_name="Jhon", last_name="Magbanua",
                                                     birth_date="1988-05-12", sex="Male"))
check("the Doctor, who also registers patients, gets the same warning",
      r.status_code == 200 and patient_count() == before
      and "Similar name, same birth date" in warning_block(body(r)))

# A Deceased record is found and labelled on the warning page.
r = staff.post("/staff/register-patient", data=dict(FORM, first_name="Teodoro", last_name="Alcantara",
                                                    birth_date="1940-02-02", sex="Male"))
block = warning_block(body(r))
check("a Deceased record is listed on the warning with its status",
      code(TEODORO) in block and "badge-archived\">Deceased<" in block)

# The check-in path: the warning keeps the visit's intent, and the confirmed save queues once.
r = staff.post("/staff/register-patient", data={"check_in_start": "1", "check_in_reason": "Zzreason",
                                                "check_in_service": "Consultation"})
form = dict(FORM, first_name="Luzviminda", last_name="Ocampo", birth_date="1962-09-30",
            address="Purok 4, Zzcheckin", check_in="1", check_in_reason="Zzreason",
            check_in_service="Consultation")
before = patient_count()
r = staff.post("/staff/register-patient", data=form)
page = body(r)
check("from the Check In dialog: the warning keeps the check-in fields, and nothing is saved",
      r.status_code == 200 and patient_count() == before and 'name="check_in" value="1"' in page
      and code(LUZ) in warning_block(page) and "Inactive" in warning_block(page))
r = staff.post("/staff/register-patient", data=dict(form, confirm_duplicate="yes", duplicate_seen=str(LUZ)))
saved = q1("SELECT id FROM patients WHERE address = 'Purok 4, Zzcheckin'")
check("... and the confirmed save registers and queues the patient once",
      r.status_code == 302 and saved is not None
      and q1("SELECT COUNT(*) FROM appointments WHERE patient_id = ?", (saved["id"],))[0] == 1)

# ===========================================================================
section("6. EDITING")


def edit_form(patient_id, **changes):
    form = patient_to_form(get_patient_by_id(patient_id))
    form.update({"emergency_contact_name": "Zzedit Kin", "emergency_contact_relationship": "Sibling",
                 "emergency_contact_number": "09000003003", "zip_code": "8405"})
    form.update(changes)
    return form


# Give NESTOR the required fields the fixture row does not have, with no name change.
r = staff.post(f"/staff/register-patient/{NESTOR}", data=edit_form(NESTOR))
check("setup: an edit of the other fields of a record that already has a twin saves",
      r.status_code == 302, r.status_code)
start = last_audit_id()
r = staff.post(f"/staff/register-patient/{NESTOR}", data=edit_form(NESTOR, address="Purok 7, Zzmoved"))
check("the check does NOT run when only other fields change (the twin is not mentioned)",
      r.status_code == 302 and q1("SELECT address FROM patients WHERE id = ?", (NESTOR,))[0] == "Purok 7, Zzmoved"
      and A.ACTION_PATIENT_DUPLICATE_CONFIRMED not in [e["action"] for e in audit_since(start)])
r = staff.post(f"/staff/register-patient/{NESTOR}", data=edit_form(NESTOR, middle_name="Zzmiddle"))
page = body(r)
check("the check runs when a name changes, and the edit is not saved",
      r.status_code == 200 and q1("SELECT middle_name FROM patients WHERE id = ?", (NESTOR,))[0] is None
      and seen_ids(page) == [NESTOR_TWIN])
check("the edit warning lists the other record, never the record being edited",
      code(NESTOR_TWIN) in warning_block(page) and code(NESTOR) not in warning_block(page)
      and f"/staff/patient_profile/{NESTOR}\"" not in warning_block(page))
check("the edit warning says to open that record instead of saving these changes",
      "open that record instead of saving these changes." in page)
check("the edit form keeps the typed value", 'value="Zzmiddle"' in page)
start = last_audit_id()
r = staff.post(f"/staff/register-patient/{NESTOR}",
               data=edit_form(NESTOR, middle_name="Zzmiddle", confirm_duplicate="yes",
                              duplicate_seen=str(NESTOR_TWIN)))
entries = audit_since(start)
check("ticked: the edit is saved",
      r.status_code == 302 and q1("SELECT middle_name FROM patients WHERE id = ?", (NESTOR,))[0] == "Zzmiddle")
check("... with the usual 'Updated patient record' entry and an IDs-only possible-duplicate entry",
      [e["action"] for e in entries] == [A.ACTION_PATIENT_UPDATED, A.ACTION_PATIENT_DUPLICATE_CONFIRMED]
      and entries[1]["details"] == f"Saved patient {code(NESTOR)} after a possible-duplicate warning "
                                   f"(matched {code(NESTOR_TWIN)})",
      [(e["action"], e["details"]) for e in entries])
r = staff.post(f"/staff/register-patient/{NESTOR}", data=edit_form(NESTOR, birth_date="1983-02-15"))
check("the check runs when the birth date changes (Rule C finds the twin, not saved)",
      r.status_code == 200 and seen_ids(body(r)) == [NESTOR_TWIN]
      and q1("SELECT birth_date FROM patients WHERE id = ?", (NESTOR,))[0] == "1983-02-14")
r = staff.post(f"/staff/register-patient/{HERMINIO}", data=edit_form(HERMINIO, first_name="Herminio Jr."))
check("an edit never matches the record itself (a name change that normalizes to the same name saves)",
      r.status_code == 302 and q1("SELECT first_name FROM patients WHERE id = ?", (HERMINIO,))[0] == "Herminio Jr.")
r = staff.post(f"/staff/register-patient/{HERMINIO}", data=edit_form(HERMINIO, first_name="Herminio Jr.",
                                                                       birth_date="1955-06-07"))
check("... nor through a near birth date of its own", r.status_code == 302)

# ===========================================================================
section("7. ROLES")
official, admin = client_as(OFFICIAL_ID), client_as(ADMIN_ID)
for label, client in (("the Barangay Official", official), ("the Administrator", admin)):
    before = patient_count()
    get_new = client.get("/staff/register-patient")
    get_edit = client.get(f"/staff/register-patient/{CRISTINA}")
    post = client.post("/staff/register-patient", data=dict(FORM, first_name="Zzofficial"))
    check(f"{label} cannot open Register Patient or Edit Patient (sent to their dashboard)",
          get_new.status_code == 302 and get_edit.status_code == 302
          and "may already be registered" not in body(get_new) + body(get_edit))
    check(f"... and a POST from {label} saves nothing and shows no warning",
          post.status_code == 302 and patient_count() == before and "may already be registered" not in body(post))

# ===========================================================================
section("8. PRIVACY: THE WARNING PAGE SHOWS NO CLINICAL OR SEALED FIELDS")
r = staff.post("/staff/register-patient", data=FORM)
page, block = body(r), warning_block(body(r))
check("setup: the warning lists the record that has conditions, allergies and consultations",
      code(CRISTINA) in block)
check("the warning holds none of that record's conditions, allergies or blood type",
      not any(t in block for t in ("Asthma", "ZZCOND-ECHO", "ZZALLERGY-FOXTROT", "AB-")), block[:600])
check("the warning holds none of that record's contact number or emergency contact",
      CONTACT not in block and KIN not in block and "09000009912" not in block)
check("the page holds no diagnosis, treatment plan or complaint, sealed or not",
      not any(t in page for t in (DIAG, PLAN, COMPLAINT, SEALED_DIAG)))
check("the page holds none of that record's private fields anywhere",
      not any(t in page for t in (CONTACT, KIN, "ZZCOND-ECHO", "ZZALLERGY-FOXTROT")))
sealed = q1("SELECT is_restricted FROM consultations WHERE id = 902")
check("setup: the record's second consultation is sealed", sealed is not None and sealed[0] == 1)

# ---------------------------------------------------------------------------
failed = [name for name, ok in results if not ok]
print("\n" + "=" * 78)
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
for name in failed:
    print(f"  FAILED: {name}")
print("=" * 78)
sys.exit(1 if failed else 0)

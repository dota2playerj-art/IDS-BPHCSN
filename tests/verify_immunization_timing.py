"""Vaccines only when due (Task 13): a dose is eligible only when the child has reached its minimum
age, the previous dose of its series is on file and valid, and the minimum interval has passed.

The adviser's finding: a 1-month-old had a dose recorded, then at a second consultation the form
still allowed ticking a vaccine meant for older babies. A dose given too early does not count and
must be repeated, so the child gets an extra injection. Basis: WHO routine immunization tables
(Pentavalent, OPV and PCV from 6 weeks with at least 4 weeks between doses; measles-containing
vaccine dose 1 at 9 months and at least 4 weeks between MCV1 and MCV2) and ACIP's 4-day grace period
when checking records of doses given elsewhere.
"""
import re
import sqlite3
import sys
from datetime import timedelta

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5

import models.immunizations as imm  # noqa: E402
from models.patients import get_patient_by_id  # noqa: E402
from utils.dates import display_date, today  # noqa: E402

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


def flat(text):
    from html import unescape
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)))


TODAY = today()
staff, doctor, admin = client_as(STAFF_ID), client_as(DOCTOR_ID), client_as(ADMIN_ID)
FORM = {"chief_complaint": "check", "temperature": "36.8", "blood_pressure": "100/60", "weight": "6"}
URL = "/staff/patient_profile/{}/dose-elsewhere"
_next = [q1("SELECT MAX(id) FROM patients")[0] + 1]


def child(tag, age_days):
    """A new patient born age_days ago. Returns (id, birth date)."""
    pid = _next[0]
    _next[0] += 1
    birth = TODAY - timedelta(days=age_days)
    run_sql("INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, sex, civil_status, "
            "address, municipality, province, contact_number, status) VALUES (?, ?, ?, 'Timing', ?, "
            "'Female', 'Single', 'Purok 1', 'San Francisco', 'Surigao del Norte', ?, 'Active')",
            (pid, f"PAT-{pid:03d}", f"Zztm{tag}", birth.isoformat(), f"0900000{pid:04d}"))
    return pid, birth


def months_ago(months):
    """The birth date of a child exactly `months` calendar months old today."""
    return imm.add_months(TODAY, -months)


def child_born(tag, birth):
    pid = _next[0]
    _next[0] += 1
    run_sql("INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, sex, civil_status, "
            "address, municipality, province, contact_number, status) VALUES (?, ?, ?, 'Timing', ?, "
            "'Female', 'Single', 'Purok 1', 'San Francisco', 'Surigao del Norte', ?, 'Active')",
            (pid, f"PAT-{pid:03d}", f"Zztm{tag}", birth.isoformat(), f"0900000{pid:04d}"))
    return pid


def put_dose(pid, key, day, evidence="given_here"):
    code, number = key.split(":")
    run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
            "administered_by) VALUES (?, ?, ?, ?, ?, ?)", (pid, code, int(number), evidence, day.isoformat(), STAFF_ID))


def status(pid):
    with app.app_context():
        return imm.get_immunization_status(get_patient_by_id(pid))


def item(pid, key):
    return next(i for i in status(pid)["schedule"] if i["key"] == key)


def n_doses(pid):
    return q1("SELECT COUNT(*) FROM immunizations WHERE patient_id = ?", (pid,))[0]


def open_visit(pid):
    return run_sql(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, status, "
        "is_walkin, checked_in_at) VALUES (?, ?, 'Consultation', ?, 'In Consultation', 1, ?)",
        (pid, STAFF_ID, TODAY.isoformat(), f"{TODAY.isoformat()} 08:00:00"))


def finish(visit):
    run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (visit,))


def give(client, pid, keys, extra=None):
    """Post the consultation form with these doses ticked as given today. Returns (response, visit)."""
    visit = open_visit(pid)
    data = dict(FORM, immunizations=list(keys), **(extra or {}))
    response = client.post(f"/staff/consultation/record/{visit}", data=data)
    return response, visit


def given_keys(pid):
    return sorted(f"{r['vaccine_code']}:{r['dose_number']}" for r in
                  db().execute("SELECT vaccine_code, dose_number FROM immunizations WHERE patient_id = ?", (pid,)))


def tick_markup(page, key):
    return re.search(r'name="immunizations"\s+value="%s"' % re.escape(key), page) is not None


# ---------------------------------------------------------------------------
section("0. THE TABLE: ONE RULE PER SCHEDULED DOSE, AS NAMED VALUES NEXT TO THE SCHEDULE")
check("every scheduled dose has a rule, and every rule names a scheduled dose",
      set(imm.DOSE_RULES) == set(imm.SCHEDULE_KEYS) and len(imm.DOSE_RULES) == len(imm.EPI_SCHEDULE) == 14)
rules = imm.DOSE_RULES
check("Pentavalent, OPV and PCV: minimum age 6 weeks, each dose needs the previous one and 4 weeks after it",
      all(rules[(c, n)].min_age_value == 6 and rules[(c, n)].min_age_unit == "weeks"
          and rules[(c, n)].previous == ((c, n - 1) if n > 1 else None)
          and rules[(c, n)].min_interval_weeks == (4 if n > 1 else 0)
          for c in ("PENTA", "OPV", "PCV") for n in (1, 2, 3)))
check("BCG and Hepatitis B from birth; IPV from 14 weeks; MR from 9 months; MMR from 12 months and 4 weeks "
      "after MR", rules[("BCG", 1)].min_age_value == 0 and rules[("HEPB", 1)].min_age_value == 0
      and (rules[("IPV", 1)].min_age_value, rules[("IPV", 1)].min_age_unit) == (14, "weeks")
      and (rules[("MR", 1)].min_age_value, rules[("MR", 1)].min_age_unit) == (9, "months")
      and (rules[("MMR", 1)].min_age_value, rules[("MMR", 1)].min_age_unit) == (12, "months")
      and rules[("MMR", 1)].previous == ("MR", 1) and rules[("MMR", 1)].min_interval_weeks == 4)
check("the grace period for a record of a dose given elsewhere is 4 days (ACIP)", imm.RECORD_GRACE_DAYS == 4)
check("the recommended ages shown to users are unchanged",
      [(r[0], r[3], r[5], r[6]) for r in imm.EPI_SCHEDULE if r[0] in ("PENTA", "MR", "MMR", "IPV")]
      == [("PENTA", 1, 6, "weeks"), ("PENTA", 2, 10, "weeks"), ("PENTA", 3, 14, "weeks"), ("IPV", 1, 14, "weeks"),
          ("MR", 1, 9, "months"), ("MMR", 1, 12, "months")])

# ---------------------------------------------------------------------------
section("1. THE ADVISER'S SCENARIO: A 1-MONTH-OLD")
infant, infant_birth = child("A", 30)
six_weeks = infant_birth + timedelta(weeks=6)
visit = open_visit(infant)
page = body(staff.get(f"/staff/consultation/record/{visit}"))
check("a 1-month-old: Pentavalent, OPV and PCV dose 1 show greyed out with the earliest date, not a tick box",
      all(not tick_markup(page, f"{c}:1") for c in ("PENTA", "OPV", "PCV"))
      and flat(page).count(f"From {display_date(six_weeks)}") >= 3, flat(page)[flat(page).find("Pentavalent"):][:300])
check("... and a later dose says what it needs first",
      "Needs Pentavalent dose 1 first" in flat(page) and "Needs OPV dose 1 first" in flat(page)
      and not tick_markup(page, "PENTA:2"))
check("... while a dose that is allowed at birth (BCG, Hepatitis B) is still a tick box",
      tick_markup(page, "BCG:1") and tick_markup(page, "HEPB:1"))
check("... and MR and MMR are greyed out with their dates",
      not tick_markup(page, "MR:1") and not tick_markup(page, "MMR:1")
      and f"From {display_date(imm.add_months(infant_birth, 9))}" in flat(page))
finish(visit)
before_consults = q1("SELECT COUNT(*) FROM consultations WHERE patient_id = ?", (infant,))[0]
for key in ("PENTA:1", "OPV:1", "PCV:1"):
    response, visit = give(staff, infant, [key])
    text = flat(body(response))
    check(f"a forged POST for {key} for the 1-month-old is refused, with the earliest date",
          "This dose is not due yet. Earliest date: " + display_date(six_weeks) in text
          and n_doses(infant) == 0
          and q1("SELECT COUNT(*) FROM consultations WHERE patient_id = ?", (infant,))[0] == before_consults, text[:300])
    finish(visit)
response, visit = give(staff, infant, ["PENTA:2"])
check("a forged POST for Pentavalent dose 2 says it needs dose 1 first",
      "not due yet. Needs Pentavalent dose 1 first" in flat(body(response)) and n_doses(infant) == 0)
finish(visit)
response, visit = give(staff, infant, ["BCG:1", "HEPB:1"])
check("a dose that is allowed (BCG, Hepatitis B at birth) saves, two in one visit",
      given_keys(infant) == ["BCG:1", "HEPB:1"], flat(body(response))[:200])
finish(visit)
response, visit = give(staff, infant, ["BCG:1"])
check("a dose already given cannot be given again: refused, nothing changes",
      "already recorded" in flat(body(response)) and given_keys(infant) == ["BCG:1", "HEPB:1"])
finish(visit)
response, visit = give(doctor, infant, ["PENTA:1"])
check("the Doctor is held to the same rule", "not due yet" in flat(body(response)) and n_doses(infant) == 2)
finish(visit)

# ---------------------------------------------------------------------------
section("2. AT 6 WEEKS: THREE DOSES IN ONE VISIT; THE NEXT NEEDS 4 WEEKS")
six, _ = child("B", 42)
visit = open_visit(six)
page = body(staff.get(f"/staff/consultation/record/{visit}"))
check("at exactly 6 weeks, dose 1 of Pentavalent, OPV and PCV are tick boxes; dose 2 is not",
      all(tick_markup(page, f"{c}:1") for c in ("PENTA", "OPV", "PCV"))
      and not tick_markup(page, "PENTA:2") and not tick_markup(page, "IPV:1"))
finish(visit)
day_before, _ = child("B0", 41)
check("one day before 6 weeks, they are not eligible", not item(day_before, "PENTA:1")["eligible"]
      and item(day_before, "PENTA:1")["earliest_date"] == TODAY + timedelta(days=1))
response, visit = give(staff, six, ["PENTA:1", "OPV:1", "PCV:1"])
check("Pentavalent, OPV and PCV dose 1 can all be given in one visit (co-administration)",
      given_keys(six) == ["OPV:1", "PCV:1", "PENTA:1"], flat(body(response))[:200])
finish(visit)
response, visit = give(staff, six, ["PENTA:2"])
check("dose 2 is refused until 4 weeks after dose 1: the earliest date is 4 weeks on",
      f"Earliest date: {display_date(TODAY + timedelta(weeks=4))}" in flat(body(response))
      and "PENTA:2" not in given_keys(six))
finish(visit)
mid, _ = child("C", 84)   # 12 weeks
put_dose(mid, "PENTA:1", TODAY - timedelta(days=27))
check("27 days after dose 1: dose 2 is not eligible, earliest tomorrow",
      not item(mid, "PENTA:2")["eligible"] and item(mid, "PENTA:2")["earliest_date"] == TODAY + timedelta(days=1))
response, visit = give(staff, mid, ["PENTA:2"])
check("... and a POST for it is refused", "not due yet" in flat(body(response)) and given_keys(mid) == ["PENTA:1"])
finish(visit)
run_sql("UPDATE immunizations SET date_administered = ? WHERE patient_id = ?",
        ((TODAY - timedelta(days=28)).isoformat(), mid))
check("28 days after dose 1: dose 2 is eligible", item(mid, "PENTA:2")["eligible"])
response, visit = give(staff, mid, ["PENTA:2"])
check("... and it is recorded", given_keys(mid) == ["PENTA:1", "PENTA:2"], flat(body(response))[:200])
finish(visit)
response, visit = give(staff, mid, ["PENTA:3"])
check("dose 3 right after dose 2 is refused (the interval counts from dose 2)",
      "not due yet" in flat(body(response)) and given_keys(mid) == ["PENTA:1", "PENTA:2"])
finish(visit)
skip, _ = child("D", 120)
response, visit = give(staff, skip, ["PENTA:3"])
check("dose 3 with no dose 2 on file is refused: it needs dose 2 first",
      "Needs Pentavalent dose 2 first" in flat(body(response)) and n_doses(skip) == 0)
finish(visit)
parent_only, _ = child("E", 100)
put_dose(parent_only, "PENTA:1", TODAY - timedelta(days=60), "parent_report")
check("a parent's report of dose 1 is not enough for dose 2 (it does not count)",
      not item(parent_only, "PENTA:2")["eligible"]
      and item(parent_only, "PENTA:2")["eligibility_reason"] == "Needs Pentavalent dose 1 first"
      and item(parent_only, "PENTA:1")["eligible"])
ipv_young, _ = child("F", 97)   # 13 weeks 6 days
ipv_old, _ = child("G", 98)
check("IPV: not before 14 weeks, allowed at 14 weeks",
      not item(ipv_young, "IPV:1")["eligible"] and item(ipv_old, "IPV:1")["eligible"])

# ---------------------------------------------------------------------------
section("3. MEASLES: MR AT 9 MONTHS; MMR AT 12 MONTHS AND 4 WEEKS AFTER MR")
young_mr = child_born("H", months_ago(9) + timedelta(days=1))
ok_mr = child_born("I", months_ago(9))
check("MR is refused the day before 9 months and allowed at 9 months",
      not item(young_mr, "MR:1")["eligible"] and item(ok_mr, "MR:1")["eligible"])
response, visit = give(staff, young_mr, ["MR:1"])
check("a forged POST for MR before 9 months is refused with its date",
      f"Earliest date: {display_date(TODAY + timedelta(days=1))}" in flat(body(response)) and n_doses(young_mr) == 0)
finish(visit)
no_mr = child_born("J", months_ago(13))
check("MMR with no MR on file needs MR first", item(no_mr, "MMR:1")["eligibility_reason"] == "Needs MR first")
response, visit = give(staff, no_mr, ["MMR:1"])
check("... and a forged POST for it is refused", "Needs MR first" in flat(body(response)) and n_doses(no_mr) == 0)
finish(visit)
too_young_mmr = child_born("K", months_ago(12) + timedelta(days=1))
put_dose(too_young_mmr, "MR:1", TODAY - timedelta(days=60))
check("MMR is refused before 12 months even with MR long ago",
      not item(too_young_mmr, "MMR:1")["eligible"]
      and item(too_young_mmr, "MMR:1")["earliest_date"] == TODAY + timedelta(days=1))
recent_mr = child_born("L", months_ago(13))
put_dose(recent_mr, "MR:1", TODAY - timedelta(days=27))
check("MMR within 4 weeks of MR is refused", not item(recent_mr, "MMR:1")["eligible"]
      and item(recent_mr, "MMR:1")["earliest_date"] == TODAY + timedelta(days=1))
response, visit = give(staff, recent_mr, ["MMR:1"])
check("... by the server too", "not due yet" in flat(body(response)) and given_keys(recent_mr) == ["MR:1"])
finish(visit)
run_sql("UPDATE immunizations SET date_administered = ? WHERE patient_id = ?",
        ((TODAY - timedelta(days=28)).isoformat(), recent_mr))
response, visit = give(staff, recent_mr, ["MMR:1"])
check("4 weeks after MR, at 12 months or more, MMR is given", given_keys(recent_mr) == ["MMR:1", "MR:1"],
      flat(body(response))[:200])
finish(visit)

# ---------------------------------------------------------------------------
section("4. A CARD DOSE IS HISTORY: RECORDED WITH ITS REAL DATE, AND TOO EARLY MEANS IT DOES NOT COUNT")


def card(pid, key, day):
    return staff.post(URL.format(pid), data={"dose_key": key, "evidence": "card",
                                             "date_given": day.isoformat(), "place_given": "District hospital"})


def counts_in_coverage():
    with app.app_context():
        c = imm.get_immunization_coverage()
        return c["doses_elsewhere"], c["doses_given"], c["enrolled"]


early5, birth5 = child("M", 200)
cov_before = counts_in_coverage()
r = card(early5, "PENTA:1", birth5 + timedelta(days=42 - 5))
it = item(early5, "PENTA:1")
check("a card dose 5 days before the minimum age is recorded, but reads 'Given too early — ask the Doctor "
      "about a repeat' (amber)",
      it["on_file"] and it["status"] == "Given too early — ask the Doctor about a repeat"
      and it["badge_class"] == "badge-waiting" and it["too_early"], dict(it))
check("... and it does not count as given", not it["given"] and status(early5)["completed_count"] == 0)
check("... the message says so", "too early" in flat(body(staff.get(f"/staff/patient_profile/{early5}"))))
check("... it does not count in coverage", counts_in_coverage() == cov_before, (counts_in_coverage(), cov_before))
check("... it does not make the next dose eligible",
      not item(early5, "PENTA:2")["eligible"] and item(early5, "PENTA:2")["eligibility_reason"] == "Needs Pentavalent dose 1 first")
check("... the profile shows it, amber, with the Doctor wording",
      "Given too early — ask the Doctor about a repeat" in body(staff.get(f"/staff/patient_profile/{early5}")))
with app.app_context():
    on_list = early5 in imm.get_immunization_alert()["patient_ids"]
check("... the dose itself is on the child's follow-up items, because it must be repeated, and the "
      "child is on the follow-up list",
      on_list and item(early5, "PENTA:1")["needs_attention"]
      and any(i["key"] == "PENTA:1" for i in status(early5)["attention_items"])
      and status(early5)["too_early_count"] == 1)
early3, birth3 = child("N", 200)
card(early3, "PENTA:1", birth3 + timedelta(days=42 - 3))
check("a card dose 3 days early is inside the 4-day grace and counts",
      item(early3, "PENTA:1")["status"] == "Given elsewhere" and item(early3, "PENTA:1")["given"]
      and not item(early3, "PENTA:1")["too_early"])
early4, birth4 = child("O", 200)
card(early4, "PENTA:1", birth4 + timedelta(days=42 - 4))
check("4 days early still counts (the grace is 4 days)", item(early4, "PENTA:1")["given"])
interval_early, birth_i = child("P", 220)
card(interval_early, "PENTA:1", birth_i + timedelta(days=50))
card(interval_early, "PENTA:2", birth_i + timedelta(days=50 + 28 - 5))
check("a card dose 5 days before the minimum interval after the previous dose is too early",
      item(interval_early, "PENTA:2")["too_early"] and not item(interval_early, "PENTA:2")["given"]
      and item(interval_early, "PENTA:1")["given"])
interval_ok, birth_j = child("Q", 220)
card(interval_ok, "PENTA:1", birth_j + timedelta(days=50))
card(interval_ok, "PENTA:2", birth_j + timedelta(days=50 + 28 - 3))
check("3 days before the minimum interval counts", item(interval_ok, "PENTA:2")["given"])
mr_early, birth_m = child("R", 330)
card(mr_early, "MR:1", imm.add_months(birth_m, 9) - timedelta(days=5))
check("a card MR dose 5 days before 9 months is too early", item(mr_early, "MR:1")["too_early"])
chain, birth_c = child("S", 330)
card(chain, "PENTA:1", birth_c + timedelta(days=30))
check("a card dose at 30 days old is too early, and then dose 2 is not eligible (needs a valid dose 1)",
      item(chain, "PENTA:1")["too_early"] and not item(chain, "PENTA:2")["eligible"])
# the consultation form's own 'given elsewhere' path
form_child, birth_f = child("T", 200)
visit = open_visit(form_child)
r = staff.post(f"/staff/consultation/record/{visit}", data=dict(
    FORM, immunizations_elsewhere=["PENTA:1"], elsewhere_proof_PENTA_1="card",
    elsewhere_date_PENTA_1=(birth_f + timedelta(days=35)).isoformat()))
check("a card dose reported on the consultation form 7 days early is saved and flagged too early",
      item(form_child, "PENTA:1")["too_early"] and not item(form_child, "PENTA:1")["given"])
finish(visit)
card_then, birth_k = child("U", 200)
visit = open_visit(card_then)
r = staff.post(f"/staff/consultation/record/{visit}", data=dict(
    FORM, immunizations_elsewhere=["PENTA:1"], elsewhere_proof_PENTA_1="card",
    elsewhere_date_PENTA_1=(birth_k + timedelta(days=60)).isoformat(), immunizations=["PENTA:2"]))
check("a card dose reported at this visit (given 140 days ago) lets the next dose be given at the same visit",
      given_keys(card_then) == ["PENTA:1", "PENTA:2"], flat(body(r))[:200])
finish(visit)

# the Administrator and Official do not reach any of it
check("the Administrator cannot record a dose (no route), so none of it applies to him",
      admin.post(f"/admin/consultation/record/{open_visit(infant)}", data=dict(FORM, immunizations=["BCG:1"])).status_code == 404)

passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)

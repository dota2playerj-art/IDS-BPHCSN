"""Vaccines only when due (Task 13), and every dose judged by one rule, and repeats (Task 14).

Task 13: a dose is eligible only when the child has reached its minimum age, the previous dose of its
series is on file and valid, and the minimum interval has passed. Task 14: ONE rule judges every recorded
dose, whatever its evidence: a dose more than 4 days before its minimum age or interval is invalid, stays
in the history, and does not count; the same dose can then be repeated as a new record, and the next dose
is judged from the repeat.

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

# ---------------------------------------------------------------------------
# TASK 14: EVERY DOSE JUDGED BY ONE RULE, AND REPEATS
# ---------------------------------------------------------------------------
import os  # noqa: E402
import shutil  # noqa: E402

from models.audit import ACTION_IMMUNIZATION_CORRECTED  # noqa: E402


def _raises(fn):
    try:
        fn()
        return False
    except sqlite3.IntegrityError:
        return True


MSG = "Given too early — ask the Doctor about a repeat"
PROFILE = "/staff/patient_profile/{}"
CORRECT = "/staff/patient_profile/{}/correct-vaccination"


def rows_of(pid, key):
    code, number = key.split(":")
    return [dict(r) for r in db().execute(
        "SELECT * FROM immunizations WHERE patient_id = ? AND vaccine_code = ? AND dose_number = ? "
        "ORDER BY id", (pid, code, int(number)))]


def coverage_numbers():
    with app.app_context():
        c = imm.get_immunization_coverage()
        d = imm.get_dose_coverage()
        penta1 = next(x for x in d["doses"] if (x["code"], x["dose_number"]) == ("PENTA", 1))
        return (c["doses_given"], c["doses_administered"], c["doses_elsewhere"], c["enrolled"],
                penta1["given"], d["total_given"])


def correct(pid, record_id, key, day):
    return staff.post(CORRECT.format(pid), data={"record_kind": "epi", "record_id": str(record_id),
                                                 "correct_vaccine": key, "correct_date": day.isoformat()},
                      follow_redirects=True)


section("5. TASK 14: ONE RULE FOR EVERY DOSE: 5 DAYS EARLY IS INVALID, 3 DAYS EARLY COUNTS, WHATEVER THE EVIDENCE")
for evidence in ("given_here", "card"):
    kid5, b5 = child("V" + evidence[:1], 200)
    put_dose(kid5, "PENTA:1", b5 + timedelta(days=42 - 5), evidence)
    it = item(kid5, "PENTA:1")
    check(f"a dose ({evidence}) given 5 days before its minimum age is invalid: it reads the Doctor message, "
          "amber, does not count, and stays on file",
          it["too_early"] and it["status"] == MSG and it["badge_class"] == "badge-waiting"
          and not it["given"] and it["on_file"] and status(kid5)["completed_count"] == 0, dict(it))
    check(f"... ({evidence}) the profile shows the message", MSG in body(staff.get(PROFILE.format(kid5))))
    for days_early, counts in ((3, True), (4, True)):
        kid3, b3 = child("W" + evidence[:1] + str(days_early), 200)
        put_dose(kid3, "PENTA:1", b3 + timedelta(days=42 - days_early), evidence)
        check(f"a dose ({evidence}) {days_early} days early is inside the 4-day grace and counts",
              item(kid3, "PENTA:1")["given"] and not item(kid3, "PENTA:1")["too_early"]
              and status(kid3)["completed_count"] == 1)
base_kid, base_birth = child("XA", 200)
cov_before = coverage_numbers()
bad_kid, bad_birth = child("XB", 200)
put_dose(bad_kid, "PENTA:1", bad_birth + timedelta(days=30))
check("an invalid dose given here does not count in coverage (doses, enrolled, the dose's own coverage)",
      coverage_numbers() == cov_before, (coverage_numbers(), cov_before))
with app.app_context():
    alert = imm.get_immunization_alert()
check("... and the child stays on the follow-up list, with the dose among the items to follow up",
      bad_kid in alert["patient_ids"] and any(i["key"] == "PENTA:1" for i in status(bad_kid)["attention_items"]))
done = child_born("XC", months_ago(20))
for key, days in (("BCG:1", 0), ("HEPB:1", 0), ("PENTA:1", 50), ("OPV:1", 50), ("PCV:1", 50),
                  ("PENTA:2", 90), ("OPV:2", 90), ("PCV:2", 90), ("PENTA:3", 130), ("OPV:3", 130),
                  ("PCV:3", 130), ("IPV:1", 120)):
    put_dose(done, key, months_ago(20) + timedelta(days=days))
put_dose(done, "MR:1", imm.add_months(months_ago(20), 9) + timedelta(days=10))
put_dose(done, "MMR:1", imm.add_months(months_ago(20), 12) + timedelta(days=40))
check("a child with all 14 doses valid is complete", status(done)["completed_count"] == 14
      and "schedule complete" in status(done)["summary"])
mmr_row = rows_of(done, "MMR:1")[0]["id"]
run_sql("UPDATE immunizations SET date_administered = ? WHERE id = ?",
        ((imm.add_months(months_ago(20), 9) + timedelta(days=10) + timedelta(days=20)).isoformat(), mmr_row))
check("moving one dose to 20 days after its previous dose makes it invalid: 13 count, not complete",
      status(done)["completed_count"] == 13 and "schedule complete" not in status(done)["summary"]
      and status(done)["too_early_count"] == 1)

# ---------------------------------------------------------------------------
section("6. TASK 14: A DOSE GIVEN TOO EARLY IS REPEATED AS A NEW RECORD")
rep, birth_r = child("YA", 50)
early_day = birth_r + timedelta(days=30)
put_dose(rep, "PENTA:1", early_day)
gate = early_day + timedelta(weeks=4)
v = item(rep, "PENTA:1")
check("the dose has only an invalid record: it must be repeated, and it is on the follow-up items",
      v["too_early"] and v["needs_attention"] and v["status"] == MSG)
check("... it becomes eligible again from the later of its minimum age and the invalid date + 4 weeks",
      not v["eligible"] and v["earliest_date"] == gate and gate > birth_r + timedelta(days=42), dict(v))
response, visit = give(staff, rep, ["PENTA:1"])
check("a forged POST for the repeat before that date is refused with the earliest date, nothing saved",
      f"Earliest date: {display_date(gate)}" in flat(body(response)) and len(rows_of(rep, "PENTA:1")) == 1)
finish(visit)
run_sql("UPDATE immunizations SET date_administered = ? WHERE patient_id = ?",
        ((birth_r + timedelta(days=20)).isoformat(), rep))
check("once the interval has passed since the invalid dose, the dose is eligible again",
      item(rep, "PENTA:1")["eligible"])
visit = open_visit(rep)
page = body(staff.get(f"/staff/consultation/record/{visit}"))
check("... and the consultation form offers it as a tick box, with the earlier dose named under it",
      tick_markup(page, "PENTA:1") and "was too early" in flat(page))
finish(visit)
response, visit = give(staff, rep, ["PENTA:1"])
two = rows_of(rep, "PENTA:1")
check("the repeat is recorded at a consultation as a NEW record: two records of the dose, the earlier one untouched",
      len(two) == 2 and two[0]["date_administered"] == (birth_r + timedelta(days=20)).isoformat()
      and two[1]["date_administered"] == TODAY.isoformat() and two[1]["evidence"] == "given_here",
      flat(body(response))[:200])
finish(visit)
it = item(rep, "PENTA:1")
check("the repeat counts: the dose reads Completed, with the repeat's record behind its row",
      it["given"] and it["status"] == "Completed" and not it["too_early"] and it["record_id"] == two[1]["id"]
      and status(rep)["completed_count"] == 1)
check("... the invalid record stays in the history under the dose's row",
      [h["kind"] for h in it["history"]] == ["too_early"] and it["history"][0]["record"]["id"] == two[0]["id"])
text = flat(body(staff.get(PROFILE.format(rep))))
check("... the profile says 'Earlier dose on <date> was too early' under the row",
      f"Earlier dose on {display_date(birth_r + timedelta(days=20))} was too early" in text)
response, visit = give(staff, rep, ["PENTA:1"])
check("a second valid record of the dose is refused by the form's server check",
      "already recorded" in flat(body(response)) and len(rows_of(rep, "PENTA:1")) == 2)
finish(visit)
with app.app_context():
    again = imm.record_immunizations(rep, [("PENTA", 1)], STAFF_ID, TODAY)
check("... by the model itself", again == [] and len(rows_of(rep, "PENTA:1")) == 2)
r = card(rep, "PENTA:1", birth_r + timedelta(days=45))
check("... and a card record of the same dose, from the profile: refused, nothing added",
      "is already recorded as given" in flat(body(staff.get(PROFILE.format(rep))))
      and len(rows_of(rep, "PENTA:1")) == 2)
parent_row = run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, "
                     "administered_by) VALUES (?, 'PENTA', 1, 'parent_report', ?)", (rep, STAFF_ID))
with app.app_context():
    outcome = imm.update_elsewhere_dose(parent_row, "card", (birth_r + timedelta(days=45)).isoformat(), None)
check("a parent's report cannot be changed into a card record that would be a second valid record",
      outcome == "duplicate" and rows_of(rep, "PENTA:1")[-1]["evidence"] == "parent_report")
check("only one parent's report per dose can exist (the table holds it)",
      _raises(lambda: run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, "
                              "administered_by) VALUES (?, 'PENTA', 1, 'parent_report', ?)", (rep, STAFF_ID))))
card_repeat, birth_cr = child("YB", 100)
put_dose(card_repeat, "PENTA:1", birth_cr + timedelta(days=30), "card")
r = card(card_repeat, "PENTA:1", birth_cr + timedelta(days=62))
check("a repeat given elsewhere (a card, at least 4 weeks after the early one) is recorded and counts",
      item(card_repeat, "PENTA:1")["given"] and len(rows_of(card_repeat, "PENTA:1")) == 2
      and item(card_repeat, "PENTA:1")["history"][0]["kind"] == "too_early")

# ---------------------------------------------------------------------------
section("7. TASK 14: A CORRECTION IS CHECKED FOR SENSE, THEN JUDGED LIKE ANY OTHER DOSE")
corr, birth_x = child("ZA", 200)
put_dose(corr, "PENTA:1", birth_x + timedelta(days=60))
rid = rows_of(corr, "PENTA:1")[0]["id"]
def corrections():
    return q1("SELECT COUNT(*) FROM audit_logs WHERE action = ?", (ACTION_IMMUNIZATION_CORRECTED,))[0]


audit_before = corrections()
response = correct(corr, rid, "PENTA:1", TODAY + timedelta(days=1))
check("a correction to a future date is refused and nothing changes",
      "cannot be in the future" in flat(body(response)) and rows_of(corr, "PENTA:1")[0]["date_administered"]
      == (birth_x + timedelta(days=60)).isoformat())
response = correct(corr, rid, "PENTA:1", birth_x - timedelta(days=1))
check("a correction to a date before the child was born is refused and nothing changes",
      "before" in flat(body(response)) and "was born" in flat(body(response))
      and rows_of(corr, "PENTA:1")[0]["date_administered"] == (birth_x + timedelta(days=60)).isoformat())
with app.app_context():
    check("... the model refuses both by itself", (
        imm.correct_immunization(rid, "PENTA", 1, TODAY + timedelta(days=1)),
        imm.correct_immunization(rid, "PENTA", 1, birth_x - timedelta(days=1))) == ("bad_date", "bad_date"))
check("... and neither refusal wrote an audit entry", corrections() == audit_before)
response = correct(corr, rid, "PENTA:1", birth_x + timedelta(days=37))
check("a correction to a too-early date is saved, and the dose is then invalid: the message, not counted",
      item(corr, "PENTA:1")["too_early"] and not item(corr, "PENTA:1")["given"]
      and item(corr, "PENTA:1")["status"] == MSG
      and "does not count" in flat(body(response)), flat(body(response))[:300])
check("... the correction kept its audit entry (one)", corrections() == audit_before + 1)
check("... and the Correct button is still on the invalid dose's row",
      'data-record-id="%d"' % rid in body(staff.get(PROFILE.format(corr))))
correct(corr, rid, "PENTA:1", birth_x + timedelta(days=50))
check("a later correction to a valid date makes the dose count again",
      item(corr, "PENTA:1")["given"] and not item(corr, "PENTA:1")["too_early"])
dup_kid, birth_d = child("ZB", 300)
put_dose(dup_kid, "PENTA:1", birth_d + timedelta(days=60))
put_dose(dup_kid, "PENTA:2", birth_d + timedelta(days=100))
second = rows_of(dup_kid, "PENTA:2")[0]["id"]
with app.app_context():
    outcome = imm.correct_immunization(second, "PENTA", 1, birth_d + timedelta(days=100))
check("a correction onto a dose that already has a valid record is refused as a duplicate",
      outcome == "duplicate" and len(rows_of(dup_kid, "PENTA:2")) == 1)
card_corr, birth_cc = child("ZC", 200)
put_dose(card_corr, "PENTA:1", birth_cc + timedelta(days=60), "card")
cid = rows_of(card_corr, "PENTA:1")[0]["id"]
correct(card_corr, cid, "PENTA:1", birth_cc + timedelta(days=36))
check("a correction of a card dose's date is judged the same way (6 days early: invalid)",
      item(card_corr, "PENTA:1")["too_early"] and not item(card_corr, "PENTA:1")["given"])

# ---------------------------------------------------------------------------
section("8. TASK 14: THE NEXT DOSE IS JUDGED FROM THE REPEAT, NOT FROM THE INVALID DOSE")
ch, birth_h = child("QA", 150)
x_day, y_day = birth_h + timedelta(days=30), TODAY - timedelta(days=10)
put_dose(ch, "PENTA:1", x_day)
put_dose(ch, "PENTA:1", y_day)
check("the repeat counts; dose 2 is eligible only 4 weeks after the REPEAT (not after the invalid dose)",
      item(ch, "PENTA:1")["given"] and item(ch, "PENTA:2")["earliest_date"] == y_day + timedelta(weeks=4)
      and y_day + timedelta(weeks=4) > x_day + timedelta(weeks=4) and not item(ch, "PENTA:2")["eligible"])
response, visit = give(staff, ch, ["PENTA:2"])
check("... and a POST for it before then is refused with that date",
      f"Earliest date: {display_date(y_day + timedelta(weeks=4))}" in flat(body(response))
      and not rows_of(ch, "PENTA:2"))
finish(visit)
put_dose(ch, "PENTA:2", y_day + timedelta(days=10), "card")
check("a card dose 2 dated after the invalid dose + 4 weeks, but before the repeat + 4 weeks, is invalid",
      item(ch, "PENTA:2")["too_early"] and not item(ch, "PENTA:2")["given"])
ch2, birth_h2 = child("QB", 150)
put_dose(ch2, "PENTA:1", birth_h2 + timedelta(days=30))
put_dose(ch2, "PENTA:1", TODAY - timedelta(days=40))
put_dose(ch2, "PENTA:2", TODAY - timedelta(days=40) + timedelta(weeks=4) - timedelta(days=3), "card")
check("a card dose 2 within 3 days of the repeat + 4 weeks counts", item(ch2, "PENTA:2")["given"])
ch3, birth_h3 = child("QC", 150)
put_dose(ch3, "PENTA:1", birth_h3 + timedelta(days=30))
put_dose(ch3, "PENTA:2", birth_h3 + timedelta(days=75), "card")
check("a dose 2 on file while dose 1 has only an invalid record does not count (it was not spaced from a valid dose)",
      item(ch3, "PENTA:1")["too_early"] and item(ch3, "PENTA:2")["too_early"])

ch4, birth_h4 = child("QD", 150)
put_dose(ch4, "PENTA:1", birth_h4 + timedelta(days=30))
put_dose(ch4, "PENTA:1", birth_h4 + timedelta(days=45))
check("a repeat given less than 4 weeks after the invalid dose is itself invalid, though the child is old enough",
      item(ch4, "PENTA:1")["too_early"] and not item(ch4, "PENTA:1")["given"]
      and len(rows_of(ch4, "PENTA:1")) == 2)
put_dose(ch4, "PENTA:1", birth_h4 + timedelta(days=73))
check("... and a repeat 4 weeks after the LAST invalid dose counts, with both earlier doses in the history",
      item(ch4, "PENTA:1")["given"] and [h["kind"] for h in item(ch4, "PENTA:1")["history"]] == ["too_early"] * 2)

# ---------------------------------------------------------------------------
section("9. TASK 14: THE MIGRATION KEEPS EVERY RECORD, AND RECORD 302'S KIND IS JUDGED BY THE RULE")
from migrations import migrate_immunization_repeats as mig  # noqa: E402

kid302, birth302 = child("RA", 30)
MIG_DB = _support.guard_path(str(_support.TEST_DIR) + "/migrating.db")
shutil.copy2(TEST_DB, MIG_DB)
c = sqlite3.connect(MIG_DB)
c.row_factory = sqlite3.Row
kept, seen_keys = [], set()
for r in c.execute("SELECT * FROM immunizations ORDER BY id"):
    key = (r["patient_id"], r["vaccine_code"], r["dose_number"])
    if key not in seen_keys:
        seen_keys.add(key)
        kept.append(dict(r))
c.executescript("DROP TABLE immunizations;")
c.executescript("""
CREATE TABLE immunizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, consultation_id INTEGER,
    vaccine_code TEXT NOT NULL, dose_number INTEGER NOT NULL,
    evidence TEXT NOT NULL DEFAULT 'given_here' CHECK (evidence IN ('given_here', 'card', 'parent_report')),
    date_administered TEXT, place_given TEXT, administered_by INTEGER NOT NULL, notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (evidence <> 'given_here' OR date_administered IS NOT NULL),
    UNIQUE (patient_id, vaccine_code, dose_number),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT);
CREATE INDEX idx_immunizations_patient ON immunizations(patient_id, date_administered);
CREATE INDEX idx_immunizations_consultation ON immunizations(consultation_id);
""")
cols = ("id", "patient_id", "consultation_id", "vaccine_code", "dose_number", "evidence",
        "date_administered", "place_given", "administered_by", "notes", "created_at")
for r in kept:
    c.execute(f"INSERT INTO immunizations ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
              [r[k] for k in cols])
old302 = c.execute(
    "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
    "administered_by) VALUES (?, 'PENTA', 1, 'given_here', ?, ?)",
    (kid302, TODAY.isoformat(), STAFF_ID)).lastrowid
c.commit()
c.close()
conn = sqlite3.connect(MIG_DB)
conn.row_factory = sqlite3.Row
check("the old table refuses a second record of one dose, and the migration sees that it needs to run",
      mig.needs_work(conn) and _raises(lambda: conn.execute(
          "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
          "administered_by) VALUES (?, 'PENTA', 1, 'given_here', '2026-01-01', ?)", (kid302, STAFF_ID))))
before_rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
audit_n = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
conn.close()
BACKUPS = _support.guard_path(str(_support.TEST_DIR) + "/migration-backups")
result = mig.run(MIG_DB, BACKUPS)
conn = sqlite3.connect(MIG_DB)
conn.row_factory = sqlite3.Row
after_rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
check("the migration keeps every record, with every value unchanged",
      after_rows == before_rows and result["rows"] == len(before_rows) and not result["problems"])
check("... it saved a copy first, and the copy holds the old rows",
      result["backup"] and os.path.exists(result["backup"])
      and sqlite3.connect(result["backup"]).execute("SELECT COUNT(*) FROM immunizations").fetchone()[0]
      == len(before_rows))
check("... it wrote one record of itself in the audit log",
      conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_n + 1)
check("... the table now takes two records of one dose and still refuses two parent's reports of one dose",
      not mig.needs_work(conn)
      and not _raises(lambda: conn.execute(
          "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
          "administered_by) VALUES (?, 'PENTA', 1, 'given_here', '2026-06-01', ?)", (kid302, STAFF_ID)))
      and _raises(lambda: [conn.execute(
          "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, administered_by) "
          "VALUES (?, 'OPV', 2, 'parent_report', ?)", (kid302, STAFF_ID)) for _ in (0, 1)]))
conn.rollback()
conn.close()
second_run = mig.run(MIG_DB, BACKUPS)
conn = sqlite3.connect(MIG_DB)
check("running it a second time does nothing: no copy, no change, no second audit entry",
      second_run["backup"] is None and conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == audit_n + 1
      and conn.execute("SELECT COUNT(*) FROM immunizations").fetchone()[0] == len(before_rows))
conn.close()
verdict_rows = sqlite3.connect(MIG_DB)
verdict_rows.row_factory = sqlite3.Row
rows302 = [dict(r) for r in verdict_rows.execute(
    "SELECT id, vaccine_code, dose_number, evidence, date_administered FROM immunizations WHERE patient_id = ?",
    (kid302,))]
verdicts = imm.judge_records(birth302, rows302)
check("a dose given here before its minimum age (the kind record 302 is: Pentavalent dose 1 at 30 days old) is "
      "judged invalid by the rule",
      verdicts[[r["id"] for r in rows302].index(old302)] == imm.VERDICT_EARLY, verdicts)
verdict_rows.close()


# ---------------------------------------------------------------------------
# TASK 15: DUE DATES THAT CAN BE GIVEN, THE BUTTON ONLY WHEN THE CHILD IS OLD ENOUGH, SHORT TEXT
# Found in real use: a baby born Sep 3, 2026, 30 days old on Oct 3, 2026, with an early Pentavalent dose 1
# recorded on Oct 3 (so it does not count), and a parent's word for BCG and Hepatitis B.
# ---------------------------------------------------------------------------
from datetime import date  # noqa: E402

section("10. TASK 15: THE 30-DAY-OLD INFANT (BORN SEP 3, 2026), SEEN ON OCT 3, 2026")
SCENE_DAY = date(2026, 10, 3)


def row_text(page, label):
    """The flat text of the profile table row whose first cell is `label`."""
    for match in re.finditer(r"<tr>(.*?)</tr>", page, re.S):
        if re.search(r">\s*%s\s*</td>" % re.escape(label), match.group(1)):
            return flat(match.group(0))
    return ""


def has_record_button(page, key):
    return re.search(r'data-mode="record"[^>]*data-dose-key="%s"' % re.escape(key), page) is not None


with _support.frozen_today(SCENE_DAY):
    scene_birth = date(2026, 9, 3)
    scene = child_born("TA", scene_birth)
    put_dose(scene, "PENTA:1", SCENE_DAY)
    for parent_key in ("BCG", "HEPB"):
        run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, administered_by) "
                "VALUES (?, ?, 1, 'parent_report', ?)", (scene, parent_key, STAFF_ID))
    st = {i["key"]: i for i in status(scene)["schedule"]}
    check("the early Pentavalent dose 1 needs a repeat, and its due date is Oct 31 (the early dose + 4 weeks), "
          "not Oct 15", st["PENTA:1"]["too_early"] and st["PENTA:1"]["due_date"] == date(2026, 10, 31),
          st["PENTA:1"]["due_date"])
    check("OPV and PCV dose 1 are due Oct 15 (their minimum age)",
          st["OPV:1"]["due_date"] == date(2026, 10, 15) and st["PCV:1"]["due_date"] == date(2026, 10, 15))
    check("Pentavalent dose 2 is due Nov 28: 4 weeks after the repeat can first be given",
          st["PENTA:2"]["due_date"] == date(2026, 11, 28), st["PENTA:2"]["due_date"])
    check("Pentavalent dose 3, whose previous dose (dose 2) has no record, reads 'After Pentavalent dose 2'",
          st["PENTA:3"]["due_date"] is None and st["PENTA:3"]["due_text"] == "After Pentavalent dose 2")
    check("a dose whose previous dose has no record shows 'After <previous dose>' and no date",
          st["OPV:2"]["due_date"] is None and st["OPV:2"]["due_text"] == "After OPV dose 1")
    check("IPV is due at 14 weeks (Dec 10) and MR at 9 months (Jun 3, 2027)",
          st["IPV:1"]["due_date"] == date(2026, 12, 10) and st["MR:1"]["due_date"] == date(2027, 6, 3))
    page = body(client_as(STAFF_ID).get(PROFILE.format(scene)))
    check("the profile's Due column shows those dates, and the recommended age column is as it was",
          "Oct 31, 2026" in row_text(page, "Pentavalent dose 1") and "6 weeks" in row_text(page, "Pentavalent dose 1")
          and "Nov 28, 2026" in row_text(page, "Pentavalent dose 2") and "10 weeks" in row_text(page, "Pentavalent dose 2")
          and "Oct 15, 2026" in row_text(page, "OPV dose 1") and "After OPV dose 1" in row_text(page, "OPV dose 2"),
          [row_text(page, "Pentavalent dose 1"), row_text(page, "OPV dose 2")])
    allowed = {"BCG:1", "HEPB:1", "PENTA:1"}   # parent reports, and the dose that needs a repeat
    shown = {k for k in st if has_record_button(page, k)}
    check("'Record dose given elsewhere' shows only on the parent-report rows and the repeat: none on a dose whose "
          "minimum age is after Oct 7", shown == allowed, sorted(shown ^ allowed))
    before = n_doses(scene)
    refused = []
    for key in ("PENTA:2", "PENTA:3", "OPV:1", "PCV:1", "OPV:2", "IPV:1", "MR:1", "MMR:1"):
        for proof in ("card", "parent_report"):
            r = client_as(STAFF_ID).post(URL.format(scene), data={
                "dose_key": key, "evidence": proof, "date_given": "2026-10-01" if proof == "card" else "",
                "place_given": ""}, follow_redirects=True)
            refused.append("not old enough" in flat(body(r)))
    check("a POST to record any of those doses as given elsewhere is refused, with a valid token, one plain message",
          all(refused) and n_doses(scene) == before, refused)
    r = client_as(STAFF_ID).post(URL.format(scene), data={
        "dose_key": "BCG:1", "evidence": "card", "date_given": "2026-09-04", "place_given": ""})
    check("a parent's report can still be upgraded to a card (BCG)", item(scene, "BCG:1")["given"])
    visit = run_sql(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, status, "
        "is_walkin, checked_in_at) VALUES (?, ?, 'Consultation', ?, 'In Consultation', 1, ?)",
        (scene, STAFF_ID, SCENE_DAY.isoformat(), "2026-10-03 08:00:00"))
    form = body(client_as(STAFF_ID).get(f"/staff/consultation/record/{visit}"))
    ftext = flat(form)
    check("the consultation form has no tick box for Pentavalent, OPV or PCV dose 1 (D5: no form defect)",
          not any(tick_markup(form, k) for k in ("PENTA:1", "OPV:1", "PCV:1")))
    check("... it greys OPV and PCV dose 1 with 'From Oct 15, 2026' and the Pentavalent repeat with "
          "'From Oct 31, 2026'", ftext.count("From Oct 15, 2026") >= 2 and "From Oct 31, 2026" in ftext,
          [m for m in re.findall(r"From [A-Z][a-z]{2} \d+, \d{4}", ftext)])
    check("... and no 'given elsewhere' box is offered for a dose the child is too young for",
          not re.search(r'name="immunizations_elsewhere"\s+value="(OPV:1|PCV:1|PENTA:2|IPV:1)"', form))
    run_sql("UPDATE appointments SET status = 'Completed' WHERE id = ?", (visit,))
    client_as(STAFF_ID)  # (a new session each time keeps the checks apart)
    # the alert
    run_sql("UPDATE immunizations SET evidence = 'parent_report', date_administered = NULL "
            "WHERE patient_id = ? AND vaccine_code = 'BCG'", (scene,))
    text = flat(body(client_as(STAFF_ID).get(PROFILE.format(scene))))
    check("the alert is a title and one short line, ending with the card request",
          "3 doses to follow up" in text and "Pentavalent dose 1 (repeat from Oct 31, 2026); BCG and Hepatitis B "
          "(parent says given, no card). Ask for the vaccination card." in text, text[text.find("to follow up") - 40:][:300])
    check("... with no 'not in today's queue', no 'next visit' and no 'recorded during a consultation' text",
          not any(t in text for t in ("not in today's queue", "At next visit", "give it at the next visit",
                                      "next consultation", "is recorded during a consultation",
                                      "If the card shows the dose")))
    check("the baby's age reads '4 weeks 2 days' on the profile", "4 weeks 2 days / Female" in text)

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

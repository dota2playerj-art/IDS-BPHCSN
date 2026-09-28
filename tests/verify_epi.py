"""Can Health Center Staff still record an EPI dose and the growth measurements?

The paediatric half of the consultation form is the part the restriction was most
likely to have broken by accident: it renders inside the same Assessment & Plan
save, its growth fields are validated by the same function whose required-field
set now changes per role, and its doses are written after the record is created
-- which is also where the new seal and refusal logging were inserted.

A child, not an adult, so height, head circumference and the EPI schedule are all
in scope. Everything created is removed at the end.

Runs on a fresh test database built by tests/_support.py.
"""
import sqlite3
import sys

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import config  # noqa: E402
from app import app  # noqa: E402

_support.attach(app)

STAFF_ID, STAFF_ROLE = 2, "Health Center Staff"

results = []
created = {"appointments": [], "consultations": [], "immunizations": []}


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def cleanup():
    conn = db()
    for row_id in created["immunizations"]:
        conn.execute("DELETE FROM immunizations WHERE id = ?", (row_id,))
    for row_id in created["consultations"]:
        conn.execute("DELETE FROM consultations WHERE id = ?", (row_id,))
    for row_id in created["appointments"]:
        conn.execute("DELETE FROM appointments WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


def main():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = STAFF_ID
        _support.open_session(sess)
        sess["role"] = STAFF_ROLE

    conn = db()
    # An infant, so BOTH growth fields are in scope rather than only height.
    patient = conn.execute(
        """
        SELECT id, patient_id, first_name, birth_date FROM patients
         WHERE status = 'Active' AND birth_date >= date('now', '-1 year')
         ORDER BY birth_date DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if patient is None:
        print("no infant on the register -- cannot run this check")
        return 2
    patient = dict(patient)
    print(f"\nInfant {patient['patient_id']} ({patient['first_name']}, "
          f"born {patient['birth_date']})\n")

    conn = db()
    cur = conn.execute(
        """
        INSERT INTO appointments (patient_id, appointment_date, appointment_time,
                                  appointment_type, status, scheduled_by)
        VALUES (?, date('now'), '11:00', 'Immunization', 'In Consultation', ?)
        """,
        (patient["id"], STAFF_ID),
    )
    conn.commit()
    appt = cur.lastrowid
    conn.close()
    created["appointments"].append(appt)

    page = client.get(f"/staff/consultation/record/{appt}")
    body = page.get_data(as_text=True)
    check("staff paediatric form renders", page.status_code == 200,
          f"status {page.status_code}")
    check("the EPI section is offered", 'name="immunizations"' in body)
    check("height is offered for a child", 'name="height"' in body)
    check("head circumference is offered for an infant",
          'name="head_circumference"' in body)
    check("diagnosis is still absent on the paediatric form",
          'name="diagnosis"' not in body)

    # Whichever scheduled dose is genuinely outstanding, taken off the rendered
    # page rather than guessed, so this cannot ask for one already on file.
    import re
    # The name and the value sit on separate lines in the template, so the
    # pattern has to span whitespace -- an adjacent-only match found zero on a
    # page that offers eleven.
    offered = re.findall(r'name="immunizations"\s+value="([^"]+)"', body)
    check("the form offers at least one dose to tick", bool(offered),
          f"{len(offered)} offered")
    dose = offered[0] if offered else None

    data = {
        "chief_complaint": "Well-baby visit and scheduled immunisation",
        "temperature": "36.9",
        "weight": "6.4",
        "height": "62",
        "head_circumference": "41",
    }
    if dose:
        data["immunizations"] = dose

    resp = client.post(f"/staff/consultation/record/{appt}", data=data,
                       follow_redirects=False)
    check("staff paediatric save accepted", resp.status_code == 302,
          f"status {resp.status_code}")

    conn = db()
    row = conn.execute(
        "SELECT * FROM consultations WHERE appointment_id = ?", (appt,)
    ).fetchone()
    conn.close()
    check("the consultation was written", row is not None)
    if row is None:
        return 1
    created["consultations"].append(row["id"])

    check("weight saved", float(row["weight"]) == 6.4)
    check("height saved -- the growth rule is unaffected", float(row["height"]) == 62)
    check("head circumference saved", float(row["head_circumference"]) == 41)
    check("diagnosis is NULL rather than a refused save", row["diagnosis"] is None)

    if dose:
        conn = db()
        shots = conn.execute(
            "SELECT * FROM immunizations WHERE consultation_id = ?", (row["id"],)
        ).fetchall()
        conn.close()
        created["immunizations"].extend(r["id"] for r in shots)
        check("the EPI dose was recorded", len(shots) == 1, f"{len(shots)} rows")
        if shots:
            code, number = dose.split(":")
            check("it is the dose that was ticked",
                  shots[0]["vaccine_code"] == code
                  and str(shots[0]["dose_number"]) == number,
                  f"{shots[0]['vaccine_code']}:{shots[0]['dose_number']}")
            check("it is dated to the visit, not to a default",
                  str(shots[0]["date_administered"])[:10]
                  == str(row["consultation_date"])[:10])

    print("\n" + "=" * 72)
    failures = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failures)}/{len(results)} checks passed")
    for name in failures:
        print("  FAILED:", name)
    return 1 if failures else 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        cleanup()
        print("\n(fixtures removed)")
    sys.exit(code)

"""Do Health Center Staff still have every capability they had before?

The restriction was supposed to remove exactly two things from this role and
nothing else. This exercises the ones most likely to have been broken by it,
through real POSTs, and asserts on what actually landed in the database:

  * recording a consultation at all -- the form now saves with two required
    fields absent, so the validator had to stop requiring them;
  * dispensing medicine, which moves stock;
  * recording an EPI immunisation and a general vaccination;
  * editing a consultation afterwards;
  * correcting a vaccination, which is a separate audited path this role keeps.

Everything it creates is removed at the end, including the stock it moved.

Runs on a fresh test database built by tests/_support.py.
"""
import sqlite3
import sys

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import config  # noqa: E402
from app import app  # noqa: E402
from models.consultations import RESTRICTED_PLACEHOLDER  # noqa: E402

_support.attach(app)

STAFF_ID, STAFF_ROLE = 2, "Health Center Staff"

results = []
created = {"appointments": [], "consultations": [], "dispensing": [],
           "immunizations": [], "general": []}
stock_restore = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def db():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def client_as(user_id, role):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
        sess["role"] = role
    return c


def cleanup():
    conn = db()
    for table, key in (("medicine_dispensing", "dispensing"),
                       ("immunizations", "immunizations"),
                       ("general_vaccinations", "general"),
                       ("consultations", "consultations"),
                       ("appointments", "appointments")):
        for row_id in created[key]:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    for item_id, quantity in stock_restore:
        conn.execute(
            "UPDATE inventory_items SET stock_quantity = ? WHERE id = ?",
            (quantity, item_id),
        )
    conn.commit()
    conn.close()


def make_queue_entry(patient_id):
    conn = db()
    cur = conn.execute(
        """
        INSERT INTO appointments (patient_id, appointment_date, appointment_time,
                                  appointment_type, status, scheduled_by)
        VALUES (?, date('now'), '10:00', 'Consultation', 'In Consultation', ?)
        """,
        (patient_id, STAFF_ID),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    created["appointments"].append(new_id)
    return new_id


def main():
    staff = client_as(STAFF_ID, STAFF_ROLE)
    conn = db()
    patient = dict(conn.execute(
        "SELECT id, patient_id, first_name FROM patients WHERE status = 'Active' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone())
    item = conn.execute(
        """
        SELECT id, name, unit, stock_quantity FROM inventory_items
         WHERE status = 'Active' AND stock_quantity >= 5
           AND (expiry_date IS NULL OR expiry_date >= date('now'))
         ORDER BY stock_quantity DESC LIMIT 1
        """
    ).fetchone()
    conn.close()

    print(f"\nPatient {patient['patient_id']} ({patient['first_name']}), "
          f"item {item['name']} at {item['stock_quantity']}\n")
    stock_before = item["stock_quantity"]
    stock_restore.append((item["id"], stock_before))

    appt = make_queue_entry(patient["id"])

    # -----------------------------------------------------------------
    print("STAFF RECORDS A CONSULTATION WITH INTAKE, A VACCINE AND A DISPENSING")
    # -----------------------------------------------------------------
    resp = staff.post(
        f"/staff/consultation/record/{appt}",
        data={
            "chief_complaint": "Fever and body aches since yesterday",
            "temperature": "38.1",
            "blood_pressure": "118/76",
            "pulse_rate": "88",
            "respiratory_rate": "20",
            "weight": "54.5",
            "remarks": "Advised rest and fluids; to return if fever persists.",
            # An "other" vaccination, which this role records.
            "general_vaccinations": "other",
            "general_vaccine_other": "Tetanus toxoid",
            "general_dose_other": "1",
            # And a dispensing, which moves stock.
            "dispense_item_0": str(item["id"]),
            "dispense_qty_0": "2",
        },
        follow_redirects=False,
    )
    check("staff consultation POST redirected to the profile (it saved)",
          resp.status_code == 302, f"status {resp.status_code}")

    conn = db()
    row = conn.execute(
        "SELECT * FROM consultations WHERE appointment_id = ?", (appt,)
    ).fetchone()
    conn.close()
    check("the consultation was written", row is not None)
    if row is None:
        return 1
    cid = row["id"]
    created["consultations"].append(cid)

    check("chief complaint saved",
          row["chief_complaint"] == "Fever and body aches since yesterday")
    check("temperature saved", float(row["temperature"]) == 38.1)
    check("blood pressure saved and normalised", row["blood_pressure"] == "118/76")
    check("pulse rate saved", row["pulse_rate"] == 88)
    check("respiratory rate saved", row["respiratory_rate"] == 20)
    check("weight saved", float(row["weight"]) == 54.5)
    check("remarks saved -- staff still writes this field",
          "Advised rest" in (row["remarks"] or ""))
    check("diagnosis is NULL, not a validation failure", row["diagnosis"] is None)
    check("treatment plan is NULL", row["treatment_plan"] is None)
    check("the record is not sealed", not row["is_restricted"])

    conn = db()
    vac = conn.execute(
        "SELECT * FROM general_vaccinations WHERE consultation_id = ?", (cid,)
    ).fetchall()
    disp = conn.execute(
        "SELECT * FROM medicine_dispensing WHERE consultation_id = ?", (cid,)
    ).fetchall()
    after_stock = conn.execute(
        "SELECT stock_quantity FROM inventory_items WHERE id = ?", (item["id"],)
    ).fetchone()[0]
    queue_status = conn.execute(
        "SELECT status FROM appointments WHERE id = ?", (appt,)
    ).fetchone()[0]
    conn.close()

    created["general"].extend(r["id"] for r in vac)
    created["dispensing"].extend(r["id"] for r in disp)

    check("the vaccination was recorded", len(vac) == 1,
          f"{len(vac)} rows")
    if vac:
        check("vaccination carries the name staff typed",
              vac[0]["vaccine_name"] == "Tetanus toxoid",
              repr(vac[0]["vaccine_name"]))
    check("the dispensing was recorded", len(disp) == 1, f"{len(disp)} rows")
    if disp:
        check("dispensing recorded the right quantity",
              disp[0]["quantity_dispensed"] == 2)
    check("stock came off the shelf",
          after_stock == stock_before - 2,
          f"{stock_before} -> {after_stock}")
    # Task 6b, D3: Staff take the intake, the Doctor has not diagnosed, and the visit is
    # a Walk-in Consultation, so it now waits for the Doctor instead of being Completed.
    check("the queue entry now waits for the Doctor (the intake is saved, no diagnosis)",
          queue_status == "Waiting for the Doctor", repr(queue_status))

    # -----------------------------------------------------------------
    print("\nSTAFF EDITS THAT CONSULTATION")
    # -----------------------------------------------------------------
    resp = staff.post(
        f"/staff/consultation/edit/{cid}",
        data={
            "chief_complaint": "Fever and body aches since yesterday",
            "temperature": "37.6",
            "blood_pressure": "118/76",
            "remarks": "Advised rest and fluids; to return if fever persists.",
        },
        follow_redirects=False,
    )
    conn = db()
    edited = conn.execute("SELECT * FROM consultations WHERE id = ?", (cid,)).fetchone()
    logged = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action = 'Updated consultation record' "
        "AND details LIKE ?", (f"%#{cid}%",)
    ).fetchone()[0]
    conn.close()
    check("staff edit saved", resp.status_code == 302, f"status {resp.status_code}")
    check("the corrected temperature is stored", float(edited["temperature"]) == 37.6)
    check("the edit was audit-logged as usual", logged >= 1, f"{logged} entries")

    # -----------------------------------------------------------------
    print("\nSTAFF CORRECTS THE VACCINATION IT JUST RECORDED")
    # -----------------------------------------------------------------
    if vac:
        conn = db()
        before_audit = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM audit_logs").fetchone()[0]
        conn.close()
        resp = staff.post(
            f"/staff/patient_profile/{patient['id']}/correct-vaccination",
            data={
                "record_kind": "general",
                "record_id": vac[0]["id"],
                "correct_vaccine_name": "Tetanus toxoid booster",
                "correct_dose_number": "2",
                "correct_date": vac[0]["date_administered"],
            },
            follow_redirects=False,
        )
        conn = db()
        corrected = conn.execute(
            "SELECT * FROM general_vaccinations WHERE id = ?", (vac[0]["id"],)
        ).fetchone()
        entries = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE id > ? AND action = "
            "'Corrected other vaccination record'", (before_audit,)
        ).fetchone()[0]
        conn.close()
        check("staff correction accepted", resp.status_code == 302,
              f"status {resp.status_code}")
        check("the vaccination name was corrected",
              corrected["vaccine_name"] == "Tetanus toxoid booster",
              repr(corrected["vaccine_name"]))
        check("the correction was audit-logged", entries >= 1, f"{entries} entries")

    # -----------------------------------------------------------------
    print("\nSTAFF'S OWN SCREENS STILL SHOW THIS VISIT")
    # -----------------------------------------------------------------
    body = staff.get(f"/staff/patient_profile/{patient['id']}").get_data(as_text=True)
    check("the visit appears in the profile",
          "Fever and body aches since yesterday" in body)
    check("the dispensing appears in the profile", item["name"] in body)
    # FIXED 2026-09-28 (L13): this compared against "Restricted — Administrator
    # access only", text the app stopped showing when the Doctor role arrived
    # (113d6b7), so it passed whatever the page said. It now uses the text the
    # app really shows on a sealed record.
    check("no restriction notice on an unsealed record",
          RESTRICTED_PLACEHOLDER not in body)

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
        print("\n(fixtures removed, stock restored)")
    sys.exit(code)

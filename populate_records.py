from datetime import timedelta

import config
from database.connection import get_db
from models.patients import generate_next_patient_id
from models.users import seed_demo_users
from utils.dates import now

DB_PATH = config.DATABASE
SCHEMA_PATH = config.SCHEMA


def ensure_schema(conn):
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if not any(row["name"] == "users" for row in tables):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            conn.executescript(handle.read())
        conn.commit()


def lookup_user_id(conn, username):
    """Resolve one of the three canonical accounts seeded by models.users.seed_demo_users()."""
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise RuntimeError(
            f"Expected account '{username}' is missing from the users table. "
            "app.seed_demo_users() is the single source of truth for logins; "
            "start app.py once against a fresh app.db to create it."
        )
    return row["id"]


# birth_date is the only source of Age (Screen 03 renders an Age column), so the dates are
# written out explicitly rather than generated: the roster deliberately spans children,
# working-age adults, and six residents aged 60+ so the senior-focused programs and the
# chronic-condition consultations below have plausible subjects. sex is paired with the
# name for the same reason — it used to alternate on the loop index, labelling Alicia male.
PATIENTS = [
    ("Alicia", "Santos", "1958-03-14", "Female"),
    ("Benedict", "Cruz", "1971-11-02", "Male"),
    ("Carla", "Dela Rosa", "1949-06-30", "Female"),
    ("Diego", "Fernandez", "1988-01-25", "Male"),
    ("Elena", "Gonzales", "1995-09-08", "Female"),
    ("Fabian", "Hernandez", "1953-12-19", "Male"),
    ("Grace", "Ilagan", "2001-04-11", "Female"),
    ("Hector", "Jimenez", "1966-07-23", "Male"),
    ("Isabel", "Lopez", "1979-02-17", "Female"),
    ("Julian", "Mendoza", "2014-10-05", "Male"),
    ("Katrina", "Natividad", "1992-05-29", "Female"),
    ("Lorenzo", "Ocampo", "1946-08-03", "Male"),
    ("Mina", "Pascual", "2019-03-22", "Female"),
    ("Nathan", "Quinones", "1984-12-09", "Male"),
    ("Olivia", "Reyes", "1961-10-16", "Female"),
]


def insert_patients(conn):
    for index, (first_name, last_name, birth_date, sex) in enumerate(PATIENTS, start=1):
        conn.execute(
            """
            INSERT OR IGNORE INTO patients
            (patient_id, first_name, middle_name, last_name, birth_date, sex, address, contact_number, emergency_contact_name, emergency_contact_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"PAT-{index:03d}",
                first_name,
                None,
                last_name,
                birth_date,
                sex,
                f"Block {index}, Barangay Poblacion",
                f"0917{(1000000 + index * 111):06d}",
                f"Emergency Contact {first_name}",
                f"0999{(2000000 + index * 111):06d}",
            ),
        )

    conn.commit()


# Two infants, so the months/days age formatting on Screens 03 and 04 has real
# data behind it and the later Consultation/Immunization work has a subject the
# EPI schedule actually applies to. Their ages are given as a number of days
# before today rather than as fixed birthdates: Age is derived from birth_date,
# so a literal date would quietly age them out of infancy and stop exercising
# the formatting within the year.
#
# (first_name, middle_name, last_name, days_old, sex)
INFANTS = [
    ("Liam", "Gabriel", "Villanueva", 128, "Male"),   # ~4 months
    ("Sofia", "Mae", "Delos Reyes", 21, "Female"),    # 3 weeks
]


def insert_infant_patients(conn):
    """Add the infant fixtures, leaving every existing patient untouched.

    Kept apart from insert_patients() for two reasons. That function takes each
    patient_id from the list index, which no longer tracks the table once records
    have been registered through Screen 05 -- PAT-016 upward are already taken,
    so an appended row would collide and be silently dropped by INSERT OR IGNORE.
    These take the next free identifier from generate_next_patient_id(), the same
    helper Register Patient uses, so they cannot collide with anything.

    And the guard is on the name rather than on INSERT OR IGNORE, because the
    birthdates move with today: re-running this script must top the table up, not
    mint a second Liam a day older than the first.
    """
    added = 0
    for first_name, middle_name, last_name, days_old, sex in INFANTS:
        existing = conn.execute(
            "SELECT 1 FROM patients WHERE first_name = ? AND last_name = ?",
            (first_name, last_name),
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """
            INSERT INTO patients
            (patient_id, first_name, middle_name, last_name, birth_date, sex, civil_status,
             address, municipality, province, emergency_contact_name,
             emergency_contact_relationship, emergency_contact_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_next_patient_id(),
                first_name,
                middle_name,
                last_name,
                (now() - timedelta(days=days_old)).strftime("%Y-%m-%d"),
                sex,
                "Minor",
                f"Purok 3, Barangay Poblacion",
                "San Francisco",
                "Surigao del Norte",
                f"Mother of {first_name} {last_name}",
                "Mother",
                f"09175{(500000 + days_old):06d}",
            ),
        )
        # Committed inside the loop: generate_next_patient_id() reads through its
        # own connection, so the first infant has to be on disk before the second
        # asks for an identifier or both would be handed the same one.
        conn.commit()
        added += 1

    return added


# Today's consultation queue for Screen 08. Written as offsets from "now" rather
# than as fixed timestamps for the same reason the infants' birthdates are: the
# queue only means anything on the day it is for, so literal times would leave the
# screen empty from tomorrow onward.
#
# The mix is deliberate. One patient is with the clinician, two are waiting behind
# them, and one is booked but has not arrived -- so the ordering rule (in
# consultation first, then waiting by arrival, then not-yet-arrived) has something
# to actually order, and "Start Consultation" has more than one candidate.
#
# (patient_index, appointment_type, status, minutes_before_now, booked_time, is_walkin, reason)
# patient_index is an index into PATIENTS above.
TODAY_QUEUE = [
    (4, "Prenatal Check-up", "In Consultation", 55, "08:30", 0,
     "Third trimester check-up, mild swelling in ankles"),
    (10, "Walk-in Consultation", "Waiting", 40, None, 1,
     "Fever and cough since Monday"),
    (1, "Hypertension Follow-up", "Waiting", 25, "09:15", 0,
     "BP monitoring, out of maintenance medicine"),
    (12, "Immunization", "Scheduled", None, "11:00", 0,
     "Pentavalent dose 2"),
]


def insert_todays_queue(conn, user_id):
    """Seed today's queue, leaving any real check-ins alone.

    Guarded on (patient, date) rather than INSERT OR IGNORE: the appointment date
    moves with today, so re-running must top today up rather than stack a second
    copy of the queue on the same patients. A patient checked in for real through
    Screen 08 is therefore never duplicated by a later seed run either.
    """
    patient_ids = [row["id"] for row in conn.execute("SELECT id FROM patients ORDER BY id").fetchall()]
    if not patient_ids:
        return 0

    day = now().strftime("%Y-%m-%d")
    added = 0
    for patient_index, appointment_type, status, minutes_ago, booked_time, is_walkin, reason in TODAY_QUEUE:
        patient_id = patient_ids[patient_index % len(patient_ids)]

        existing = conn.execute(
            "SELECT 1 FROM appointments WHERE patient_id = ? AND date(appointment_date) = ?",
            (patient_id, day),
        ).fetchone()
        if existing:
            continue

        checked_in_at = None
        if minutes_ago is not None:
            checked_in_at = (now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            """
            INSERT INTO appointments
                (patient_id, scheduled_by, appointment_type, appointment_date,
                 appointment_time, status, notes, is_walkin, checked_in_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                user_id,
                appointment_type,
                day,
                booked_time,
                status,
                reason,
                is_walkin,
                checked_in_at,
            ),
        )
        added += 1

    conn.commit()
    return added


def insert_consultations(conn, user_id):
    patient_ids = [row["id"] for row in conn.execute("SELECT id FROM patients ORDER BY id").fetchall()]
    if not patient_ids:
        return 0

    # The leading number is an index into PATIENTS: each complaint is attached to a resident
    # whose age makes it plausible (chronic conditions to the older residents, the viral
    # infection to the 7-year-old) rather than to whoever the loop counter landed on.
    consults = [
        (12, "Fever and cough", "Viral upper respiratory infection", "Rest, hydration, and monitor symptoms"),
        (13, "Chest pain", "Anxiety-related mild palpitations", "Reassurance and follow-up check"),
        (2, "Diabetes check-up", "Blood sugar under control", "Continue medication and diet plan"),
        (8, "Back pain", "Muscle strain", "Warm compress and physical therapy"),
        (11, "High blood pressure", "Elevated blood pressure", "Medication review and lifestyle counseling"),
    ]

    # Guarded on (patient, complaint) the same way insert_infant_patients() and
    # insert_todays_queue() are guarded, and for the same reason: consultation_date
    # is derived from today, so it cannot be part of the key, and without a guard
    # every run appended a second copy of all five -- which is how the table
    # reached ten rows of five distinct consultations.
    added = 0
    for index, (patient_index, chief_complaint, diagnosis, treatment_plan) in enumerate(consults):
        patient_id = patient_ids[patient_index % len(patient_ids)]

        existing = conn.execute(
            "SELECT 1 FROM consultations WHERE patient_id = ? AND chief_complaint = ?",
            (patient_id, chief_complaint),
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """
            INSERT INTO consultations
            (patient_id, recorded_by, consultation_date, chief_complaint, diagnosis, treatment_plan, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                user_id,
                # Clinic-local, so seeded consultation dates line up with the
                # "today" every screen reads from utils.dates.
                (now() - timedelta(days=index)).strftime("%Y-%m-%d"),
                chief_complaint,
                diagnosis,
                treatment_plan,
                # No note, rather than a note saying where the row came from.
                # This column is printed on Patient Profile under "Additional
                # Notes", so the old string put this file's name in front of a
                # clinician reading a patient's history. NULL is what the other
                # remark-less consultations already hold, and
                # models/consultations.py renders it as "Not recorded" -- true,
                # and in the project's own wording. Inventing a neutral sentence
                # instead would be a note nobody wrote.
                # See migrate_clear_seeded_remarks.py, which cleared the five
                # rows this line had already written.
                None,
            ),
        )
        added += 1

    conn.commit()
    return added


# Stock levels are the point of this table, so they are written out explicitly
# rather than generated: five of the fifteen sit at or below their own reorder
# level (one of them at zero) so the low-stock half of Proposal Objective 2 has
# real data to display, and three carry expiry dates that have passed or fall
# inside the 90-day near-expiry window. Every threshold is per-item, because a
# health center reorders gauze and amoxicillin at very different levels.
#
# The medicine names are the ones already named in 06_DESIGN_CONTENT_LIBRARY.md
# §Medicines and in the Screen 06 mockup, so the seeded rows read as the same
# inventory those pages were drawn against.
#
# (name, generic_name, category, drug_class, strength, form, unit,
#  stock, threshold, expiry_date, date_received, batch_number, supplier)
INVENTORY_ITEMS = [
    ("Paracetamol", "Paracetamol", "Medicine", "Analgesic / Antipyretic", "500mg", "Tablet", "Tablet",
     820, 200, "2027-06-30", "2026-05-12", "PCM-2026-0512", "DOH Regional Warehouse - Caraga"),
    ("Amoxicillin", "Amoxicillin Trihydrate", "Medicine", "Antibiotic", "500mg", "Capsule", "Capsule",
     48, 100, "2026-09-30", "2026-03-17", "AMX-2026-0317", "DOH Regional Warehouse - Caraga"),
    ("Cotrimoxazole", "Sulfamethoxazole + Trimethoprim", "Medicine", "Antibiotic", "400/80mg", "Tablet", "Tablet",
     15, 60, "2026-09-18", "2026-02-08", "CTX-2026-0208", "Provincial Health Office - Surigao del Norte"),
    ("Ibuprofen", "Ibuprofen", "Medicine", "Analgesic / Antipyretic", "400mg", "Tablet", "Tablet",
     90, 90, "2027-02-28", "2026-04-21", "IBU-2026-0421", "Pharex Health Corp."),
    ("Amlodipine", "Amlodipine Besylate", "Medicine", "Antihypertensive", "5mg", "Tablet", "Tablet",
     340, 150, "2027-03-31", "2026-01-19", "AML-2026-0119", "DOH Regional Warehouse - Caraga"),
    ("Losartan", "Losartan Potassium", "Medicine", "Antihypertensive", "50mg", "Tablet", "Tablet",
     260, 100, "2027-05-31", "2026-01-19", "LOS-2026-0119", "DOH Regional Warehouse - Caraga"),
    ("Metformin", "Metformin Hydrochloride", "Medicine", "Antidiabetic", "500mg", "Tablet", "Tablet",
     210, 120, "2027-01-31", "2026-02-25", "MET-2026-0225", "Provincial Health Office - Surigao del Norte"),
    ("Ferrous Sulfate", "Ferrous Sulfate + Folic Acid", "Medicine", "Vitamins & Supplements", "300mg", "Tablet", "Tablet",
     155, 80, "2026-12-31", "2026-03-04", "FER-2026-0304", "DOH Regional Warehouse - Caraga"),
    ("Vitamin C", "Ascorbic Acid", "Medicine", "Vitamins & Supplements", "500mg", "Tablet", "Tablet",
     480, 150, "2027-08-31", "2026-06-02", "VTC-2026-0602", "Pharex Health Corp."),
    ("ORS Powder Sachet", "Oral Rehydration Salts", "Medicine", "Oral Rehydration", "20.5g", "Sachet", "Sachet",
     22, 60, "2026-10-25", "2026-04-30", "ORS-2026-0430", "UNICEF Donation - DOH Caraga"),
    ("Cetirizine", "Cetirizine Dihydrochloride", "Medicine", "Antihistamine", "10mg", "Tablet", "Tablet",
     140, 60, "2026-07-15", "2025-11-14", "CTZ-2025-1114", "Pharex Health Corp."),
    ("Salbutamol Nebule", "Salbutamol Sulfate", "Medicine", "Bronchodilator", "2.5mg/2.5mL", "Nebule", "Vial",
     75, 30, "2026-06-30", "2025-12-09", "SAL-2025-1209", "Provincial Health Office - Surigao del Norte"),
    ("Sterile Gauze Pad 4x4", None, "Supply", None, None, None, "Pack",
     0, 40, "2028-01-31", "2026-05-26", "GAU-2026-0526", "Barangay Poblacion LGU Procurement"),
    ("Disposable Face Mask", None, "Supply", None, None, None, "Box",
     600, 200, "2028-06-30", "2026-05-26", "MSK-2026-0526", "Barangay Poblacion LGU Procurement"),
    ("Digital Thermometer", None, "Equipment", None, None, None, "Piece",
     6, 2, None, "2025-09-15", None, "Barangay Poblacion LGU Procurement"),
]


def insert_inventory_items(conn):
    """Seed the medicine and supply inventory.

    INSERT OR IGNORE against the UNIQUE item_code, matching insert_patients():
    re-running the script tops the table up rather than duplicating it, and never
    overwrites a stock figure an operator has since edited through Screen 07.
    """
    for index, item in enumerate(INVENTORY_ITEMS, start=1):
        (name, generic_name, category, drug_class, strength, form, unit,
         stock, threshold, expiry_date, date_received, batch_number, supplier) = item

        conn.execute(
            """
            INSERT OR IGNORE INTO inventory_items
            (item_code, name, generic_name, category, drug_class, dosage_strength,
             dosage_form, unit, stock_quantity, low_stock_threshold, expiry_date,
             date_received, batch_number, supplier, storage_location, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"MED-{index:04d}",
                name,
                generic_name,
                category,
                drug_class,
                strength,
                form,
                unit,
                stock,
                threshold,
                expiry_date,
                date_received,
                batch_number,
                supplier,
                # Two cabinets and a supply room is the whole storage estate of a
                # barangay health center; medicines are split across the cabinets.
                "Supply Room, Rack 1" if category != "Medicine"
                else f"Cabinet {'AB'[index % 2]}, Shelf {index % 3 + 1}",
                "Active",
            ),
        )

    conn.commit()
    return len(INVENTORY_ITEMS)


# insert_announcements() used to sit here, seeding ten rows into schedule_logs.
# It was the only writer that table ever had and, unlike every other seeder in
# this file, it used a plain INSERT rather than INSERT OR IGNORE -- which is why
# five runs of this script had left fifty rows behind. Community Announcements
# has been retired and the table is dropped by migrate_drop_schedule_logs.py, so
# the seeder is gone with it.


def main():
    conn = get_db()
    ensure_schema(conn)
    # Logins are owned entirely by models.users.seed_demo_users(); this script only borrows the
    # existing staff/official rows to attribute its sample records to. It no longer mints
    # its own seed-staff / seed-official accounts (audit §6.5f).
    seed_demo_users()
    staff_user_id = lookup_user_id(conn, "staff")
    insert_patients(conn)
    infant_count = insert_infant_patients(conn)
    queue_count = insert_todays_queue(conn, staff_user_id)
    consultation_count = insert_consultations(conn, staff_user_id)
    inventory_count = insert_inventory_items(conn)
    conn.close()

    print(
        f"Inserted {infant_count} infant patients, {queue_count} queue entries for today, "
        f"{consultation_count} consultation records "
        f"and {inventory_count} inventory items into {DB_PATH}"
    )


if __name__ == "__main__":
    main()

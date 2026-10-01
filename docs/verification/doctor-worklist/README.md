# Task 6 — the Doctor's list and "Left before being seen"

Step 1: how a visit moves today, and what the code does that the task did not expect.

## Queue statuses (appointments.status)

`Scheduled`, `Confirmed` (booked ahead, retired 2026-09-05; old rows only), `Waiting`,
`In Consultation`, `Completed`, `Cancelled`, `No-show`. A CHECK in `schema.sql` lists them.

A visit now moves like this:

1. Staff **check in** the patient: a new row, `Waiting`, with the check-in time.
2. Staff **start** the consultation: `In Consultation`. Only one visit can be in
   consultation at a time (held in SQL, `start_consultation()`).
3. Staff **record** the intake (complaint, vitals, doses, dispensing). Saving the form
   writes the `consultations` row **and completes the queue entry** (`Completed`) in one
   step (`process_record_consultation()`).
4. The Doctor later **edits** that consultation and writes the diagnosis and treatment
   plan. Only the Doctor can (`can_diagnose()`).

## What the code does that the task did not expect

* **Intake completes the visit.** A visit that has intake but no diagnosis is already
  `Completed` in the queue. So "completed" cannot be the test for "not seen by the Doctor
  yet". The test used here is the one the task also names: **no diagnosis written**.
* **There is no service list.** Every visit's `appointment_type` is the one constant
  "Walk-in Consultation". The service is only the typed check-in reason, which can be
  sealed, so it cannot be classified. The retired booking list held `Consultation`,
  `Prenatal Check-up`, `Immunization`, `DM / Hypertension Monitoring`, `Dental` and
  `Follow-up Consultation`. The Service Schedule is empty on purpose.

## Services and the Doctor (D2)

`SERVICES_NEEDING_DOCTOR` in `models/doctor_worklist.py` names the `appointment_type`
values that need a diagnosis: Walk-in Consultation, Consultation, Follow-up Consultation,
DM / Hypertension Monitoring (a clinical review: blood pressure, blood sugar, medicine
changes). A visit with no type is treated as a consultation. Not on the list: Prenatal
Check-up, Immunization, Dental (midwife, health worker and dentist services). **Today
every new visit is a Walk-in Consultation, so in practice every visit without a
diagnosis is listed.** The constant starts to separate services only when a visit carries
another type. Logged for the team.

## Where "has a diagnosis" is decided

One place: `models/doctor_worklist.py`. A visit has a diagnosis when its consultation's
`diagnosis` is not blank. A sealed diagnosis is stored encrypted and is not blank, so a
sealed visit counts as diagnosed.

## Sealed visits

A sealed visit without a diagnosis cannot happen through the screens (the Doctor seals,
and sealing needs the Doctor's diagnosis). If one does appear, its row shows the patient's
name, ID, service and times only. The list reads no complaint, no reason and no sealed
field, for anyone.

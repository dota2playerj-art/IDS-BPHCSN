# Task 6b — service at check-in, and the status "Waiting for the Doctor"

Step 1: where the service is stored now, how a visit moves, and what the migration will convert. Counts only.

## Where the service is stored

`appointments.appointment_type` (TEXT, no CHECK). `check_in_patient()` wrote the constant
`WALK_IN_TYPE = "Walk-in Consultation"` for every new visit, so on this laptop's database
all 410 visits hold that one value. The check-in reason is typed text (`appointments.notes`)
and can be sealed, so it cannot be used to tell a service.

Services are already read in these places: the queue (`appointment_scheduling.html`,
`staff_dashboard.html`, the queue export), "Appointments by service" in Reports & Analytics
(`get_appointment_report()`, grouped on `appointment_type`), the Prenatal Check-up count
printed beside the prenatal note, and `models/doctor_worklist.py` (`SERVICES_NEEDING_DOCTOR`).

## The check-in form and route

Two paths, both in the Check In dialog on the Patient Queue:

* **Existing patient:** `POST /staff/appointment_scheduling/check-in`
  (`staff_check_in_patient` -> `process_check_in()` -> `check_in_patient()`).
* **New patient:** the dialog hands the reason over by POST to Register Patient
  (`staff_register_patient`), which keeps it in the session and carries it as a hidden
  field; saving the patient calls `process_new_patient_check_in()` -> `check_in_patient()`.

Both reach the one model function, so the service is checked there too.

## Every place that sets "Completed"

* `complete_consultation()` — the queue's "Mark Completed" button (no record written) and,
  until now, saving the intake (`process_record_consultation()`).
* `get_queue_stats()`, `get_appointment_day_summary()` and the report outcomes count it.

Saving the intake is the one that was wrong: it closed a visit the Doctor had not seen.

## The visit flow now

1. Staff **check in** the patient and choose the service (required, no default): `Waiting`.
2. Staff **start** the consultation: `In Consultation`.
3. Staff **save the intake**. If the service needs a diagnosis and none was written:
   `Waiting for the Doctor`. Otherwise `Completed` (immunization, prenatal, dental, or a visit
   the Doctor recorded himself with a diagnosis).
4. The Doctor **saves a diagnosis**: `Completed`.
5. Staff or the Doctor can mark a visit **Left before being seen** from `Waiting`,
   `In Consultation` or `Waiting for the Doctor`, and undo it the same day.
6. Staff or the Doctor can **correct the service** while the visit is not Completed or Left.

## VISIT_SERVICES (the final list)

Built from the services the code and reports already name (Prenatal Check-up and
Immunization in Reports & Analytics; Consultation, Follow-up Consultation, DM / Hypertension
Monitoring and Dental from the retired booking list):

| Service | Needs the Doctor |
|---|---|
| Consultation | yes |
| Follow-up Consultation | yes |
| Hypertension / Diabetes Monitoring | yes |
| Prenatal Check-up | no |
| Immunization | no |
| Dental | no |

"Walk-in Consultation" stays only as the name old rows carry; it needs the Doctor like a
Consultation and is not offered for a new visit. "DM / Hypertension Monitoring" was never
stored, so it is replaced by the plainer "Hypertension / Diabetes Monitoring".

## What the migration will convert on this laptop's app.db (counts only)

* 410 visits: all `Walk-in Consultation`, left as they are.
* 6 visits are Completed, have a consultation record and no diagnosis: they become
  `Waiting for the Doctor`.
* 0 Completed visits have no consultation record at all (they would stay Completed: the
  Doctor has nothing to open).
* 0 visits marked Left before being seen were Completed before (their undo target would be
  moved to `Waiting for the Doctor`).

## Two things to decide

* The service names a clinical fact (a prenatal visit). The Administrator's queue, queue
  export and dashboard now show no service, like the check-in reason. The correction's audit
  entry has the wording the task gave ("Changed the service of visit APT-00081 from
  Consultation to Immunization.") and names no patient, but the Administrator can read it.
* The queue's "Mark Completed" button closes a visit with nothing written, whatever its
  service. It still gives `Completed`. Only saving the intake sends a visit to the Doctor.

# Migrations

A migration changes an existing `app.db` to match a newer version of the code. Each one is run once, by hand,
from the project root: `python migrations/<name>.py [database]`. Each makes a backup first where it changes data,
checks its own work, and is safe to run twice (the second run does nothing).

**A new laptop does not need any of them.** Build the fictional demo database instead:

```
python archive_plain_databases.py
python seed_demo_data.py --replace
python archive_plain_databases.py --remove-previous
```

Run a migration only on a database that was built before the change it describes.

## In the order they were written

| Written | File | What it does |
|---|---|---|
| 2026-08-14 | `migrate_add_appointment_queue.py` | give appointments the two queue states and the check-in fields. |
| 2026-08-14 | `migrate_add_consultation_columns.py` | extend consultations with vitals, growth measures and follow-up. |
| 2026-08-14 | `migrate_add_immunizations.py` | add the immunizations table. |
| 2026-08-14 | `migrate_add_inventory_columns.py` | extend inventory_items with the fields Add/Edit Medicine collects. |
| 2026-08-14 | `migrate_add_patient_columns.py` | extend the patients table with the fields Register Patient collects. |
| 2026-08-14 | `migrate_add_sms_broadcasts.py` | add the sms_broadcasts and sms_broadcast_recipients tables. |
| 2026-08-14 | `migrate_drop_schedule_logs.py` | drop the schedule_logs table. |
| 2026-08-14 | `migrate_enforce_single_consultation.py` | reduce the queue to one consultation at a time. |
| 2026-08-27 | `migrate_add_general_vaccinations.py` | add the general_vaccinations table. |
| 2026-08-28 | `migrate_add_medicine_dispensing.py` | add the medicine_dispensing table. |
| 2026-08-29 | `migrate_close_stuck_consultation.py` | close the visit left In Consultation on 2026-08-28. |
| 2026-09-01 | `migrate_add_appointment_sms.py` | add the appointment_sms_messages table. |
| 2026-09-04 | `migrate_correct_admin_persona.py` | give the Administrator account a generic name. |
| 2026-09-05 | `migrate_add_consultation_restriction.py` | give a consultation somewhere to record that it is confidential. |
| 2026-09-06 | `migrate_add_immunization_source.py` | let an immunisation record say whether this health center gave it. |
| 2026-09-24 | `migrate_add_doctor_role.py` | add the Doctor role, and the demo account that holds it. |
| 2026-09-26 | `migrate_add_service_schedule.py` | add the service_schedule table, and put nothing in it. |
| 2026-09-28 | `migrate_add_must_change_password.py` | Add users.must_change_password, and mark accounts still on an old demo password. |
| 2026-10-01 | `migrate_redact_clinical_audit_text.py` | Remove diagnosis and treatment text from old audit entries, and encrypt sealed records. |
| 2026-10-01 | `migrate_seal_free_text_fields.py` | Seal all free text of restricted visits, and remove free clinical text from old audit entries. |
| 2026-10-01 | `migrate_admin_minimum_necessary.py` | Remove patient-linked clinical details from earlier audit entries. |
| 2026-10-02 | `migrate_mask_audit_phone_numbers.py` | Mask phone numbers in earlier audit entries. |
| 2026-10-02 | `migrate_add_left_before_seen.py` | add the "Left before being seen" queue status (Task 6, M5). |
| 2026-10-02 | `migrate_visit_service_and_doctor_status.py` | the queue status "Waiting for the Doctor" (Task 6b, M33 and L31). |
| 2026-10-02 | `migrate_remove_service_names_from_audit.py` | take visit service names out of earlier audit entries (Task 6c, L32). |
| 2026-10-03 | `migrate_immunization_evidence.py` | a dose says what its record rests on: given here, a card, or a parent's report (Task 9). |

Repair scripts that only served the old, archived demo data were deleted in Task 7.

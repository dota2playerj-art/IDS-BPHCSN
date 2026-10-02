PRAGMA foreign_keys = ON;

-- role: four values. 'Doctor' was added by migrate_add_doctor_role.py when the
-- RHU's field data separated system administration (the Administrator, a
-- barangay Kagawad) from clinical authority (the RHU physician). A database
-- built from this file already has it; an older one gets it from that script.
--
-- must_change_password: 1 means the person must set their own password before
-- they can use any other screen. It is set when an account is created, when an
-- Administrator resets its password, and when the first accounts are seeded. It
-- is cleared when the person changes their own password. Last in the table, as
-- migrate_add_must_change_password.py adds it to an existing database.
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Admin', 'Doctor', 'Health Center Staff', 'Barangay Official')),
    email TEXT,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    must_change_password INTEGER NOT NULL DEFAULT 0
);

-- medical_conditions and allergies hold a JSON array of strings, e.g.
-- '["Hypertension", "Diabetes"]'. JSON rather than comma-separated because the
-- Register Patient form pairs fixed checkbox chips with a free-text "other"
-- note, and that free text can itself contain commas.
--
-- status is a soft lifecycle flag: patient records are never hard-deleted. Only
-- Health Center Staff and Administrator may change it; Barangay Official never can.
CREATE TABLE patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    birth_date TEXT,
    sex TEXT,
    civil_status TEXT,
    blood_type TEXT,
    address TEXT,
    municipality TEXT,
    province TEXT,
    zip_code TEXT,
    contact_number TEXT,
    emergency_contact_name TEXT,
    emergency_contact_relationship TEXT,
    emergency_contact_number TEXT,
    emergency_contact_address TEXT,
    medical_conditions TEXT,
    allergies TEXT,
    status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive', 'Deceased')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per visit written up. The four clinical text fields are what the
-- health worker types; the vitals above them are what was measured on the way in.
--
-- Units are fixed by convention rather than stored: temperature is Celsius,
-- weight kilograms, height and head_circumference centimetres, pulse_rate beats
-- per minute, respiratory_rate breaths per minute. One health center, one set of
-- instruments -- a unit column would only allow two rows that cannot be compared.
--
-- blood_pressure is one TEXT reading ("120/80") rather than two numeric columns,
-- because half a blood pressure is not a measurement. Its shape and range are
-- validated in models/consultations.py before it is stored.
--
-- height is recorded for children under five and head_circumference for infants
-- under one (see PEDIATRIC_AGE_YEARS / INFANT_AGE_YEARS). That rule is about the
-- patient on the day of the visit, not about the column, so it lives in the model
-- rather than in a CHECK that would need rebuilding if the cohort ever changed.
--
-- appointment_id ties the record to the queue entry it documents, so a visit
-- cannot be written up twice. Nullable: a consultation can be recorded outside
-- the queue.
CREATE TABLE consultations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    recorded_by INTEGER NOT NULL,
    appointment_id INTEGER,
    consultation_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    chief_complaint TEXT,
    diagnosis TEXT,
    treatment_plan TEXT,
    remarks TEXT,
    temperature REAL,
    blood_pressure TEXT,
    pulse_rate INTEGER,
    respiratory_rate INTEGER,
    weight REAL,
    height REAL,
    head_circumference REAL,
    follow_up_date TEXT,
    -- THE CONFIDENTIALITY SEAL. Set by the Doctor -- the licensed clinician --
    -- on an entry they judge to be sensitive, and read by every screen that
    -- would otherwise show this record's diagnosis or treatment plan to anyone
    -- else, the Administrator included. (It was the Administrator's until the
    -- RHU's field data showed the Administrator is a barangay Kagawad, not the
    -- doctor; a seal set under that account stays set.) RA 11166 makes HIV status privileged medical information with
    -- criminal penalties for unauthorised disclosure, and it is not the only
    -- such rule; nothing here guesses which diagnoses are covered, because a
    -- system that guessed would be wrong in both directions. The clinician
    -- decides and this column holds the decision.
    --
    -- It seals every free-text field (diagnosis, treatment plan, chief complaint and
    -- remarks) and the check-in reason, stored
    -- encrypted. The visit date, vitals, doses and dispensing stay legible to
    -- Health Center Staff, who still take the intake and still hand the medicine
    -- over. See models/consultations.py SEALED_FIELDS.
    --
    -- restricted_by / restricted_at say who sealed it and when, so the profile
    -- can print that beside the placeholder without a per-row search of the audit
    -- trail. audit_logs remains the authority; these two are a convenience and
    -- are cleared whenever the restriction is lifted.
    is_restricted INTEGER NOT NULL DEFAULT 0 CHECK (is_restricted IN (0, 1)),
    restricted_by INTEGER,
    restricted_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Nullable, with no default, as in the migrated database
    -- (migrate_add_consultation_columns.py). create_consultation() inserts NULL
    -- and then sets it to created_at in the same transaction. Equal to created_at
    -- means "never edited". A NOT NULL here made every new consultation fail on
    -- a fresh install.
    updated_at TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT,
    -- No ON DELETE clause, as in the migrated database
    -- (migrate_add_consultation_restriction.py). Nothing deletes an account.
    FOREIGN KEY (restricted_by) REFERENCES users(id),
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
);

-- Two different classifications live here, and they are not interchangeable:
--
--   category    the item type, constrained to Medicine / Supply / Equipment.
--   drug_class  the therapeutic classification (Antibiotic, Antihypertensive,
--               ...) that Screen 06's table shows as a pill and Screen 07's
--               "Category" dropdown offers. Free text, because the vocabulary
--               is a presentation list that will grow.
--
-- stock_quantity is compared against this row's own low_stock_threshold rather
-- than a single system-wide number: a barangay health center reorders gauze and
-- amoxicillin at very different levels.
--
-- status is a soft lifecycle flag, as on patients: inventory rows are not
-- hard-deleted.
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    generic_name TEXT,
    brand_name TEXT,
    category TEXT NOT NULL CHECK (category IN ('Medicine', 'Supply', 'Equipment')),
    drug_class TEXT,
    dosage_strength TEXT,
    dosage_form TEXT,
    unit TEXT,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER NOT NULL DEFAULT 0,
    expiry_date TEXT,
    date_received TEXT,
    batch_number TEXT,
    manufacturer TEXT,
    supplier TEXT,
    unit_cost REAL,
    storage_location TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- schedule_logs used to be defined here. It was meant to hold both appointments
-- and community announcements. Neither half survived: appointments have their
-- own table below, and Community Announcements was retired in favour of SMS
-- broadcasts, which are a real record of what was sent. Nothing read the table,
-- nothing referenced it, and it is dropped from existing databases by
-- migrate_drop_schedule_logs.py. Do not re-add it without a feature behind it.

-- One table covers both a booked appointment and a walk-in, because a walk-in is
-- just an appointment created at the moment the patient arrives. That keeps the
-- consultation queue a single query instead of a union of two sources.
--
-- status carries the visit through its whole life, including the queue:
--
--   Scheduled / Confirmed   booked, patient not yet here
--   Waiting                 checked in, in the queue
--   In Consultation         with the clinician now
--   Completed / Cancelled / No-show
--   Left before being seen  checked in, then went home before the Doctor saw them
--                           (Task 6, M5). Set by Staff or the Doctor, and undone the
--                           same day. left_by, left_at and status_before_left record
--                           who, when and what the status was before.
--
-- is_walkin records whether there was a prior booking. Once a scheduled patient
-- is checked in their row is otherwise indistinguishable from a walk-in's, so the
-- distinction has to be stored at check-in or it is lost.
--
-- checked_in_at is arrival time, which created_at cannot stand in for: on a
-- pre-booked visit created_at is when it was booked, so ordering the queue by it
-- would put everyone who booked ahead of everyone who walked in, whatever the
-- actual order of arrival.
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    scheduled_by INTEGER NOT NULL,
    appointment_type TEXT,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT,
    assigned_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN ('Scheduled', 'Confirmed', 'Waiting', 'In Consultation', 'Waiting for the Doctor', 'Completed', 'Cancelled', 'No-show', 'Left before being seen')),
    notes TEXT,
    is_walkin INTEGER NOT NULL DEFAULT 0,
    checked_in_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    left_by INTEGER,
    left_at TEXT,
    status_before_left TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (scheduled_by) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (left_by) REFERENCES users(id) ON DELETE SET NULL
);

-- One row per dose a child has had. The schedule these are measured against is
-- NOT here: the DOH Expanded Program on Immunization infant schedule is national
-- policy, identical in every barangay and changed only by DOH circular, so it
-- lives as EPI_SCHEDULE in models/immunizations.py alongside the other
-- controlled vocabularies. See that module's header for the full reasoning.
--
-- vaccine_code is the stable identity ('PENTA'), not the display name: renaming
-- a vaccine on screen must not orphan the records already written against it.
--
-- `evidence` says what the record of this dose rests on (Task 9). The health center
-- cannot know what happened at another hospital, so a dose that was not given here
-- counts only when someone has seen it written down:
--
--   'given_here'     this health center gave it, during a consultation. Somebody
--                    here held the syringe, on date_administered, and
--                    administered_by names them. HL7 FHIR primarySource = true.
--   'card'           given elsewhere, and the vaccination card or record book was
--                    SEEN. Written, dated evidence. FHIR primarySource = false,
--                    reportOrigin = "record".
--   'parent_report'  the parent or guardian says it was given, and has no card.
--                    FHIR primarySource = false, reportOrigin = "recall". It does
--                    NOT count as given for completion or coverage, and it can be
--                    upgraded to 'card' when the card is shown, or removed.
--
-- The basis is the CDC General Best Practices: only written, dated records are
-- accepted as evidence of vaccination, and without one the child is treated as
-- unvaccinated. 'given_here' and 'card' count as given; 'parent_report' does not.
--
-- date_administered is nullable, and the CHECK below makes that one-sided: a dose
-- given here must say when. A 'card' dose must have a date when it is recorded
-- (models/immunizations.py enforces it), but rows migrated from the old "reported"
-- doses may have none. A 'parent_report' date is optional. place_given is optional
-- free text for a dose given elsewhere.
--
-- Only 'given_here' needs a consultation. Doses given elsewhere are recorded from
-- the Immunization Record tab with no consultation; consultation_id is nullable
-- for that, and because a deleted consultation sets it NULL.
--
-- UNIQUE (patient_id, vaccine_code, dose_number) is the clinically important
-- constraint. A child cannot receive the same dose twice, and a schema that
-- permits it will eventually hold it -- which would make a defaulting child look
-- up to date. It is also what lets a double-submitted form be absorbed by
-- INSERT OR IGNORE instead of duplicating a dose, and what stops a dose recorded
-- as given elsewhere being recorded a second time as given here.
--
-- consultation_id is SET NULL rather than CASCADE on purpose: the vaccination
-- happened whether or not its paperwork survives.
CREATE TABLE immunizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_code TEXT NOT NULL,
    dose_number INTEGER NOT NULL,
    evidence TEXT NOT NULL DEFAULT 'given_here'
        CHECK (evidence IN ('given_here', 'card', 'parent_report')),
    date_administered TEXT,
    place_given TEXT,
    administered_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (evidence <> 'given_here' OR date_administered IS NOT NULL),
    UNIQUE (patient_id, vaccine_code, dose_number),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
);

-- One row per vaccination given outside the EPI schedule -- to a patient of any
-- age, including adults. Separate from `immunizations` on purpose, and the
-- separation is the feature.
--
-- `immunizations` exists to answer "is this child on the DOH EPI schedule?", so
-- everything reading it is scoped to the under-five cohort that schedule
-- describes. This table answers only "was this vaccine given?", which is true of
-- any patient at any age, and it carries no schedule column of any kind -- no due
-- date, no status, no grace period. There is no single official adult
-- immunisation schedule in the Philippines to evaluate against, so a due/overdue
-- reading here would be invented precision rather than a clinical fact. That is
-- the split HL7 FHIR draws between Immunization and ImmunizationRecommendation.
--
-- vaccine_name holds the name itself, not a code, because nothing looks these
-- rows up: the entry form's list is an explicitly non-exhaustive convenience
-- ending in a free-text row, and a code for a vaccine nobody anticipated would
-- have to be invented at the point of typing. The EPI table stores a code for
-- the opposite reason -- EPI_SCHEDULE finds records by it.
--
-- dose_number is nullable, unlike the EPI table's. Most of these have no fixed
-- dose count, and requiring a number would force a health worker to invent one.
--
-- UNIQUE (patient_id, vaccine_name, date_administered) rather than the EPI
-- table's UNIQUE across dose numbers. Influenza is one shot every year for life
-- and a Td booster a decade later is a new dose, not a duplicate, so a
-- dose-spanning constraint would refuse real events. The same vaccine to the
-- same patient on the same day is still one event however often the form is
-- submitted, which is what the date makes true.
--
-- The three foreign keys match `immunizations` exactly, for the same reasons.
CREATE TABLE general_vaccinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_name TEXT NOT NULL,
    dose_number INTEGER,
    date_administered TEXT NOT NULL,
    administered_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (patient_id, vaccine_name, date_administered),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
);

-- Medicine actually handed to a patient, taken off the shelf.
--
-- The other half of Objective 2's "real-time monitoring". inventory_items holds
-- one number per item, and every other writer moves it up or corrects it
-- wholesale; this is the only thing in the system that takes units off a shelf,
-- and models/dispensing.py decrements inventory_items.stock_quantity in the same
-- transaction that inserts the row here, so the record and the shelf can never
-- disagree about what left.
--
-- One row is HL7 FHIR's MedicationDispense in its ward-stock sense -- issuing a
-- dose from stock to a patient for consumption -- and, like FHIR's, it is tied to
-- the encounter that justified it. There is no dispensing path in this system
-- that is not anchored to a consultation, which is what DOH guidance for a
-- barangay-level facility requires: medicine given out here is traceable to the
-- medical supervision that authorised it.
--
-- inventory_item_id is the traceability link back to the batch, the expiry date
-- and the supplier the units came from. medicine_name and unit are a snapshot of
-- what was actually handed over: the Add / Edit Medicine form can rewrite an
-- inventory row's name in place, and a history rendered purely by joining would
-- silently re-label a dose given months ago. Same pair, same reason, as
-- sms_broadcast_recipients' patient_id alongside recipient_name.
--
-- UNIQUE (consultation_id, inventory_item_id): one medicine, one line per visit,
-- with the amount on it. Dispensing is quantitative and so cannot use the
-- INSERT OR IGNORE that makes a double-submitted vaccination form harmless -- an
-- ignored insert here would leave the stock decrement beside it unmatched. So a
-- double submission is refused rather than absorbed, and this is what it is
-- refused on. See migrate_add_medicine_dispensing.py for the full reasoning.
CREATE TABLE medicine_dispensing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    inventory_item_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    unit TEXT,
    quantity_dispensed INTEGER NOT NULL CHECK (quantity_dispensed > 0),
    date_dispensed TEXT NOT NULL,
    dispensed_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (consultation_id, inventory_item_id),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE RESTRICT,
    FOREIGN KEY (dispensed_by) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    module TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- One row per community SMS broadcast composed and sent from Screen 09.
--
-- A broadcast belongs to no patient: it is what the barangay said to the
-- community, so it is anchored to the account that sent it and to nothing else.
--
-- The audience is stored twice on purpose. `audience` is the key the recipients
-- were resolved from ('seniors'), and `audience_label` is what it was called at
-- the time ('Senior Citizens'). Renaming an audience later must not silently
-- rewrite what a broadcast already sent said it went to.
--
-- recipient_count / sent_count / failed_count are sums of the real per-recipient
-- rows in sms_broadcast_recipients, kept here so the history table does not need
-- a subquery per row. There is no delivered_count, and there is no delivery
-- percentage: Semaphore reports delivery through a callback this application does
-- not expose, so "accepted by the gateway" is the strongest claim the data
-- supports and the only one recorded.
--
-- segments and encoding are what the message cost to send -- see the segment
-- arithmetic in utils/sms.py. One credit per segment per recipient.
--
-- delivery_mode is per broadcast, not per system: 'live' when SEMAPHORE_API_KEY
-- was configured at send time, 'simulated' when it was not. A history that spans
-- the day credentials arrive stays truthful about which messages really left.
CREATE TABLE sms_broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    message TEXT NOT NULL,
    category TEXT,
    audience TEXT NOT NULL,
    audience_label TEXT NOT NULL,
    recipient_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    segments INTEGER NOT NULL DEFAULT 0,
    encoding TEXT NOT NULL DEFAULT 'GSM-7',
    status TEXT NOT NULL DEFAULT 'Sent' CHECK (status IN ('Sent', 'Partial', 'Failed')),
    delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('live', 'simulated')),
    sent_by INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sent_by) REFERENCES users(id) ON DELETE RESTRICT
);

-- One row per number a broadcast was actually attempted against, with the
-- gateway's own reply. This is what makes the counts above real rather than
-- assumed, and it is the only place a per-number failure can be read back.
--
-- recipient_name and mobile_number are copied rather than joined: they record
-- who was texted and on what number at the time. A patient who later changes
-- their number must not retroactively change who a past advisory reached.
--
-- patient_id / user_id are ON DELETE SET NULL, and both are nullable, because a
-- recipient is one or the other -- a patient contact or a staff account.
CREATE TABLE sms_broadcast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL,
    patient_id INTEGER,
    user_id INTEGER,
    recipient_name TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Sent', 'Failed')),
    gateway_response TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (broadcast_id) REFERENCES sms_broadcasts(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- One text message to one patient about one of their own appointments -- the
-- individual counterpart of the two broadcast tables above. It is a separate
-- table rather than a nullable patient_id on sms_broadcasts because the two
-- record different things: a broadcast is what the barangay told the community
-- and belongs to no patient, while a row here belongs to one appointment and is
-- part of what that person was told about their own care.
--
-- event is what the message is about, and it is CHECK-constrained to the three
-- things worth telling one patient: a new booking, a move, a cancellation. There
-- is no 'no-show' member -- somebody who did not attend already knows, and a text
-- saying so would be a reprimand sent at the barangay's expense.
--
-- status admits 'Sent' and 'Failed' and nothing else, exactly as
-- sms_broadcast_recipients.status does, and for the same reason: nothing in this
-- application receives Semaphore's delivery callbacks, so no row could ever
-- legitimately hold 'Delivered'.
--
-- message, recipient_name and mobile_number are stored rather than recomposed or
-- joined. They record what was actually sent, to whom, and on what number, at
-- the time. A patient who later changes their number -- or an appointment later
-- moved again -- must not retroactively rewrite the history of what was sent.
--
-- delivery_mode is per message for the reason it is per broadcast: 'live' when
-- SEMAPHORE_API_KEY was configured at send time, 'simulated' when it was not.
--
-- appointment_id and patient_id are ON DELETE SET NULL: the message was sent
-- whether or not the rows it was composed from still exist. sent_by is ON DELETE
-- RESTRICT, matching sms_broadcasts.sent_by -- an account cannot be deleted out
-- from under a record naming them as the sender.
CREATE TABLE appointment_sms_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    appointment_id INTEGER,
    patient_id INTEGER,
    event TEXT NOT NULL CHECK (event IN ('booked', 'rescheduled', 'cancelled')),
    recipient_name TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    message TEXT NOT NULL,
    segments INTEGER NOT NULL DEFAULT 0,
    encoding TEXT NOT NULL DEFAULT 'GSM-7',
    status TEXT NOT NULL CHECK (status IN ('Sent', 'Failed')),
    delivery_mode TEXT NOT NULL CHECK (delivery_mode IN ('live', 'simulated')),
    gateway_response TEXT,
    sent_by INTEGER NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (sent_by) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT,
    updated_by INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Which services the health center runs on which days, one service per row,
-- entered by the Administrator. It is the successor to advance booking: the
-- facility decides the days, and patients walk in. It is read-only information
-- -- nothing refuses a check-in or a consultation because of it.
--
-- NO ROW IS EVER SEEDED. The health center's real days have not been confirmed,
-- and a plausible timetable here would be read as a fact. The screens that read
-- this table say plainly when it is empty. See migrate_add_service_schedule.py.
--
-- The days are two columns and there is no "pattern type" column:
--   weekdays        ISO weekday numbers, ascending: '1' Monday .. '7' Sunday
--   weeks_of_month  NULL for every week, or which occurrences in the month:
--                   '2,4' is the 2nd and 4th
-- so "daily, Monday to Friday" is ('1,2,3,4,5', NULL), "every Monday and
-- Thursday" is ('1,4', NULL), and "every 2nd and 4th Wednesday" is ('3', '2,4').
-- The pattern is what the two columns say, so it cannot disagree with them.
-- Weeks run 1st to 4th only: most months have no 5th occurrence of a weekday.
CREATE TABLE service_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK (length(trim(service)) > 0),
    weekdays TEXT NOT NULL CHECK (
        weekdays <> '' AND weekdays NOT GLOB '*[^1-7,]*'
    ),
    weeks_of_month TEXT CHECK (
        weeks_of_month IS NULL
        OR (weeks_of_month <> '' AND weeks_of_month NOT GLOB '*[^1-4,]*')
    ),
    note TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER,
    updated_at TEXT,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_patients_last_name ON patients(last_name);
CREATE INDEX idx_consultations_patient_date ON consultations(patient_id, consultation_date);
-- Answers "has this queue entry already been written up?" before a second
-- consultation can be recorded against the same visit.
CREATE INDEX idx_consultations_appointment ON consultations(appointment_id);
CREATE INDEX idx_inventory_low_stock ON inventory_items(stock_quantity, low_stock_threshold);
CREATE INDEX idx_appointments_date ON appointments(appointment_date, status);
-- The consultation queue reads one day's rows and orders them by arrival.
CREATE INDEX idx_appointments_queue ON appointments(appointment_date, status, checked_in_at);
-- The profile tab and the schedule calculation read one child's doses; the
-- consultation form reads back what was given during one visit.
CREATE INDEX idx_immunizations_patient ON immunizations(patient_id, date_administered);
CREATE INDEX idx_immunizations_consultation ON immunizations(consultation_id);
-- The Patient Profile reads one patient's non-EPI vaccination history, newest
-- first; the consultation form reads back what was given during one visit.
CREATE INDEX idx_general_vaccinations_patient ON general_vaccinations(patient_id, date_administered);
CREATE INDEX idx_general_vaccinations_consultation ON general_vaccinations(consultation_id);
-- Patient Profile reads one patient's dispensing history, newest first; the
-- consultation form and the dashboard's Recent Consultations table read what was
-- given during one visit; Reports & Analytics ranks the most-dispensed medicines
-- inside a date range.
CREATE INDEX idx_medicine_dispensing_patient ON medicine_dispensing(patient_id, date_dispensed);
CREATE INDEX idx_medicine_dispensing_consultation ON medicine_dispensing(consultation_id);
CREATE INDEX idx_medicine_dispensing_item ON medicine_dispensing(inventory_item_id, date_dispensed);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, created_at);
-- The history table is one page of broadcasts, newest first.
CREATE INDEX idx_sms_broadcasts_sent_at ON sms_broadcasts(sent_at, id);
-- The detail panel reads one broadcast's recipients.
CREATE INDEX idx_sms_recipients_broadcast ON sms_broadcast_recipients(broadcast_id, status);
-- The individual-confirmation history panel is one page of messages, newest
-- first; the patient-facing lookups read one appointment's messages.
CREATE INDEX idx_appointment_sms_sent_at ON appointment_sms_messages(sent_at, id);
CREATE INDEX idx_appointment_sms_appointment ON appointment_sms_messages(appointment_id, sent_at);
CREATE INDEX idx_settings_key ON settings(setting_key, updated_at);

"""Migration: three demo-data corrections found by the 4 September 2026 audit.

WHY THESE THREE ARE ONE SCRIPT
-------------------------------
They are three different tables and three different decisions, and they are here
together because they answer one question: what in this database would a defence
panel read and not believe. Splitting them into three scripts would mean three
backups taken minutes apart and three separate "everything else is unchanged"
proofs, each blind to the other two. One script, one backup, and one verification
pass that permits exactly the changes declared below and nothing else is the
stronger guarantee, and it is the one this file makes.

Each part is independently skippable: a part whose rows are already correct
reports so and writes no audit entry, so re-running is safe.


PART 1 -- THE TEST PATIENT PAT-027 "Joe Rogan"
-----------------------------------------------
Patient 92 is named after a real, internationally recognised public figure. It is
somebody trying the Register Patient form with the first name that came to mind
on 2026-08-26, and the record shows it: the emergency contact is "John" with no
surname, and the medical conditions and allergies are both empty lists.

It matters more than an odd-looking row because of where it sits. Patient Records
is the first screen of the first objective, and PAT-027 is visible on it without
scrolling. 06_DESIGN_CONTENT_LIBRARY.md requires realistic Filipino healthcare
information throughout and 03_SCREEN_SPECIFICATIONS.md forbids sample content by
name; this is the clearest violation of both left in the database.

WHAT GOES WITH THE PATIENT, AND IN WHICH ORDER
    appointment_sms_messages  1, 2   the two messages sent about appointment 75
    appointments             75      2026-09-02 08:00 Consultation, Cancelled
    patients                 92      PAT-027 "Joe Rogan"

Children first, so no statement ever runs against a row whose referent has
already gone. The two SMS rows carry foreign keys to BOTH the patient and the
appointment, so they must go before either.

The appointment is deleted rather than left Cancelled for the same reason
migrate_remove_fake_patient.py gave: `Cancelled` is a statement that a real
booking was called off, and this booking was never real. The row is also
foreign-keyed to patient 92 and could not survive its removal without orphaning.

WHAT IS NOT REMOVED, AND THIS IS THE IMPORTANT PART
    audit_logs 958, 959

Those two entries record that the system composed and sent (in simulated mode)
an appointment SMS on 2026-09-01, and they name "Joe Rogan (PAT-027)". They stay.

This is not an oversight and it is not laziness. It is the same rule
migrate_remove_test_residue.py followed when it left entries 951 and 952 in
place, and the same rule 06_DESIGN_CONTENT_LIBRARY.md states about the
Administrator persona correction: **an audit trail is not rewritten to match a
tidier version of the past.** The sends happened. `audit_logs` also has no
foreign key to `patients` -- its only FK is `user_id` -> `users` -- so removing
the patient orphans nothing in the referential sense; these entries are text
describing an event, not pointers to a row.

The practical consequence, stated so nobody is surprised by it in front of a
panel: **searching Audit Logs for "Rogan" will still return two entries.** That
is the correct behaviour of an audit trail and it is defensible out loud. If the
team decides it wants those entries gone as well, that is a separate decision
about whether this project's audit trail is immutable, and it should be made
explicitly rather than smuggled into a data cleanup. This script does not make
it.


PART 2 -- THE TWO HAND-ENTERED INVENTORY ROWS
----------------------------------------------
MED-0016 (Diatabs) and MED-0017 (Mefenamic Acid) were typed into the Add Medicine
form on 2026-08-07. Every other row in `inventory_items` came from the seed and
reads in one register; these two read in another -- all capitals, a misspelling,
and on MED-0016 three fields that are clinically wrong.

MED-0016, field by field:

  supplier    'PHILIPPINE GOVERMENT' -> 'DOH Regional Warehouse - Caraga'
      Misspelled ("GOVERMENT"), and not a supply channel this dataset uses. The
      operator meant "supplied by government", and the house-style rendering of
      exactly that is the DOH regional warehouse this database already names on
      six other items. San Francisco, Surigao del Norte is in Caraga, so the
      channel is the right one as well as the consistent one. The misspelling is
      the part that matters most: `supplier` is a printed column on Medicine
      Inventory and appears in every inventory export a panel would be handed.

  notes       'MEDICINE FOR STOMACH' -> a specific dispensing note
      All capitals and vague. Replaced with what a health worker would actually
      need to know at the point of issue.

  drug_class  'Antibiotic' -> 'Antidiarrheal'
      Simply wrong, and wrong in the one way a clinical reviewer would catch
      immediately. Diatabs is loperamide; loperamide is not an antibiotic. This
      field is in scope even though the audit only named supplier and notes,
      because the replacement note says what the medicine is for -- leaving the
      class as "Antibiotic" beside it would have the row contradict itself.

  generic_name 'DIATABS' -> 'Loperamide Hydrochloride'
      "DIATABS" is the brand. A generic-name column holding a brand name is not a
      casing problem, it is the wrong value.

  brand_name  'DIATABS' -> 'Diatabs'          casing
  manufacturer 'UNILAB' -> 'Unilab, Inc.'     casing, matching 'Pharex Health Corp.'
  dosage_strength '500mg' -> '2 mg'
      Loperamide is dosed at 2 mg per unit. 500 mg is not a strength this
      medicine comes in; it looks like the 500 mg carried by the paracetamol and
      mefenamic acid rows nearby.
  dosage_form 'Capsule' -> 'Tablet'
      NOT changed to match real-world Diatabs, deliberately. `unit` on this row
      is 'Tablet', and the two historical `medicine_dispensing` rows that issued
      this item (ids 3 and 13) both recorded 'Tablet'. Those rows say what was
      actually handed to a patient and are not editable by this or any other
      migration, so the item is aligned to them rather than the other way round.
      Changing `unit` instead would have left the stock card disagreeing with its
      own dispensing history.
  storage_location 'CABINET 2' -> 'Cabinet 2'
      Casing only. The house pattern elsewhere is "Cabinet A, Shelf 2", and this
      row is deliberately NOT rewritten into it: there is no shelf recorded here
      and inventing one to match a pattern is precisely the kind of invented
      detail 06_DESIGN_CONTENT_LIBRARY.md §17 exists to record the cost of. The
      operator's own numbering is kept and only the shouting is removed.

MED-0017, field by field:

  supplier    'UNILAB' -> 'Unilab, Inc.'
      Casing. Kept as a manufacturer-as-supplier, which this dataset already does
      with 'Pharex Health Corp.', because Dolfenal is Unilab's and there is no
      evidence of any other channel to substitute.
  manufacturer 'UNILAB' -> 'Unilab, Inc.'     casing
  dosage_strength '500' -> '500 mg'           missing unit
  storage_location 'CABINET3' -> 'Cabinet 3'  casing and spacing

  `notes` is left NULL. Every other row in the table has no note, and writing one
  here to fill a gap would be inventing content rather than correcting it.
  `low_stock_threshold` of 1 is left alone: it is unusual beside the 30-200 the
  other rows carry, but it is an operator's choice about a stock item, not an
  error, and this script does not overrule those.

No stock figure, expiry date, batch number or status is touched by this part.
Nothing here changes what is on the shelf.


PART 3 -- PERSONAS FOR THE STAFF AND OFFICIAL DEMO ACCOUNTS
------------------------------------------------------------
`users` 2 and 3 carry their own role as their name:

    id 2  username 'staff'     full_name 'Health Center Staff'
    id 3  username 'official'  full_name 'Barangay Official'

The Administrator was given a real persona on 2026-09-04 and these two were not,
so the profile chip shows a person for one role and a job title for the other
two. It reads as unfinished, and a panel that has just been shown "Kagawad
Antonio Acido" may reasonably ask why the other two accounts are not people.

    id 2  -> 'Jennifer Ramos'
    id 3  -> 'Hon. Michael Flores'

Both names are taken from 06_DESIGN_CONTENT_LIBRARY.md's own example lists for
those roles. Neither collides with a surname already in the patient roster, which
is why "Maria Santos", "Angela Cruz" and "Hon. Karen Mendoza" were passed over,
and "Joshua Reyes" was passed over for a stronger reason: it was the invented
Administrator persona this project spent a migration removing, and putting it
back on a different account would be actively confusing.

THESE TWO ARE NOT REAL PEOPLE, AND THAT IS THE DIFFERENCE FROM THE ADMINISTRATOR.
Kagawad Antonio Acido is stated in 06_DESIGN_CONTENT_LIBRARY.md as fact because
he is the real person holding that account, confirmed by the project's technical
adviser. These two are demonstration personas drawn from that document's example
lists, and the document is updated to say exactly that rather than to imply a
third and fourth confirmed identity.

WHAT DOES NOT CHANGE: both usernames, both roles, both password hashes. Only
`full_name` is written. Username is fixed for the life of an account in this
project, and the role is the value the schema's CHECK constraint allows and
`role_required()` compares.

WHAT THIS DOES TO THE AUDIT TRAIL: nothing retrospective. 606 existing entries
quote these accounts by username and by their old full name, and every one of
them is left exactly as written -- the same rule Part 1 follows and the same one
the Administrator persona correction followed. Entries written from now on will
carry the new names. A reader comparing an old entry with a new one sees an
account that was renamed, which is what happened.

ONE APPLICATION CODE CHANGE ACCOMPANIES THIS PART, AND IT IS NOT OPTIONAL.
`utils/names.py` draws the two-letter avatar and skips honorifics so the circle
reads the person rather than their title. Its TITLES set deliberately excluded
"hon.", and said so in its own docstring: "no account in this system carries it
... It belongs in this list on the day such an account exists, not before."
Account 3 is now that account, so "hon." is added to TITLES in the same commit.
Without it the Barangay Official's avatar reads "HF" -- the honorific and the
surname -- instead of "MF".


WHAT THIS TOUCHES IN TOTAL
---------------------------
Four rows deleted, four rows updated, and up to three INSERTs into audit_logs.
Every other row of every table is compared column by column against the backup
taken immediately before this run, and any difference at all aborts the
transaction before it commits.

Three audit entries rather than one, because these are three decisions in three
modules and the trail is read per module. A part that finds its rows already
correct writes nothing.

Idempotent. Re-running reports rows already gone or already corrected and writes
no second entry.

Run:  python migrate_demo_data_hygiene.py
"""
import os
import sqlite3
import sys

import config

BACKUP = os.path.join(
    os.path.dirname(os.path.abspath(config.DATABASE)),
    "app.db.PRETASK_BACKUP_joerogan-supplier-personas_20260905_040813",
)

# ---------------------------------------------------------------- PART 1 ----
# (table, id, what it is) in deletion order -- children first.
REMOVE = [
    ("appointment_sms_messages", 1,
     "APT-SMS-2026-0001, booked, to Joe Rogan on 09055477625"),
    ("appointment_sms_messages", 2,
     "APT-SMS-2026-0002, cancelled, to Joe Rogan on 09055477625"),
    ("appointments", 75,
     "patient 92, 2026-09-02 08:00, Consultation, Cancelled"),
    ("patients", 92, 'PAT-027 "Joe Rogan", Active'),
]

# A migration that deletes by id alone deletes whatever has since moved into
# that id. Each row is matched on the fields that make it identifiable before
# anything is written; a mismatch refuses that row rather than guessing.
IDENTITY = {
    ("patients", 92): {
        "patient_id": "PAT-027",
        "first_name": "Joe",
        "last_name": "Rogan",
        "birth_date": "1970-03-19",
        "created_at": "2026-08-26 04:47:18",
    },
    ("appointments", 75): {
        "patient_id": 92,
        "appointment_date": "2026-09-02",
        "appointment_time": "08:00",
        "status": "Cancelled",
        "created_at": "2026-09-01 02:40:44",
    },
    ("appointment_sms_messages", 1): {
        "reference": "APT-SMS-2026-0001",
        "patient_id": 92,
        "appointment_id": 75,
        "event": "booked",
    },
    ("appointment_sms_messages", 2): {
        "reference": "APT-SMS-2026-0002",
        "patient_id": 92,
        "appointment_id": 75,
        "event": "cancelled",
    },
}

# Every table with a foreign key to patients or appointments, and the column
# that holds it. Asked of the database at run time rather than taken from the
# survey in the docstring, so a reference created between then and now stops
# this run instead of being deleted out from under.
REFERENCES = [
    ("consultations", "patient_id", "patients", 92),
    ("consultations", "appointment_id", "appointments", 75),
    ("immunizations", "patient_id", "patients", 92),
    ("general_vaccinations", "patient_id", "patients", 92),
    ("medicine_dispensing", "patient_id", "patients", 92),
    ("sms_broadcast_recipients", "patient_id", "patients", 92),
    ("appointment_sms_messages", "patient_id", "patients", 92),
    ("appointment_sms_messages", "appointment_id", "appointments", 75),
]

# ------------------------------------------------------- PARTS 2 AND 3 ----
# (table, id, {column: (before, after)}). `before` is asserted before the write
# for the same reason IDENTITY exists: a column that no longer holds the value
# this migration was written against is a column somebody else has changed, and
# overwriting it blind would discard their edit.
UPDATE = [
    ("inventory_items", 16, "MED-0016 Diatabs", {
        "supplier": ("PHILIPPINE GOVERMENT", "DOH Regional Warehouse - Caraga"),
        "notes": ("MEDICINE FOR STOMACH",
                  "Anti-diarrhoeal for acute, uncomplicated diarrhoea. Not to be "
                  "issued where there is fever or blood in the stool; refer those "
                  "cases for consultation."),
        "drug_class": ("Antibiotic", "Antidiarrheal"),
        "generic_name": ("DIATABS", "Loperamide Hydrochloride"),
        "brand_name": ("DIATABS", "Diatabs"),
        "manufacturer": ("UNILAB", "Unilab, Inc."),
        "dosage_strength": ("500mg", "2 mg"),
        "dosage_form": ("Capsule", "Tablet"),
        "storage_location": ("CABINET 2", "Cabinet 2"),
    }),
    ("inventory_items", 25, "MED-0017 Mefenamic Acid", {
        "supplier": ("UNILAB", "Unilab, Inc."),
        "manufacturer": ("UNILAB", "Unilab, Inc."),
        "dosage_strength": ("500", "500 mg"),
        "storage_location": ("CABINET3", "Cabinet 3"),
    }),
    ("users", 2, "the Health Center Staff demo account", {
        "full_name": ("Health Center Staff", "Jennifer Ramos"),
    }),
    ("users", 3, "the Barangay Official demo account", {
        "full_name": ("Barangay Official", "Hon. Michael Flores"),
    }),
]

# Which part each audit entry belongs to, and who it is attributed to.
#
# Part 1 goes to user 2: appointment 75 carries scheduled_by = 2 and both SMS
# rows carry sent_by = 2, so the removal is recorded against the account that
# created the rows, exactly as migrate_remove_fake_patient.py did.
#
# Parts 2 and 3 go to user 1: correcting master inventory data and renaming an
# account are both Administrator actions, and only an Administrator can reach
# the screens that perform them.
AUDIT = [
    ("part1", 2, "Removed test data", "Patient Records",
     'Removed the test patient record PAT-027 "Joe Rogan" (patient id 92), the '
     "appointment booked for them (#75, a Consultation for Sep 02, 2026 at "
     "08:00, already Cancelled) and the two appointment SMS messages sent about "
     "it (APT-SMS-2026-0001 booked and APT-SMS-2026-0002 cancelled). The patient "
     "was registered on Aug 26, 2026 at 04:47:18 by somebody trying the Register "
     "Patient form: the name is that of a real, internationally recognised "
     "public figure, the emergency contact is a bare first name, and both the "
     "medical conditions and allergies are empty. It was removed rather than "
     "archived because it describes no person and no event, which is the same "
     "ground the Aug 31 and Sep 02, 2026 test-data removals were made on. "
     "Nothing else referred to it: no consultation, immunisation, vaccination, "
     "medicine issue or broadcast recipient, so no stock and no clinical history "
     "was affected. NOTE FOR ANYONE READING THE OLDER ENTRIES: audit entries "
     "#958 and #959, which record the two SMS sends and name this patient, were "
     "deliberately NOT removed. They record what the system actually did on Sep "
     "01, 2026, and an audit trail is not rewritten to match a tidier past. A "
     'search of this trail for "Rogan" will still return them, and that is '
     "correct. PAT-027 is now free and the next real registration will be given "
     "it"),
    ("part2", 1, "Corrected inventory record details", "Medicine Inventory",
     "Corrected two hand-entered stock records, MED-0016 (Diatabs) and MED-0017 "
     "(Mefenamic Acid), both typed into the Add Medicine form on Aug 07, 2026 in "
     "a different style from every seeded row. On MED-0016: the supplier read "
     '"PHILIPPINE GOVERMENT" -- misspelled, and not a channel this database '
     'uses -- and is now "DOH Regional Warehouse - Caraga", the government '
     "channel already named on six other items and the correct region for San "
     'Francisco, Surigao del Norte. The note read "MEDICINE FOR STOMACH" and now '
     "states what a health worker needs at the point of issue. Three clinical "
     'fields were wrong and are corrected: the drug class read "Antibiotic" for '
     "what is an antidiarrhoeal, the generic name held the brand "
     '"DIATABS" rather than Loperamide Hydrochloride, and the strength read '
     '"500mg" where loperamide is dosed at 2 mg. The dosage form was aligned to '
     '"Tablet" to agree with the item unit and with the two dispensing records '
     "that issued it, which state what was actually handed to a patient and were "
     "not altered. On MED-0017: the supplier and manufacturer were shouted "
     '"UNILAB" and are now "Unilab, Inc.", and the strength "500" now carries '
     "its unit. Storage locations on both were un-shouted but deliberately not "
     "rewritten into the house shelf pattern, because no shelf is recorded on "
     "either row and inventing one would be inventing data. No stock figure, "
     "expiry date, batch number or status was touched, and nothing on the shelf "
     "changed"),
    ("part3", 1, "Updated user account", "User Management",
     "Gave the two demonstration accounts real personas, so that all three roles "
     "are represented by a person rather than one person and two job titles. "
     'Account "staff" was named "Health Center Staff" and is now Jennifer '
     'Ramos; account "official" was named "Barangay Official" and is now Hon. '
     "Michael Flores. Both names are taken from the project's own design content "
     "library example lists for those roles, and neither collides with a surname "
     "already on the patient roster. THESE TWO ARE DEMONSTRATION PERSONAS AND "
     "NOT CONFIRMED REAL PEOPLE, which is the difference between them and the "
     "Administrator account: Kagawad Antonio Acido is the real holder of that "
     "account, confirmed by the project's technical adviser. Usernames, roles "
     "and password hashes are unchanged -- only the display name was written. "
     "Existing audit entries naming these accounts by their old full name were "
     "not rewritten, so entries before and after this point differ, which is "
     "what a rename looks like in a trail that is not edited"),
]

ALL_TABLES = (
    "patients", "consultations", "appointments", "inventory_items",
    "medicine_dispensing", "immunizations", "general_vaccinations",
    "sms_broadcasts", "sms_broadcast_recipients", "appointment_sms_messages",
    "settings", "users",
)


def snapshot(conn, tables=ALL_TABLES):
    """Every row of every table, keyed by table and id, for a column-level diff."""
    return {
        table: {
            row["id"]: dict(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")
        }
        for table in tables
    }


def main():
    if not os.path.exists(BACKUP):
        print(f"The reference backup is missing:\n  {BACKUP}\n"
              "This migration proves it changed only what it says it changed by "
              "diffing against that file, and will not run without it. Nothing "
              "has been changed.")
        sys.exit(1)

    reference = sqlite3.connect(f"file:{BACKUP}?mode=ro", uri=True)
    reference.row_factory = sqlite3.Row
    expected = snapshot(reference)
    expected_audit = {
        row["id"]: dict(row)
        for row in reference.execute("SELECT * FROM audit_logs ORDER BY id")
    }
    reference.close()

    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    before = snapshot(conn)
    before_audit = {row["id"] for row in conn.execute("SELECT id FROM audit_logs")}

    print("rows before migration:")
    for table in ALL_TABLES:
        print(f"  {table:26} {len(before[table]):4}   "
              f"(backup holds {len(expected[table])})")

    # -- PART 1: is anything pointing at the rows to be removed? -------------
    print("\nPART 1 -- references to patient 92 / appointment 75:")
    blocking = []
    for table, column, parent, row_id in REFERENCES:
        found = [r["id"] for r in conn.execute(
            f"SELECT id FROM {table} WHERE {column} = ?", (row_id,))]
        # The two SMS rows are themselves being removed, so they are expected to
        # appear here. Anything else is a genuine blocker.
        unexpected = [i for i in found
                      if (table, i) not in {(t, r) for t, r, _ in REMOVE}]
        print(f"  {table + '.' + column:38} = {row_id:<4} {len(found)} row(s)"
              + (f"  {found}" if found else "")
              + ("  <- all being removed by this script" if found and not unexpected else ""))
        if unexpected:
            blocking.append(f"{table}.{column} still names {parent}.{row_id}: "
                            f"rows {unexpected}")
    if blocking:
        conn.rollback()
        conn.close()
        print("\nREFUSED -- something refers to these rows, so removing them "
              "would orphan it. Nothing has been changed:")
        for problem in blocking:
            print("  -", problem)
        sys.exit(1)

    removed, absent, refused = [], [], []
    for table, row_id, description in REMOVE:
        row = before[table].get(row_id)
        if row is None:
            absent.append((table, row_id, description))
            continue
        mismatched = [
            f"{column}: {row[column]!r} (expected {value!r})"
            for column, value in IDENTITY[(table, row_id)].items()
            if row[column] != value
        ]
        if mismatched:
            refused.append((table, row_id, mismatched))
            continue
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        removed.append((table, row_id, description))

    print(f"\n  rows removed:     {len(removed)}")
    for table, row_id, description in removed:
        print(f"    {table}.{row_id}  {description}")
    for table, row_id, description in absent:
        print(f"    already gone:   {table}.{row_id}  {description}")
    for table, row_id, mismatched in refused:
        print(f"    REFUSED {table}.{row_id} is not the row this migration "
              "describes, so it is a different record now and is not touched:")
        for detail in mismatched:
            print(f"        {detail}")

    # -- PARTS 2 AND 3: the field-level corrections --------------------------
    print("\nPARTS 2 AND 3 -- field corrections:")
    updated, already, update_refused = [], [], []
    for table, row_id, description, columns in UPDATE:
        row = before[table].get(row_id)
        if row is None:
            update_refused.append((table, row_id, [f"row {row_id} does not exist"]))
            continue
        wrong = [f"{c}: {row[c]!r} (expected {old!r} or {new!r})"
                 for c, (old, new) in columns.items()
                 if row[c] != old and row[c] != new]
        if wrong:
            update_refused.append((table, row_id, wrong))
            continue
        changes = {c: new for c, (old, new) in columns.items() if row[c] == old}
        if not changes:
            already.append((table, row_id, description))
            continue
        conn.execute(
            f"UPDATE {table} SET " + ", ".join(f"{c} = ?" for c in changes)
            + " WHERE id = ?",
            (*changes.values(), row_id),
        )
        updated.append((table, row_id, description, changes, row))

    for table, row_id, description, changes, old_row in updated:
        print(f"  {table}.{row_id}  {description}")
        for column, new in changes.items():
            print(f"      {column:18} {old_row[column]!r}")
            print(f"      {'':18} -> {new!r}")
    for table, row_id, description in already:
        print(f"  already correct:  {table}.{row_id}  {description}")
    for table, row_id, wrong in update_refused:
        print(f"  REFUSED {table}.{row_id} does not hold the values this "
              "migration was written against:")
        for detail in wrong:
            print(f"      {detail}")

    if refused or update_refused:
        conn.rollback()
        conn.close()
        print("\nREFUSED -- at least one row is not what this migration "
              "describes. Nothing has been changed.")
        sys.exit(1)

    # -- say so in the audit trail ------------------------------------------
    part_did_something = {
        "part1": bool(removed),
        "part2": any(t == "inventory_items" for t, _, _, _, _ in updated),
        "part3": any(t == "users" for t, _, _, _, _ in updated),
    }
    entries_written = 0
    for part, user_id, action, module, details in AUDIT:
        if not part_did_something[part]:
            continue
        conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, module, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, action, module, details, "127.0.0.1"),
        )
        entries_written += 1

    # -- verify against the backup before committing -------------------------
    after = snapshot(conn)
    intended_removals = {(t, r) for t, r, _ in REMOVE}
    gone = {(t, r) for t, r, _ in removed}
    intended_updates = {(t, r): cols for t, r, _, cols in
                        [(t, r, d, c) for t, r, d, c in UPDATE]}
    problems = []

    for table in ALL_TABLES:
        want, got = expected[table], after[table]
        for row_id, old in want.items():
            new = got.get(row_id)
            if new is None:
                if (table, row_id) not in intended_removals:
                    problems.append(
                        f"{table}.{row_id} was in the backup and is now gone, and "
                        "it is not one of the rows this migration removes")
                continue
            if (table, row_id) in gone:
                problems.append(
                    f"{table}.{row_id} was deleted by this run and is still here")
                continue
            allowed = intended_updates.get((table, row_id), {})
            for column, value in old.items():
                if new[column] == value:
                    continue
                if column in allowed and new[column] == allowed[column][1]:
                    continue    # a declared correction, applied
                problems.append(
                    f"{table}.{row_id} differs from the backup on {column}: "
                    f"{value!r} -> {new[column]!r}, which this migration does "
                    "not declare")
        for row_id in got:
            if row_id not in want:
                problems.append(
                    f"{table}.{row_id} is here but is not in the backup")

    # audit_logs is the one table this migration may ADD to, and it is checked
    # against both references. Against the backup: every entry that was in it
    # must still be there, unchanged -- entries 958 and 959 included, which is
    # the whole point of Part 1's note. Against the start of this run: this run
    # appended exactly the entries it meant to.
    audit_after = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM audit_logs ORDER BY id")
    }
    for row_id, old in expected_audit.items():
        new = audit_after.get(row_id)
        if new is None:
            problems.append(f"audit_logs.{row_id} was removed")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(
                    f"audit_logs.{row_id} differs from the backup on {column}")
    added = [i for i in audit_after if i not in before_audit]
    if len(added) != entries_written:
        problems.append(f"this run appended {len(added)} audit entries, expected "
                        f"{entries_written}")
    since_backup = [i for i in audit_after
                    if i not in expected_audit and i not in added]

    violations = list(conn.execute("PRAGMA foreign_key_check"))
    for violation in violations:
        problems.append(f"foreign key violation: {tuple(violation)}")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"integrity_check said {integrity!r}")

    if problems:
        conn.rollback()
        conn.close()
        print("\nMIGRATION PROBLEMS -- nothing was committed:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    conn.commit()

    print("\nverified against the backup: every row of every table is "
          "column-for-column identical to the state before this run,")
    print(f"  except the {len(removed)} declared removal(s), the {len(updated)} "
          f"declared row correction(s), and {len(added)} appended audit "
          f"entr{'y' if len(added) == 1 else 'ies'} "
          f"{added if added else ''}")
    print("  audit entries 958 and 959, which name the removed patient, were "
          "deliberately preserved and verified unchanged")
    if since_backup:
        print(f"  {len(since_backup)} audit entr(ies) appeared between the backup "
              f"and this run and were left alone: {since_backup}")
    print(f"foreign_key_check:   {len(violations)} violations")
    print(f"integrity_check:     {integrity}")

    print("\nrows after migration:")
    for table in ALL_TABLES:
        delta = len(after[table]) - len(expected[table])
        print(f"  {table:26} {len(after[table]):4}"
              + (f"   ({delta:+d})" if delta else ""))
    conn.close()


if __name__ == "__main__":
    main()

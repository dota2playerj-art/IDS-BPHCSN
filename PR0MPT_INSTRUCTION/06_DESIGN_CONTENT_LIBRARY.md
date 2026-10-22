# IDS-BPHCSN DESIGN CONTENT LIBRARY

Version: 1.0

---

# Purpose

This document contains the official reusable content for the IDS-BPHCSN project.

All AI-generated UI, mockups, reports, dashboards, tables, forms, and sample data should use the information contained in this document.

This ensures consistency across every screen of the application.

---

# Project Location

Country

Philippines

Province

Surigao del Norte

Municipality

San Francisco (formerly Anao-Aon)

Barangay

Barangay Poblacion

Health Center

Barangay Poblacion Health Center

Nearest City

Surigao City, approximately 12 km east

## Why these two values are stated here and not cited

Province and Municipality above read, until 2026-08-26, "(Use the province stated in the approved capstone proposal.)" and the equivalent for Municipality. Those placeholders were never resolved, and the document they point at cannot resolve them: **the approved Capstone Proposal names no municipality and no province anywhere.** This was confirmed by extracting the full text of `Capstone_Proposal.pdf` — all 34 pages decoded — which contains zero occurrences of "Agusan", "San Francisco", "del Sur" or "del Norte". Its only geographic string is "Surigao City", on the title page, as the address of Northeastern Mindanao Colleges. The Proposal refers throughout to "Barangay Poblacion Health Center" and nothing more specific.

An unresolved placeholder pointing at a document that cannot answer it is how a wrong value gets invented, and that is precisely what happened. "San Francisco, Agusan del Sur" — a real municipality, but in the wrong province about 150 km away — was invented in `models/patients.py`, became the closed list the Register Patient form offered, and was written into eleven real patient records before anyone noticed. The full account is Section 17 of `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md`.

The values above are therefore **stated outright rather than cited.** They are the real-world location of the health center, confirmed by the project team and formally approved by the Barangay Poblacion captain on a signed form. For location, this document is the authority: it defers to nothing, and no future session should ever need to infer, guess, or reconstruct these values from anywhere else.

Note also that this municipality has **eleven barangays, and exactly one Poblacion** — not numbered barangays. "Barangay Poblacion" is a complete and unambiguous name here.

---

# User Accounts

## Administrator

Name

Kagawad Antonio Acido

Title

Kagawad (elected barangay councilor), chairing the Health Committee

Username

admin

Role

Administrator

Status

Active

### Why this persona is stated here and not cited

"Dr. Joshua Reyes" was a placeholder, invented for this document and copied from
here into the seeded `admin` account, the sidebar defaults in `utils/context.py`
and the two `_initials()` docstrings. The real person holding this account is
**Antonio Acido**, a Kagawad chairing the barangay's Health Committee, confirmed
by the project team's technical adviser. He is not a physician, so the honorific
is "Kagawad" and not "Dr.".

Two things deliberately did NOT change with the name:

* **The username stays `admin`.** A username is permanently fixed in this
  project -- `models/users.py` says why at length: it is what past audit entries
  are attributable to, so an account needing a different username is a different
  account.
* **The system role stays "Admin" / "Administrator".** That is the value the
  schema's CHECK constraint allows, the string `role_required()` compares, and
  the label User Management shows in the Role column. Only the person filling
  the role changed. What reads "Kagawad, Health Committee" is the subtitle under
  the name in the profile chip, which describes the person, not the permission.

Audit entries already written under the old name were **not** rewritten. They
say what the system recorded at the time, which is what an audit trail is for.

---

## Health Center Staff

Name

Jennifer Ramos

Username

staff

Role

Health Center Staff

Status

Active

Examples (for sample data elsewhere)

Maria Santos

Angela Cruz

Joshua Reyes

Mark Dela Cruz

Jennifer Ramos

---

## Barangay Officials

Name

Hon. Michael Flores

Username

official

Role

Barangay Official

Status

Active

Examples (for sample data elsewhere)

Hon. Roberto Villanueva

Hon. Michael Flores

Hon. Arlene Garcia

Hon. Karen Mendoza

---

### Why these two personas are demonstration personas, and the Administrator's is not

Added 2026-09-05. Until then both accounts carried their own **role** as their
name -- `staff` was called "Health Center Staff" and `official` was called
"Barangay Official" -- so the profile chip showed a person for one role and a job
title for the other two. That reads as unfinished beside a correctly-named
Administrator, and it is the sort of thing a panel asks about.

The names above are drawn from this document's own example lists for those roles,
and neither collides with a surname already on the patient roster. "Maria
Santos", "Angela Cruz" and "Hon. Karen Mendoza" were passed over for that reason.
"Joshua Reyes" was passed over for a stronger one: it was the *invented*
Administrator persona this project spent a migration removing, and putting it
back on a different account would be actively confusing to anyone reading the
audit trail.

**The distinction that matters, and it must not be blurred.** Kagawad Antonio
Acido is stated above as fact because he is the real person holding the
Administrator account, confirmed by the project's technical adviser. **Jennifer
Ramos and Hon. Michael Flores are not real people.** They are demonstration
personas, chosen from a list of examples, and nothing about them has been
confirmed by anybody. If a real health worker or barangay official is ever given
an account, they get their own -- a new account with their own username, not a
rename of one of these, for the same reason `models/users.py` gives at length: a
username is what past audit entries are attributable to, so an account needing a
different username is a different account.

Two consequences worth recording, both matching how the Administrator rename was
handled:

* **Existing audit entries were not rewritten.** 606 entries name these two
  accounts, many by their old full name. They say what the system recorded at the
  time. Entries written before and after 2026-09-05 therefore differ, which is
  what a rename looks like in a trail that is not edited.
* **`utils/names.py` gained "hon." in the same commit.** That file's TITLES set
  had deliberately excluded the honorific, and said so: it "belongs in this list
  on the day such an account exists, not before." Account `official` is now that
  account, so without the entry its avatar would read "HF" -- the title and the
  surname -- rather than "MF".

---

# Sample Patients

Examples

Juan Dela Cruz

Maria Santos

Jose Ramirez

Ana Villanueva

Mark Flores

Jennifer Cruz

Carlo Mendoza

Angelica Reyes

Rose Ramos

Michael Bautista

Christine Gomez

Kevin Navarro

Princess Torres

Joshua Castillo

Rhea Fernandez

Use realistic Filipino names throughout the project.

---

# Common Diseases

Hypertension

Diabetes

Influenza

Dengue Fever

Asthma

Pneumonia

Tuberculosis

COVID-19

Upper Respiratory Infection

Skin Allergy

Common Cold

Fever

Headache

Diarrhea

Urinary Tract Infection

---

# Vaccines

BCG

Hepatitis B

Pentavalent

MMR

Polio

COVID-19 Vaccine

Influenza Vaccine

Pneumococcal Vaccine

Tetanus Toxoid

HPV Vaccine

---

# Medicines

Paracetamol

Amoxicillin

Ibuprofen

Cetirizine

Mefenamic Acid

Metformin

Losartan

Amlodipine

Salbutamol

Omeprazole

Vitamin C

ORS

Multivitamins

Ferrous Sulfate

Calcium Carbonate

---

# Inventory Status

In Stock

Low Stock

Out of Stock

Expired

Near Expiration

---

# Appointment Types

General Consultation

Prenatal Checkup

Child Immunization

Senior Citizen Checkup

Blood Pressure Monitoring

Medical Certificate

Follow-up Consultation

Nutrition Counseling

Vaccination

Family Planning

---

# Notification Categories

Health Advisory

Vaccination Campaign

Medical Mission

Emergency Announcement

Medicine Availability

Barangay Assembly

Prenatal Program

Nutrition Program

COVID Advisory

Dengue Awareness

---

# Sample Notifications

Free vaccination this Friday from 8:00 AM to 3:00 PM.

Senior citizens are encouraged to attend their monthly health checkup.

Medicine inventory has been updated.

New prenatal consultation schedule is available.

Medical mission will be conducted next week.

---

# Dashboard Statistics

Registered Patients

1,248

Today's Appointments

18

Medicines Available

245

Low Stock Medicines

12

Completed Consultations

1,087

Pending Appointments

9

Unread Notifications

6

---

# Report Types

Patient Registration Report

Medicine Inventory Report

Consultation Report

Appointment Report

Monthly Health Report

Vaccination Report

Community Notification Report

User Activity Report

Audit Log Report

---

# Status Labels

Active

Inactive

Pending

Completed

Cancelled

Approved

Rejected

Expired

Scheduled

Available

Unavailable

---

# Priority Levels

Low

Medium

High

Critical

---

# Colors for Status

Green

Success

Orange

Warning

Red

Critical

Blue

Information

Gray

Inactive

---

# Date Format

Month DD, YYYY

Example

July 07, 2026

---

# Time Format

12-hour format

Example

8:30 AM

Rules (Task 21, 2026-10-22). Every time a person reads, on a screen, in an Excel or PDF file or on
a printout, uses this format:

- Time only: "2:21 PM". No leading zero on the hour, one space, AM or PM in capitals.
- Date and time: the screen's own date style, then the time: "Oct 12, 2026 · 11:34 AM". The
  exports' stamp reads "October 22, 2026 at 2:21 PM".
- Noon is "12:00 PM", midnight is "12:00 AM", 00:05 is "12:05 AM".
- Where seconds are shown (the Audit Logs detail), they stay: "2:21:05 PM".
- Stored values, form values and `<input type="time">` fields stay 24-hour ("14:21"); the browser
  shows a time field in its own way.

One helper builds it on each side: `utils/dates.py` `format_time()` / `format_datetime()` (also
the Jinja filters `format_time` and `format_datetime`) and `static/js/time-format.js`
(`IDSTime.formatTime()`, `IDSTime.formatDateTime()`).

---

# Currency

Philippine Peso (PHP)

Example

₱150.00

---

# Language

Primary

English

Future enhancement

Filipino

---

# Charts

Use realistic values.

Avoid perfect numbers.

Example

Patient Registration

January 82

February 95

March 108

April 91

May 126

June 118

---

# Audit Logs

Examples

Administrator logged in

Patient record updated

Medicine inventory adjusted

Appointment created

User password reset

Monthly report generated

---

# General Rule

Never use placeholder content such as:

Lorem Ipsum

John Doe

Sample User

ABC Company

Example Address

Always use realistic Philippine healthcare information that matches the context of the Barangay Health Center.
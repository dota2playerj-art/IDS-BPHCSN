# IDS-BPHCSN DEVELOPMENT GUIDE

Version: 1.0

---

# Purpose

This document defines the official software development standards for the Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications (IDS-BPHCSN).

Every AI assistant, developer, or contributor must follow these standards when generating code or suggesting implementation approaches.

The goal is to keep the project simple, maintainable, beginner-friendly, and aligned with the approved capstone proposal.

---

# Official Technology Stack

## Frontend

- HTML5
- CSS3
- Bootstrap 5
- JavaScript (Vanilla)

---

## Backend

- Python
- Flask

---

## Database

- SQLite

---

## Development Environment

- Visual Studio Code

---

## Browser

- Google Chrome
- Microsoft Edge

---

# System Architecture

Per the approved Capstone Proposal, IDS-BPHCSN follows a **Client-Server Architecture using a
Star Topology**. A single centralized server (Flask application + SQLite database) handles all
application logic and database operations. Client devices — Administrator, Doctor, Health Center Staff, and
Barangay Official workstations, plus mobile browsers for client-side access — each connect
individually to that central server, typically over a local Wi-Fi router.

This is not a distributed or multi-server design. All backend/deployment planning should assume
one Flask process and one SQLite database file as the single source of truth.

---

# Exact System Requirements (per approved Capstone Proposal)

## Admin-side Software
- Windows 10/11
- Python 3.11 or newer with Flask 3.1
- SQLite (built-in)
- Visual Studio Code 1.88+
- Git/GitHub (latest)
- Semaphore API (Free Developer Tier) — official SMS gateway
- Google Chrome / Microsoft Edge (latest)

## Client-side Software
- Windows 10/11 or Android (mobile browser access)
- Chrome / Edge / Safari (latest)
- Bootstrap 5.3 via CDN
- Vanilla JavaScript (no jQuery; nothing is loaded from a CDN)

## Admin-side Hardware
- Intel Core i5 / AMD Ryzen 5 or higher
- 8–16GB RAM
- 512GB SSD
- Windows 10/11 (64-bit)
- Minimum 10 Mbps broadband

## Client-side Hardware
- Desktop, laptop, or mobile device with a browser
- Intel Core / AMD Ryzen 3 or equivalent
- 4–8GB RAM
- 128–256GB SSD
- Minimum 10 Mbps connection, optional mobile hotspot backup
- Connects to the central Flask server via Wi-Fi router

---

# Technologies Not Allowed

Unless explicitly approved by the project team, do NOT introduce:

- React
- Next.js
- Vue.js
- Angular
- Tailwind CSS
- Laravel
- Django
- ASP.NET
- Firebase
- MongoDB
- Supabase
- Node.js
- Express.js

The purpose of this restriction is to keep the project manageable for beginner developers and consistent with the approved capstone proposal.

---

# Bootstrap Guidelines

Bootstrap 5 is the official UI framework.

Use Bootstrap components whenever possible.

Preferred Bootstrap components include:

- Navbar
- Sidebar (customized using Bootstrap)
- Cards
- Tables
- Forms
- Buttons
- Alerts
- Badges
- Modals
- Dropdowns
- Pagination
- Breadcrumbs
- Accordion
- Toast Notifications

Avoid replacing Bootstrap with another UI framework.

---

# HTML Guidelines

Use semantic HTML.

Examples:

<header>

<nav>

<main>

<section>

<article>

<footer>

Avoid unnecessary nested div elements.

Keep HTML organized and readable.

---

# CSS Guidelines

Create separate CSS files.

Avoid inline styling.

Organize CSS into sections:

General

Layout

Sidebar

Header

Dashboard

Forms

Tables

Buttons

Responsive Rules

Comments should clearly identify sections.

---

# JavaScript Guidelines

Vanilla JavaScript is the only scripting used. There is no jQuery, and no script is loaded from a CDN; Bootstrap and Chart.js are vendored under `static/`.

Keep scripts modular.

Separate scripts by feature.

Examples:

login.js

dashboard.js

patient.js

inventory.js

appointments.js

reports.js

Avoid unnecessary third-party JavaScript libraries.

---

# Flask Guidelines

Organize the project using Flask best practices.

Recommended structure:

project/

app.py

templates/

static/

routes/

database/

models/

utils/

Do not place all code inside app.py.

Keep responsibilities separated.

---

# Database Guidelines

Use SQLite.

Recommended tables include:

users

patients

appointments

consultations

medicines

inventory_logs

notifications

audit_logs

settings

Use proper primary keys.

Use foreign keys where appropriate.

Avoid duplicated data.

Note: this is the recommended table list. Always verify the actual current state of
schema.sql directly before assuming any table exists — a prior audit found the implemented
schema used a smaller, consolidated set (e.g. inventory_items instead of separate
medicines/inventory_logs, and schedule_logs handling both appointments and announcements via a
log_type column) and was missing dedicated appointments, audit_logs, and settings tables at the
time. Confirm current state before building against it.

---

# Naming Conventions

Python

snake_case

Example:

patient_records()

HTML IDs

camelCase

Example:

patientTable

CSS Classes

kebab-case

Example:

patient-card

Database Tables

plural

Example:

patients

Database Columns

snake_case

Example:

first_name

---

# Coding Standards

Write readable code.

Use meaningful variable names.

Avoid abbreviations.

Comment complex logic.

Keep functions small.

Avoid duplicated code.

Follow consistent indentation.

---

# Security Standards

Implement:

User authentication

Role-based authorization

Session management

Input validation

Password hashing

SQL injection protection

Escape user-generated content when displayed.

Every form carries a CSRF token. A sealed consultation's free text is stored encrypted (AES-256-GCM, key in
`.env`). Backups are encrypted `.idsbackup` files. Counts of fewer than 5 are folded or hidden for the
Administrator and the Barangay Official, and phone numbers are masked on the screens that show them to those
roles.

---

# Error Handling

Display user-friendly error messages.

Log technical errors internally.

Never expose sensitive information.

Validate all form inputs.

---

# File Organization

Recommended structure:

project/

app.py, config.py, schema.sql

routes/        one blueprint per role, plus shared context builders

models/        all data access

utils/         dates, roles, security, SMS, small counts, masking

templates/     Jinja templates; base.html is the shared shell

static/        vendored CSS, JS and fonts

database/      connection and first-run set-up

migrations/    one-time, idempotent schema migrations

tests/         automated suites (python tests/run_all.py)

README.md

---

# User Roles

Administrator (a Kagawad)

- Accounts, settings, Service Schedule, SMS broadcasts, inventory, Audit Logs and reports
- Patients as demographics and counts only; the Patient Queue is read-only

Doctor

- Diagnosis and treatment plan, sealing a consultation, declaring a death
- Everything Health Center Staff do on the clinical floor, and a list of visits Waiting for the Doctor

Health Center Staff

- Check-in (choosing the service), intake, patient records, dispensing, inventory

Barangay Official

- Community reports and SMS broadcasts; no patient records

Each role must only access authorized modules. The server enforces this on every route (`role_required`),
not only in the menus. Clinical data is for the care team only: the Doctor and Health Center Staff.

---

# Development Workflow

Requirements Analysis

↓

UI Design

↓

Frontend Development

↓

Backend Development

↓

Database Integration

↓

Testing

↓

Documentation

↓

Deployment

---

# AI Code Generation Rules

When generating code:

Follow Bootstrap.

Follow Flask.

Follow SQLite.

Do not invent new technologies.

Do not replace the architecture.

Generate complete code.

Include comments when appropriate.

Maintain consistency with the UI Design System.

---

# Code Quality Checklist

Every generated code should be:

Readable

Organized

Maintainable

Secure

Responsive

Reusable

Consistent

Beginner-friendly

---

# Future Scalability

The system should be designed so that future improvements can include:

Email notifications

Cloud database migration

SMS gateway integration

Role expansion

Patient history improvements

Analytics enhancements

These future improvements must not affect the current architecture.

---

# Final Development Principle

The project prioritizes clarity, maintainability, and consistency over unnecessary complexity.

Every implementation decision should support the approved capstone proposal and remain achievable by the project team using Flask, Bootstrap 5, and SQLite.
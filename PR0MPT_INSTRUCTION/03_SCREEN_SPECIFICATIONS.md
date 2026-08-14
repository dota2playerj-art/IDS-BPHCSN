# IDS-BPHCSN SCREEN SPECIFICATIONS

Version: 1.0

---

# Purpose

This document defines every screen of the IDS-BPHCSN system.

Each screen specification includes:

- Purpose
- Authorized User
- Layout
- Components
- Navigation
- Actions
- Validation
- Backend Notes

The Login Page and Administrator Dashboard are the official visual references for the entire system.

Every screen must reuse the same design system.

---

# SCREEN 01

## Login Page

Purpose

Authenticate authorized users.

Authorized Users

- Administrator
- Health Center Staff
- Barangay Official

Components

- Logo
- System Title
- Username
- Password
- Show Password
- Remember Me
- Login Button

Behavior

Authenticate user.

Redirect based on role.

Validation

Required fields.

Invalid credentials.

Locked session after multiple failed attempts.

Navigation

Successful Login

↓

Dashboard

---

# SCREEN 02

## Administrator Dashboard

Purpose

Provide a complete overview of the health center.

Components

Sidebar

Header

Dashboard Cards

Recent Consultations

Today's Appointments

Medicine Inventory Summary

Quick Actions

Notifications

Activity Timeline

System Status

Reports Preview

Actions

Open any module.

View notifications.

Generate reports.

Search patient.

---

# SCREEN 03

## Patient Records

Purpose

Manage all registered patients.

Components

Search Bar

Advanced Filter

Patient Table

Pagination

Add Patient Button

Export Button

Actions Column

Table Columns

Patient ID

Full Name

Age

Gender

Address

Contact Number

Last Visit

Status

Actions

Search

Filter

Sort

View

Edit

Archive

Print

Backend Notes

Retrieve data from SQLite.

---

# SCREEN 04

## Register Patient

Purpose

Register a new patient.

Sections

Personal Information

Emergency Contact

Medical Information

Buttons

Save

Cancel

Reset

Fields

Patient ID

First Name

Middle Name

Last Name

Birthdate

Age

Gender

Civil Status

Address

Contact Number

Blood Type

Medical Conditions

Allergies

Validation

Required fields.

Duplicate patient detection.

---

# SCREEN 05

## Patient Profile

Purpose

Display complete patient information.

Tabs

Personal Information

Medical History

Consultation History

Medicine History

Vaccination Records

Appointment History

Buttons

Edit

Print

Back

---

# SCREEN 06

## Medicine Inventory

Purpose

Manage medicines.

Components

Search

Filter

Medicine Table

Low Stock Widget

Expiration Widget

Buttons

Add Medicine

Update Stock

Print Inventory

Columns

Medicine Name

Category

Quantity

Expiration Date

Supplier

Status

---

# SCREEN 07

## Add/Edit Medicine

Purpose

Manage medicine details.

Fields

Medicine Name

Generic Name

Category

Quantity

Unit

Expiration Date

Supplier

Storage Location

Buttons

Save

Update

Cancel

Validation

No negative quantity.

Expiration date required.

---

# SCREEN 08

## Appointment Scheduling

Purpose

Manage appointments.

Components

Calendar

Upcoming Appointments

Walk-in Queue

Today's Schedule

Buttons

Schedule

Reschedule

Cancel

Complete

Fields

Patient

Date

Time

Purpose

Assigned Staff

Status

---

# SCREEN 09

## Community Notifications

Purpose

Send announcements.

Components

Recipient Selection

Message Editor

SMS Preview

Character Counter

Delivery Status

Buttons

Send

Save Draft

Schedule

History

Recipients

Residents

Senior Citizens

Pregnant Women

Parents

Health Workers

Entire Barangay

---

# SCREEN 10

## Reports & Analytics

Purpose

Generate reports.

Charts

Monthly Consultations

Medicine Usage

Patient Registration

Appointment Statistics

Tables

Top Diseases

Low Stock Medicines

Vaccination Summary

Buttons

Generate

Print

Export PDF

Export Excel

---

# SCREEN 11

## User Management

Purpose

Manage system users.

Columns

Name

Role

Username

Status

Last Login

Buttons

Add User

Reset Password

Disable

Enable

Delete

Roles

Administrator

Health Center Staff

Barangay Official

---

# SCREEN 12

## Audit Logs

Purpose

Monitor activities.

Columns

Date

Time

User

Action

Module

IP Address

Status

Filters

User

Date

Action

---

# SCREEN 13

## Settings

Purpose

Configure the system.

Sections

General Settings

Health Center Information

SMS Settings

Backup

Restore

Security

Account

Buttons

Save

Reset

Backup Database

Restore Database

---

# SCREEN 14

## Health Center Staff Dashboard

Purpose

Dashboard for healthcare workers.

Widgets

Today's Patients

Appointments

Medicine Requests

Recent Consultations

Notifications

Quick Actions

No access to

User Management

Settings

Audit Logs

---

# SCREEN 15

## Barangay Official Dashboard

Purpose

View community health information.

Widgets

Health Announcements

Community Reports

Vaccination Campaigns

Upcoming Programs

Statistics

Quick Actions

View Reports

View Notifications

No access to

Patient Medical Records

User Management

Settings

Inventory Management

---

# Global Navigation Rules

Login

↓

Role Verification

↓

Dashboard

↓

Module

↓

Back to Dashboard

Logout available on every page.

---

# Common Components

Every screen must reuse

Sidebar

Header

Cards

Buttons

Tables

Typography

Colors

Spacing

Icons

Status Badges

---

# Data Standards

Always use

Realistic Filipino names

Realistic medicine names

Realistic addresses

Realistic consultation records

Realistic healthcare statistics

Never use

Lorem Ipsum

John Doe

Sample Data

Placeholder Text

---

# Backend Integration Notes

Every screen must be designed for future integration with

Flask

Bootstrap

SQLite

Avoid designs that require unsupported frontend frameworks.

---

# Final Principle

Every screen must look like it belongs to one complete enterprise healthcare management system.

Consistency is more important than visual variety.
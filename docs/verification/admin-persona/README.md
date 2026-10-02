# admin-persona

Verification of the Administrator persona correction — "Dr. Joshua Reyes", a
placeholder invented in `06_DESIGN_CONTENT_LIBRARY.md`, replaced by the person
who actually holds the account: **the Administrator (Health Committee Chair)**, a Kagawad chairing the
barangay's Health Committee.

## What changed, and what deliberately did not

| | |
| --- | --- |
| Stored `users.full_name` | `the Administrator (Health Committee Chair)` |
| Profile chip / sidebar subtitle | `Kagawad, Health Committee` |
| Avatar initials | `AA` |
| **Username** | **`admin`, unchanged** |
| **Password** | **unchanged — `password_hash` verified byte-for-byte** |
| **System role** | **`Admin` / "Administrator", unchanged** |
| **Audit history** | **unchanged — 506 entries still name the old persona** |

The system role and the person's office are two different things and are stored
in two different places. `Admin` is what the schema's CHECK constraint allows,
what `role_required()` compares, and what the Role column and My Account show.
`Kagawad, Health Committee` is only the subtitle under the name in the profile
chip, which describes the person. Nothing about permissions moved.

Audit entries written before the correction were **not** rewritten. They say
what the system recorded at the time, which is what an audit trail is for. Those
rows read a little oddly beside the corrected name in the User column, which is
joined live from `users` — that is the honest result, not a defect.

## Found already done, on inspection

`models/users.py` (the seeded name), `utils/context.py` (chip name, subtitle,
initials), `routes/audit_views.py` (initials), `templates/settings.html`
("Head Physician / Administrator" → "Administrator", since the box shows
whoever is signed in rather than a stored head physician),
`06_DESIGN_CONTENT_LIBRARY.md`, and `migrate_correct_admin_persona.py` — which
had **already been run** against the live database. All correct.

## Found missing, and completed

**1. `routes/user_views.py::_initials()` — the roster drew a different answer.**

The rule that skips an honorific before taking initials existed in **three**
copies. Two were updated with `"kagawad"`; the third, User Management's, was
not — and it had never skipped titles at all. One account therefore rendered

```
AA   in the header, on every screen
AA   on every audit entry it had ever written
KA   on the User Management roster
```

on screens an administrator reads side by side, with nothing in any of the three
files hinting the other two existed. The same copy had disagreed before the
correction too (`DR` there against `JR` everywhere else); the persona change only
made it visible.

Fixed at the cause: the rule is now **`utils/names.py::initials()`**, once, and
all three call it. The `empty` return stays a per-caller choice — the sidebar
renders a blank circle for a signed-out visitor, the trail and the roster render
`?`, and both are right where they are.

`"Hon."` was deliberately **not** added to the title list. No account carries it,
and adding a title on speculation would silently change what an account nobody
has created yet renders as.

**2. The migration's docstring claimed a figure it had not counted.**

It said 508 audit entries name the old persona. Counted against the database as
it stood before the migration: **506**. Corrected, with a note saying the number
is now counted rather than remembered — the script prints it on every run.

## Evidence

- **94-check persona suite**, against a throwaway copy: the stored row (name
  corrected, username / role / active flag / password hash all unchanged, 506
  historical entries intact); **all 12 Administrator HTML screens rendered** and
  each asserted to carry the name, the subtitle and an `AA` avatar, with the
  placeholder absent and no "Head Physician" label anywhere; the roster asserted
  to draw `AA` and **not** `KA`; Audit Logs asserted to show the corrected name
  in the live-joined User column *while* still carrying old entries in their
  original wording; Settings' box; My Account showing the person's name and the
  **system** role; and both other roles' chips and sidebar cards unaffected.
- **Authentication and the password features**: the Administrator signs in with
  its unchanged credentials, a wrong password is still refused, the self-service
  change still saves and the account signs in with the new password with the
  persona intact, and Reset Password and Edit User still work — Edit User still
  refusing to rename a username.
- **The my-account suite re-run: 338 checks, 0 failures.**
- **Route × role matrix: byte-identical** to the post-my-account snapshot —
  97 rules, 212 pairs, zero 5xx.
- `python app.py` starts clean.

## The migration, exercised on both paths

Run against scratch copies before being run for real:

- **Apply**, against `app.db.PRETASK_BACKUP_admin-persona_20260904_042833`:
  `"Dr. Joshua Reyes" -> "the Administrator (Health Committee Chair)"`, then VERIFICATION PASSED —
  username, role and `password_hash` unchanged, 506 audit entries untouched,
  every other column of all 4 accounts byte-for-byte unchanged.
- **Idempotent re-run** on the same file: `already ... nothing to do`, same
  verification.
- **Against the live database**: reports `already ... nothing to do`, and the
  file is **byte-identical** afterwards to
  `app.db.PRETASK_BACKUP_persona-finish_20260904_114516`, taken before the run.

## No images

Same rule as `add-user/` and `form-redisplay/`: the screens involved are an
account roster and an audit trail. The browser pass ran against a throwaway copy
served on port 5056, and the real database was confirmed unchanged by SHA-256
before and after.

## Reproducing it

1. `python migrate_correct_admin_persona.py` — on a database already corrected
   it prints `already ... nothing to do` and writes nothing.
2. `python app.py`, and sign in as `admin` with that computer's password — the
   credentials are unchanged by any of this.
3. The header chip, the sidebar card, **User Management's roster**, Audit Logs
   and My Account must all show `AA`, `the Administrator (Health Committee Chair)`, and the system
   role `Admin` / `Administrator`. The chip's subtitle, and only it, reads
   `Kagawad, Health Committee`.
4. Scroll Audit Logs back to entries written before the correction. They still
   say "Dr. Joshua Reyes" inside their own sentences, and must.

# Task 7 — final clean-up: triage of the open issues

Every issue in `PROJECT_STATUS.md` that was not Done or Accepted before this task, and what Task 7 does with it.

| Issue | What | Decision | Where |
|---|---|---|---|
| M7 | Settings has disabled panes and display-only parts | FIX | Step 3 (remove disabled panes; keep the read-only rules) |
| M8 | No Semaphore key, SMS is simulated | FIX the display; the key itself is a pre-defense action | Step 3 (SMS mode line, `.env.example`), checklist |
| M9 | Three project names | FIX | Step 2 |
| M10 | Wordy tooltips and audit text | FIX | Step 5 |
| M12 | No git remote push | PRE-DEFENSE ACTION (the team pushes) | checklist |
| M14 | Official's Notifications placeholder | FIX | Step 3 |
| M18, M19, M22, M32 | Old backups, a git bundle and old session folders outside the repo | PRE-DEFENSE ACTION (the team deletes or locks them away; not in the repo) | stays open |
| M20 | Anonymous refused requests leave no audit row | ACCEPT: an audit row must name an account, a decision already made | tracker |
| M23 | Sealing key on the same PC | ACCEPT: BitLocker is the control, a decision already made | tracker |
| M31 | Fresh-install Administrator named after a real person | FIX | Step 6 |
| M35 | Service list not confirmed with the health center | INTERVIEW | tracker |
| L3 | "Booked" column on the queue | FIX | Step 3 |
| L4 | Booking-era wording in Community Reports | FIX | Step 3 |
| L6 | PhilHealth No. always "Not recorded" | FIX | Step 3 |
| L7 | Stale comments (Reschedule/Cancel, slot generator, Medicine only) | FIX | Step 3 |
| L10 | Very long file-top comments | FIX | Step 6 |
| L11 | Second IPV dose | INTERVIEW | tracker |
| L12 | Roadmap says 89 endpoints, three roles | FIX | Step 7 |
| L14 | Wrong note in `migrate_add_consultation_columns.py` | FIX | Step 6 |
| L15 | Missing "must change password" sentence | FIX | Step 4 |
| L16 | GET /logout shows a 405 page | FIX | Step 4 |
| L17 | Keep-alive ignores maintenance mode | FIX | Step 4 |
| L19 | Sealed visit keeps dates, vitals, doses readable | ACCEPT: by design, numbers and dates, not free text | tracker |
| L21 | Fixture phone numbers look real | FIX | Step 9 (closest: tests) |
| L22 | Wrong docstring about the Administrator | FIX | Step 3 (stale comments) |
| L23 | Seal audit entry in its own transaction | FIX | Step 4 (closest: small bugs) |
| L29 | Repair-only migrations for the archived data | FIX (delete) | Step 6 |
| L30 | The demo-data suite is slow | FIX | Step 8 (`--quick`) |

Also waiting for the health center interview: the empty Service Schedule.

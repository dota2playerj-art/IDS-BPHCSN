# Schedule Appointment — the empty scroll region below the last field

## What was reported

The Schedule Appointment dialog on Appointment Scheduling showed only the
**Note** field, followed by a large empty scrollable gap before Cancel / Book
Appointment. Every field above Note — patient picker, Date, Time, Reason /
Service, Assign to — appeared not to render.

## What was actually wrong

Nothing failed to render. The server sends the whole form on every request; it
was confirmed in the response body before a browser was opened. The dialog had
grown roughly **670px of empty scrollable area below the form**, and any scroll
of the dialog body — a wheel, or the browser bringing a field into view after a
rejected submit — landed the operator in that emptiness with only the last field
still on screen.

The cause is one missing CSS declaration:

```css
.patient-option{display:block; ...}          /* not positioned */
.patient-option input{position:absolute; ...} /* the hidden radio */
```

The patient rows are label/radio pairs: the radio is `position:absolute;
opacity:0` so the whole visible row is drawn by `.po-body`. An absolutely
positioned box is laid out against its nearest **positioned** ancestor. Neither
`.patient-option` nor `.patient-pick` was positioned, so the search went further
up and found Bootstrap's `.modal-body`, which carries `position: relative` in the
framework's own stylesheet.

The consequence is that the radios were never inside the scrolling patient list
at all. `.patient-pick` clips its content at `max-height:280px`, but it cannot
clip a box whose containing block is outside it. All 22 radios were laid out
against `.modal-body` at their full unclipped stacking length and contributed
every pixel of it to that element's scroll height. Measured in the browser:

| dialog | `.modal-body` scrollHeight, broken | real content height |
|---|---|---|
| Schedule Appointment | 1542px | 871px |
| Check In Patient | 1573px | 666px (no scroll at all) |

The radios are `opacity:0`, so the defect had nothing to show for itself except
blank space — which is exactly how it was reported.

The Check In Patient dialog is built from the same `.patient-pick` /
`.patient-option` markup and carried the identical defect. It was less visible
there only because that dialog is shorter and fitted without scrolling once the
phantom height was gone.

## The fix

`position:relative` on `.patient-option`, in
`templates/appointment_scheduling.html`. Each row becomes its own containing
block, the radio stays inside the row it belongs to, and the list clips it like
any other content. One line, both dialogs, no markup or script change.

After the fix the Schedule Appointment body's scrollHeight is 871px against a
form ending at 855px — the 16px remainder is `.modal-body`'s own bottom padding,
which is the entire gap that is supposed to be there.

## What was verified, in a browser

- Dialog opened fresh from the New Appointment button: patient search, patient
  list, Date, Time, Reason / Service, Assign to and Note all present, in order,
  spacing intentional. Scrolled to the very bottom: the last hint line sits
  16px above the footer, with no empty region.
- Patient search still filters the list ("Grace" → Grace Ilagan alone), the row
  still selects, and the Time hint still updates from the chosen date
  ("Nothing booked that day yet."), so the hidden radio is still the control it
  always was — it is only positioned differently.
- **A real appointment was booked through the dialog end to end.** Grace Ilagan
  (PAT-007), Prenatal Check-up, Sep 10 2026 at 10:30. The page came back with
  the confirmation sentence and the SMS offer for APT-00080, the booking
  appeared under Upcoming Reminders, and the row was confirmed in the database
  with status `Scheduled` and the note intact.
- **The form-redisplay path was re-checked**, because it is the one that made
  the gap most visible. Submitted with everything blank: the dialog reopens on
  the error banner, all four field errors show against the right fields, the
  typed note is kept, and the fully scrolled body again ends flush.
- Check In Patient dialog opened and confirmed to have no scroll overflow at all
  (scrollHeight == clientHeight).
- Route × role matrix snapshotted before and after across 210 route/role pairs
  (Admin, Health Center Staff, Barangay Official, anonymous). **Identical.**
- `python app.py` starts clean.

The booking test ran against the live database with a copy taken first; the copy
was restored afterwards and `app.db` is byte-identical to its pre-test state
(md5 `19aaf0fbbfa339914d3d2252677883f6`, max appointment id back to 79). The
verification appointment does not survive in the record.

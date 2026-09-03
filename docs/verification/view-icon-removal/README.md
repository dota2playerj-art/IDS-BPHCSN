# View icon removal — User Management

Verification that the View icon and its Actions column are gone from User
Management's roster, that nothing was orphaned by their removal, and that the
one thing the icon did carry beyond duplication — keyboard access to an account —
survives the deletion.

Like the passes beside it, this one retained **no images**. Its subject is the
roster of every account that can sign in to the system; a picture of that screen
is a list of every way into it, which is the reason `add-user/` keeps none
either. The whole run was driven against a throwaway copy of `app.db` on port
5077, and the real database was confirmed byte-identical to
`app.db.PRETASK_BACKUP_view-icon-removal_20260904_034857` by SHA-256 afterwards.

## What was removed, and why it was redundant rather than merely unused

The icon was not broken. It called `selectUser(this.closest('tr'))` — the *same
function*, not a similar one — that the row's own `onclick` calls. Clicking the
icon and clicking anywhere else in the same row produced identical results: the
row highlighted, and that account's detail panel un-hidden beside the table. The
panel it opened was, for the first row, already open on arrival.

Nor was there anything for a View to show. Every column of `users` except
`password_hash` is already on that panel — username, email, phone, role, status
and the exact `created_at` through `display_timestamp` — beside Last Login, which
is derived from the audit trail, and the live list of screens the role can open.
Medicine Inventory's View exists because eight stored fields had no reader
outside the form that could also change them. User Management has no such field.

Three things went:

- the `<button class="action-icon">` and the `<td>` wrapping it,
- the `<th style="text-align:right;">Actions</th>` above it, since it was the
  only occupant of that column and a header over nothing reads as a control that
  failed to render,
- the `.action-icon` and `.action-icon:hover` rules, which that button was the
  sole user of in this template. Left behind they would have been dead CSS
  describing a control that no longer exists.

The table now matches Audit Logs', which has had this shape all along:
selectable rows, a detail panel beside them, and no Actions column.

## The regression the removal would otherwise have introduced

The icon was a `<button>`, so Tab reached it and Enter pressed it. That was
incidental to its purpose and it was the only keyboard route to selecting an
account: every panel but the first carries `hidden`, hidden content takes no
focus, and Edit User, Reset Password and Deactivate all live inside those panels.
Deleting the button alone would have left an Administrator working from the
keyboard able to administer the first account on the roster and no other.

So the affordance moved onto the row rather than being deleted with the duplicate
control: `tabindex="0"` makes each row focusable, a `keydown` handler activates it
on Enter or Space, `aria-controls`/`aria-expanded` name the panel it opens and say
whether that panel is the one showing, and a `:focus-visible` outline makes the
focused row visible — these rows carry no outline of their own. `selectUser()`
now keeps `aria-expanded` in step, since the attribute is rendered once on the
server for whichever row starts selected. Space is prevented from its default
page-scroll; Enter has no default here and is left alone.

The `<tr>` stays a `<tr>`. `role="button"` would also have made it focusable and
would have stopped a screen reader announcing it as a table row at all.

## The automated suite

**202 checks, 0 failures**, in one run against a scratch copy:

- **Removal.** No `action-icon` anywhere in the rendered page, no `visibility`
  glyph, no "View details" label, no `Actions` header.
- **Table structure, measured rather than eyeballed.** Exactly 5 header cells,
  reading User / Role / Contact / Status / Last Login; one row per account; every
  row carrying exactly 5 cells; no empty cell anywhere in the table; no `colspan`
  left behind.
- **Row-click behaviour intact.** `selectUser` still defined, every row still
  calling it on click, every row focusable, every row naming a panel that exists,
  first row rendered expanded and the rest collapsed, keydown handler emitted,
  focus ring styled.
- **Panels untouched.** One per account, the first visible and the rest hidden,
  and the set of panels the rows point at equal to the set that exists.
- **The four real actions untouched.** Add User, and an Edit and Reset dialog per
  account, all still rendered; the status dialog and the last-Administrator
  wording still present.
- **Role isolation.** Health Center Staff and Barangay Official are still refused
  User Management, checked through their own login routes against the running
  application.
- **No regressions.** A sweep rendering every argument-free GET route under all
  three roles — 150 requests — returned no 5xx.

Route × role matrix snapshotted before and after: **95 rules, identical, zero
drift.** `python app.py` starts clean.

## The live browser pass

Driven as the Administrator, the **only** role that can open this screen — the
task asked for both roles that can reach it and there is one, since `2208e51`
closed User Management to everyone else. Staff and Official refusal is covered in
the suite above against the same running application rather than clicked through.

What was confirmed in the live DOM and on screen:

- The table renders five columns with **no trailing gap**. Measured from the
  page: the table's right edge and its container's right edge are the same pixel
  (1061), Last Login runs 894→1061, and every body cell's left edge matches its
  header's exactly. The freed width was absorbed by the remaining columns rather
  than leaving a stub where the Actions column had been.
- Clicking a row still selects it and swaps the panel — clicking Arnel Manalastas's
  row moved the panel from the Administrator to `bhwmanalastas`, with that account's
  own creation date and its own shorter list of reachable screens.
- **Enter on a focused row** selected it and swapped the panel to Barangay
  Official. **Space** selected Arnel Manalastas's row and the page did **not**
  scroll (`window.scrollY` 500 before and after).
- The teal focus ring is plainly visible on a keyboard-focused row, and is
  distinguishable from the green selected-row background — both were on screen at
  once, on different rows, and read as two different things.
- **Edit User opened on the right account** — `bhwmanalastas`, chosen entirely by
  keyboard — with the name and role filled in and the username locked, proving the
  whole keyboard chain reaches an account's real controls.

## Reproducing it

1. Copy `app.db` somewhere scratch and point `app.config["DATABASE"]` at the
   copy, then serve it on a spare port.
2. Sign in as the Administrator and open User Management.
3. Confirm the table has five columns ending at Last Login, with no Actions
   column and no empty space where one was.
4. Click a row other than the first: it highlights and the panel beside it
   changes to that account.
5. Press Tab until a row takes focus — the teal outline shows which — then press
   Enter, and then Space on another row. Each selects the focused row, and Space
   must not scroll the page.
6. With an account chosen by keyboard alone, open Edit User from the panel and
   confirm it names that account.

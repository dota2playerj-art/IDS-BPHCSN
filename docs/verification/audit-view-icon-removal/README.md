# View icon removal — Audit Logs

Verification that the View icon and its Actions column are gone from the Audit
Logs trail, that nothing was orphaned by their removal, and that the one thing
the icon did carry beyond duplication — keyboard access to an entry — survives
the deletion.

This is the second half of the removal `1d48f1c` began on User Management, and
it is the same removal for the same reason. The screen it leaves behind is the
shape that commit's message said this one had had all along, which turned out to
be true of everything except the Actions column itself.

Like the passes beside it, this one retained **no images** in version control.
Its subject is the activity trail: every row names an account, a role and an IP
address, and the panel beside them prints the before-and-after values of edited
patient records. A picture of that screen is a picture of those records. The
whole run was driven against throwaway copies of `app.db`, and the real database
was confirmed byte-identical to
`app.db.PRETASK_BACKUP_audit-view-icon_20260904_165447` by SHA-256 afterwards
(`0b6af2098bd40ef9da212379b9c1cc4496aa3934fbaf673ddbbb1c469598f0bb`).

## What was removed, and why it was redundant rather than merely unused

The icon was not broken, and it was not unwired either — which is the detail that
took a moment to see. It carried **no handler of its own**. It sat inside a
`<tr onclick="selectRow(this)">`, so a click on it bubbled to that handler and
selected the row. It therefore did exactly what clicking anywhere else in the
same row did, one pixel away from itself, and on the first row it re-opened a
panel that was already open on arrival. User Management's icon reached the same
end by calling `selectUser()` explicitly; this one reached it by falling through.

Nor was there anything for a View to show. Every column of `audit_logs` is
already on the panel beside the table — the full timestamp, the user and their
role, the module, the IP address, the entry number, and `details`, the one column
that is **not** in the table at all, expanded into a "What happened" summary and
before/after boxes per changed field. The panel is a superset of the row, not a
subset of it. Nothing in the row is truncated either: the only `white-space:
nowrap` rules in the template are on filter chips, headers, module pills and
status badges, and Activity is a plain `<td>` with no ellipsis. Medicine
Inventory's View earns its place because eight stored fields there have no reader
outside the form that can also change them. No field here is in that position.

Three things went:

- the `<button class="action-icon">` and the `<td>` wrapping it,
- the `<th style="text-align:right;">Actions</th>` above it, since it was the
  only occupant of that column and a header over nothing reads as a control that
  failed to render,
- the `.action-icon` and `.action-icon:hover` rules, which that button was the
  sole user of in this template. Left behind they would have been dead CSS
  describing a control that no longer exists.

The two empty-state rows — `#auditEmpty` and `#auditNoMatch` — dropped from
`colspan="7"` to `colspan="6"`. A colspan left at 7 does not fail loudly; it
quietly makes the empty message wider than the table it sits in, so both were
checked against the rendered header count rather than against the number 6.

## The regression the removal would otherwise have introduced

The icon was a `<button>`, so Tab reached it and Enter pressed it, and the click
that raised fell through to the row's handler. That was incidental to its purpose
and it was the only keyboard route to choosing an entry: every panel but the
first carries `hidden`, and hidden content takes no focus.

Audit Logs is a reading screen — its panels hold no controls, unlike User
Management's — so what would have been lost is not the ability to act but the
ability to choose what to read. A keyboard-only Administrator would have been
able to read the first entry's before/after detail and no other, on the one
screen in the system whose purpose is accountability. That is a loss of function,
not of decoration.

So the affordance moved onto the row rather than being deleted with the duplicate
control: `tabindex="0"` makes each row focusable, a `keydown` handler activates it
on Enter or Space, `aria-controls`/`aria-expanded` name the panel it opens and say
whether that panel is the one showing, and a `:focus-visible` outline makes the
focused row visible — these rows carry no outline of their own. The panels gained
an `id` for `aria-controls` to point at; they had only ever been addressed by
`data-detail`. `selectRow()` now keeps `aria-expanded` in step, since the
attribute is rendered once on the server for whichever row starts selected. Space
is prevented from its default page-scroll; Enter has no default here and is left
alone.

The `<tr>` stays a `<tr>`. `role="button"` would have made it focusable too and
would have stopped a screen reader announcing it as a table row at all, which is
the one thing about it worth announcing.

## What was checked

**834 checks, 0 failures**, against a throwaway copy of the database:

- **The icon is gone**, in the template source and in the rendered HTML: no
  `action-icon` class, no `visibility` glyph, no `View entry` label, no `Actions`
  header, no `colspan="7"` anywhere.
- **The table is square.** Six header cells, in the expected order, and every one
  of the 100 body rows carrying exactly six cells, none of them empty, none of
  them a leftover colspan.
- **Every row is a control.** All focusable, all carrying `onclick`, all naming
  an `aria-controls` target that exists, and exactly one — the first — starting
  with `aria-expanded="true"`.
- **Panels untouched.** One per entry, the first visible and the rest hidden, the
  set of panel ids equal to the set the rows point at, and each panel's `id`
  agreeing with its own `data-detail`.
- **The detail still carries what the row does not** — the Field Changes and
  What happened sections are still rendered.
- **The rest of the screen is untouched** — search box, filter panel and both
  exports still present.
- **Role isolation.** Health Center Staff and Barangay Official are still refused
  Audit Logs, checked through their own login routes.

**Both empty states rendered for real** — 9 further checks, 0 failures — by
deleting every row from a second throwaway copy after signing in. The
"No activity recorded yet" row and the "No entry matches that search" row each
render, exactly two `colspan` cells exist on the page, both read 6, and both were
compared against the *rendered* header count rather than a hardcoded number.

Route × role matrix snapshotted before and after: **97 rules, identical**, with
every parameterless GET returning the same status code under all three roles and
each landing on the same dashboard. `python app.py` starts clean and serves
`/` 302 and `/login` 200.

## The live browser pass

Driven as the Administrator, the only role that can open this screen since
`2208e51`. Staff and Official refusal is covered in the suite above against the
same running application rather than clicked through.

The session was established without typing a password into the sign-in form: a
throwaway runner outside the application set the session keys directly and served
the real app against a copy of the database. No application code was involved in
that, and none was changed for it.

What was confirmed in the live DOM and on screen:

- The table renders six columns with **no trailing gap**. Measured from the page:
  the table's right edge, its scroll container's right edge and the card's content
  edge are all the same pixel (1061); the last header cell and the last body cell
  both end at 1061; and `scrollWidth - clientWidth` is 0, so nothing is being
  hidden by a scrollbar. The freed width was absorbed by the remaining columns
  rather than leaving a stub where Actions had been.
- Clicking a row still selects it and swaps the panel — clicking the third row
  moved the panel to entry #1147, "Downloaded a database backup".
- **Enter on a focused row** selected it and swapped the panel; **Space** on
  another selected that one, and its `defaultPrevented` was true, so the page did
  not scroll. Throughout, exactly one row was `selected`, exactly one carried
  `aria-expanded="true"`, and exactly one panel was visible — the three never
  disagreed.
- **Enter in the search box did not hijack the selection**, confirming the
  handler ignores targets that are not rows.
- Tab reached a row for real — not programmatically — from the search box:
  `:focus-visible` matched and the teal ring (`rgb(15,110,86)`) was plainly
  visible around the full six-column width of the row, flush to the card's right
  edge. Pressing Enter there turned the row green and moved the panel to entry
  #1149; the focus ring stayed legible against the selected background.
- The **no-match empty state** renders centred across the whole six-column width,
  under the full header rather than short of it.

## Reproducing it

1. Copy `app.db` somewhere scratch and point `app.config["DATABASE"]` at the
   copy, then serve it on a spare port.
2. Sign in as the Administrator and open Audit Logs.
3. Confirm the table has six columns ending at Status, with no Actions column and
   no empty space where one was.
4. Click a row other than the first: it highlights and the panel beside it changes
   to that entry, including its before/after boxes.
5. Press Tab until a row takes focus — the teal outline shows which — then press
   Enter, and then Space on another row. Each selects the focused row, and Space
   must not scroll the page.
6. Type something that matches nothing into the search box and confirm the
   "No entry matches that search" row spans the whole table.
7. For the other empty state, delete every row from the scratch copy's
   `audit_logs` after signing in and reload the screen.

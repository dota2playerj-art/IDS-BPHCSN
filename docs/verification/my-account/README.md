# my-account

Verification of **My Account** — the signed-in person reading their own account
details and changing their own password, reached from the profile chip in the
header by all three roles.

## What was built, and the boundary it was held to

Two things, and deliberately nothing else:

1. **Own account details, read-only** — full name, role, username, each printed
   with a line saying who *can* change it and why the reader cannot.
2. **Change Password** — current password, new password, confirm new password.
   The current password is verified against the stored hash before anything is
   written; the new one goes through the same `check_password_strength()` that
   Add User and the Administrator's Reset Password already use.

**Not built, on purpose:** no profile photograph, no editable name or role from
this panel (both stay Admin-only through Edit User), no notification
preferences, no personalisation of any kind. `users.email` and `users.phone`
are still never written by anything. The suite asserts these absences rather
than assuming them — `type="file"`, `name="full_name"`, `name="role"` and
`name="username"` are each checked to be absent from the rendered page for
every role.

## No images, for the reason `add-user/` gives

This screen's subject is a credential. A picture of it is an account's identity
beside a password form. The whole pass ran against **throwaway copies** of
`app.db` — the automated suite against one, the live browser run against another
served on port 5056 — so creating changes, signing in and out left nothing in
the real database. Confirmed afterwards by SHA-256 over the whole file against
`app.db.PRETASK_BACKUP_my-account_20260904_110941`: **byte-identical**.

## The automated suite

**338 checks, 0 failures**, in one end-to-end run against a scratch copy. In
outline:

- **The panel, for each of the three roles.** Reachable from the profile chip
  on an *ordinary* screen (the `href="/account"` menu item is in the header of
  each role's dashboard, not only of My Account itself); renders at 200; shows
  that role's own stored name, role label and username; carries the three
  password boxes and posts them to `/account/password`; carries no editable
  name/role/username field, no file input, and no account id. `GET` on the
  write endpoint is 405.

- **Every refusal, one submit each, for each role.** A wrong current password, a
  new password that is too short, one using only one character kind, one
  containing the account's own username, a common password, and a mismatched
  confirmation. Each is asserted on the rendered response to come back at **200
  rather than a redirect**, on the My Account page itself, with the message
  beside the right box, `is-invalid` on that box, and the red "Your password was
  not changed" banner counting the fields. A blank submit reports all three
  boxes at once; a submit that is wrong in two ways reports both.

- **What a refusal leaves behind.** After every one of them: the stored hash is
  untouched, the old password still verifies, and **no audit row was written** —
  the count is compared against the one taken immediately after the sign-in that
  opened the session. Every submitted value is searched for in the returned
  HTML and is absent, so no password is written back into the page.

- **A real change, and the login that proves it.** For each role: the change
  redirects to `/account` and flashes; the stored hash changes; the **new**
  password verifies against it and the **old** one no longer does; username,
  full name, role, `is_active` and `created_at` are unchanged; neither password
  appears in plaintext in any column of the row. Then the login form is used:
  the new password signs in and reaches that role's dashboard, and the old one
  is refused and is audited as a refused sign-in. The session that made the
  change stays open — the same client reaches its own screens without signing in
  again.

- **The audit entry.** Exactly one `Changed own account password` row per
  change, attributed to the **holder** (`user_id` is the account itself), filed
  under **Authentication**, naming the account, the person and the stored role,
  saying the current password was verified against the stored hash and that this
  was done by the holder "and not on their behalf", and pointing at the
  administrator's reset as a different entry. Neither password is in it — nor
  anywhere in the whole `audit_logs` table, asserted by searching every
  `details` value for all six credentials used in the run.

- **The guard, and forged posts.** Anonymous `GET /account` and anonymous
  `POST /account/password` both redirect to the login form and change nothing. A
  signed-in account POSTing the *Administrator's* `user_id` alongside its own
  passwords changes only its own row — the Administrator's hash is untouched and
  still verifies its own password — because the route reads no account from the
  request. A deactivated account is refused at My Account like every other
  guarded screen, and during a maintenance window a live non-Administrator
  session gets 503 there while the Administrator still gets 200.

- **Spaces are not trimmed.** The rule counts "a symbol or a space" as one of
  its four character kinds, so a password that begins and ends with a space is
  accepted, stored exactly as typed, refuses its own trimmed form, and signs in
  at the login form.

- **Re-setting the same password.** Allowed, because nothing in this system
  remembers a previous password and Settings says so out loud. It is not
  reported as a change that took the old one away: the flash says the credential
  is unchanged, and the audit entry says so too rather than claiming "the
  previous password stopped working".

- **No interference with the Administrator's Reset Password.** The Admin reset
  still saves, still flashes its own message, still writes
  `Reset user account password` under **User Management** attributed to the
  administrator, and writes no self-change entry. The reset account then signs
  in with what the administrator set and changes it themselves — the two paths
  compose, and the trail shows which was which.

- **No regressions.** Add User still redisplays a weak password at 200 with the
  name and username kept and its dialog reopened inside `DOMContentLoaded`, and
  still creates a real account. A successful sign-in and a refused one are still
  audited. An account created *after* this feature existed can use it. Audit
  Logs renders, with the new phrase in it.

## Route × role matrix

Snapshotted before and after — every URL rule with its methods and the roles its
decorator admits, plus a live sweep of every parameterless GET route as each of
the three roles and as an anonymous visitor.

The diff is **exactly** the two new rules and the four sweep rows they produce:

```
> /account            GET   auth.my_account           login_required
> /account/password   POST  auth.change_own_password  login_required
> /account  anonymous  302  /login
> /account  admin      200
> /account  staff      200
> /account  official   200
```

95 rules → 97; 208 sweep pairs → 212; **zero 5xx**, and the other 208 pairs are
byte-identical.

## The live browser pass

Driven against a scratch copy served on port 5056, in a real Chrome window, as
each of the three roles in turn.

| Role | What was done, and what was seen |
| --- | --- |
| Health Center Staff | Clicked the profile circle: the menu now holds **My Account** above Logout. Opened it; the account details read *Health Center Staff / Health Center Staff / staff*. Submitted a **wrong current password** — the page came straight back with the red banner, the Current Password box outlined red and "That is not the password this account signs in with" beneath it, all three boxes empty. Submitted a **3-character new password with a mismatched confirmation** — both errors shown at once, banner counting 2 fields, and the submitted value confirmed absent from the live DOM. Then a real change, which redirected to My Account with the flash, still signed in. |
| Administrator | Same menu item, own details *the Administrator (Health Committee Chair) / Administrator / admin*. Real change made and flashed. Opened **Audit Logs** and read both self-change rows in the table: attributed to the holder, module **Authentication**, phrase **Changed own account password**. |
| Barangay Official | Same menu item, own details, real change made and flashed. |

For each of the three: signed out, the **old** password was refused at the login
form with "Invalid security credentials.", and the **new** password signed in and
landed on that role's own dashboard.

Two screenshots during the run caught the page mid-repaint and one
`Page.captureScreenshot` call timed out; the state was re-read from the live DOM
each time and was correct. Nothing was retained from the pass either way, per
the folder rule above.

## Reproducing it

1. Copy `app.db` somewhere scratch and point a throwaway launcher at it, so the
   run writes nothing to the real database:

   ```python
   import app as m
   flask_app = m.create_app()
   flask_app.config["DATABASE"] = r"C:/path/to/scratch/app.db"
   flask_app.run(port=5056)
   ```

   Running `python app.py` instead works the same way — it simply changes the
   real accounts' passwords, which you then have to change back and cannot look
   up.
2. Sign in as any of the three seeded accounts and click the profile circle in
   the top right. **My Account** is the first item.
3. Submit the form with a wrong current password. The page must come back with
   the error on that box and all three boxes empty.
4. Submit it with the right current password and a five-character new one. Same
   shape, with "Too short. A password must be at least 12 characters; this one
   is 5."
5. Make a real change, sign out, and try the old password — it must be refused —
   then the new one.
6. As the Administrator, read **Audit Logs** filtered to **Authentication**. The
   change is one row, phrased *Changed own account password*, against the person
   who made it. An Administrator's reset of somebody else's password is a
   different phrase under **User Management**, and both are visible for
   comparison.

# The login form shows only messages it knows (2026-09-26)

Before this change, `login.html` printed whatever arrived in `?error=`.
`/login?error=Call 0917-000-0000 to verify your account` put that sentence in
the red alert box, on a page headed with the health center's name. Autoescaping
meant HTML came out as text rather than markup, but the text itself was shown,
and anyone could send the link. The self-deactivation notice added in 23c099a
could be summoned the same way, by typing it into the address bar. Nothing
about any account was disclosed.

## What changed

- The two refusals that redirect to the form with `?error=` now put a **key**
  there instead of the sentence:
  - `refuse_credentials()` in `utils/security.py` sends `?error=credentials`;
  - the maintenance-window refusal in `routes/auth.py` sends
    `?error=maintenance`.
- `login()` looks the key up in `LOGIN_FORM_MESSAGES` and gives the template
  the sentence it finds there, never the value that arrived. A key that is not
  in the table gives `None`, and the form shows no message. There is no
  fallback sentence and no echo.
- **No wording changed.** Both sentences are the same constants as before, and
  `login.html` is untouched. Only the redirect URL differs. It was
  `/login?error=Invalid+security+credentials.` and is now
  `/login?error=credentials`.

**Why keys, rather than a list of allowed sentences.** Checking the incoming
sentence against a list would also have worked, and would have kept the old
URLs. It was not chosen for two reasons. First, a URL carrying the sentence
still reads as "the page prints what the URL says". Second, the next edit to
that code could turn it back into an echo without anyone noticing. With keys,
the text on the page cannot come from the request, because nothing in the
request is text the page prints.

**Why both keys are safe to leave public.** Anyone can type `?error=credentials`
or `?error=maintenance`. Neither sentence names an account or says anything
about one, and both were already the answer any visitor could get by
submitting the form. The self-deactivation notice is deliberately **not** in
the table. It is delivered only as a flash in the signed session cookie of the
browser that earned it, and a key for it would let anybody display it.

## How it was verified

A git worktree at ffec974 (before) and one with the change (after), each over
a fresh copy of the live database. The live `app.db` had the same SHA-256
before and after. The probe served each tree with werkzeug on a real socket,
drove it with a cookie-jar HTTP client, and did not follow redirects
automatically, so each redirect could be checked.

- **Crafted `?error=` values show nothing.** The values tried:
  - plain text;
  - HTML with a link;
  - a `<script>` tag;
  - a 5,000-character string;
  - Tagalog text;
  - the old generic sentence, the old maintenance sentence, and the
    self-deactivation notice;
  - ` credentials ` with spaces, `CREDENTIALS` in capitals, and an empty value;
  - a repeated parameter with an unknown value first.

  For each, the page is byte-identical to a plain `/login`, and the supplied
  text (raw or escaped) appears nowhere in it. Before the change, every one of
  them was printed.
- **The ordinary refusals are unchanged.** Wrong password, unknown username,
  and a deactivated account with the correct and with a wrong password each
  land on a page that shows exactly "Invalid security credentials.". The four
  pages are byte-identical to each other and to the same pages before the
  change. The maintenance refusal (correct Health Center Staff credentials
  during a window) lands on a page byte-identical to before.
- **The self-deactivation notice still works end to end.** An Administrator
  with a second Administrator present deactivates their own account. The
  response is `302` to plain `/login`, the session holds no identity, and the
  form shows the notice and only it. A reload shows nothing. The last
  Administrator is still refused, and anonymous probes cannot produce the
  notice. 40 / 40.
- Route × role matrix (four roles plus anonymous, 490 cells): identical, no 5xx.

## Other pages that print query-string values

Every `request.args` read in `routes/` was traced to what it renders. Three
show the value back as it arrived. All three are behind sign-in, so a link
works only on someone already signed in. None was changed here: each fix would
change what a message says, or how a screen works, and both are outside this
change. They are listed for the team to decide.

- **Reports & Analytics and Community Reports**
  (`routes/report_views.py parse_report_range()`).
  - **What is shown:** a `type`, `from` or `to` the screen cannot use comes
    back in quotes, e.g. `"<value>" is not a date this screen can read.`,
    in the alert above the figures.
  - **Where:** for all four roles. The value is not length-capped. The same
    sentences are copied into the Excel export's "Date range" table, under
    the health center's name.
  - **The fix:** stop quoting the value, for example "The start date in the
    link is not a date this screen can read." That changes the wording of
    three messages across a screen and its exports, so it was reported
    instead.
- **Register Patient, first-visit check-in**
  (`?check_in=1&check_in_reason=…`, `routes/patient_views.py check_in_reason()`).
  - **What is shown:** the reason prints as "Reason for visit recorded so far:
    <value>". It also goes into a hidden field, so it is saved as the visit
    reason if the operator saves the form.
  - **Where:** for the Administrator, Health Center Staff and the Doctor.
    Capped at 200 characters.
  - **Why it works this way:** it is the designed path. The Check In dialog
    submits by GET and carries the typed reason here.
  - **The fix:** carry the reason another way, for example by POST or held on
    the server. That changes the check-in flow, so it was reported instead.
- **Register Patient, Save & Register Another** (`address`, `municipality`,
  `province`, `zip_code`).
  - **What is shown:** the carried address prefills the form's input boxes.
    Municipality and province are only matched against their dropdown
    options, so only the address and ZIP code boxes show the value as sent.
    Nothing is printed as page text, and nothing is saved unless the operator
    saves.
  - **Where:** for the same three roles.
  - **Assessment:** this is the same prefill a search box does, and it is by
    design.

The rest take only values they check. The patient search term goes back into
the search box, which is the search box's job. `month`, `module` and `tab` are
checked against the values the screen offers and fall back when they don't
match. Service Schedule's `edit` and `delete` must be the id of an existing
entry, and its "not on the schedule any more" message is fixed text. No
template reads `request` directly. Every value reaches a page through a view
builder, and that is where each one was traced.

## How to reproduce

`e2e_login_messages.py` and `e2e_self_deactivation.py` are in the session
scratchpad `…/claude/C--IDS-BPHCSN/b74e63e7-…/scratchpad/t2/`. Run each with a
code tree, a pristine copy of the database, a port and an output file. The JSON
each writes keeps every landing page in full, so two trees can be compared byte
for byte.

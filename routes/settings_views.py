"""Context for Screen 13, Settings.

This screen had no context at all until now, which was correct while there was
nothing to give it: `settings()` in routes/admin.py rendered the template bare,
and every field on it is a disabled control quoting utils/unavailable.py's
`settings` reason. Nothing was stored, so nothing was read.


WHY IT HAS A CONTEXT NOW, AND WHY ONLY THIS MUCH
------------------------------------------------
Nothing on this screen is stored yet -- the settings table is still empty and no
route writes it, so the reason above still stands over every input. What changed
is narrower and lives in one pane.

The Security Settings pane made a claim it could not keep. Under "Login Attempt
Limit" it said "Account locks after this many failed attempts", which was false
twice over: nothing counted the attempts, and nothing locked anything. Now that
routes/auth.py records every sign-in and every refusal, the first half is no
longer false -- the attempts are counted, and counted accurately -- while the
second half remains false and always was. A pane that says "5" beside a sentence
promising a lockout is worse for having real data behind half of it, because the
number now looks live.

So the pane keeps its disabled inputs and gains one block below them separating
the two: what this system actually records about sign-ins, with the real figures,
and the plain statement that no setting above is enforced. That is the whole of
what this file provides. It deliberately does not turn Session Timeout, Two-Factor
Authentication or any password rule into a stored value -- those are unbuilt
features, not unwired displays, and inventing storage for them is a different and
much larger task than the one that closed the sign-in gap.


WHERE THE FIGURES COME FROM
---------------------------
models/audit.py, the same two functions Audit Logs and User Management read, so
this screen cannot report a different number of sign-ins from the screen whose
job it is to report them. Nothing is counted locally here.
"""
from models.audit import get_audit_stats, get_last_logins
from models.users import get_all_users
from utils.dates import display_timestamp


def _most_recent_sign_in(last_logins, users):
    """(account name, rendered timestamp) for the newest sign-in, or (None, None).

    Derived from the same per-account map User Management's Last Login column
    uses rather than from a fresh query, so the two cannot name different
    moments. An empty map means no account has ever signed in, which is a real
    state on a freshly seeded database and is reported as itself.
    """
    if not last_logins:
        return None, None

    by_id = {user["id"]: user for user in users}
    # Ties are real: CURRENT_TIMESTAMP has one-second granularity, and two
    # accounts signing in within the same second is ordinary at shift change.
    # The rendered string cannot tell them apart either way -- display_timestamp()
    # stops at the minute -- so the only thing at stake is which name is printed,
    # and user_id breaks the tie so it is at least the same name on every reload
    # rather than whichever row the map happened to yield first.
    user_id, stamp = max(last_logins.items(), key=lambda item: (str(item[1]), item[0]))
    account = by_id.get(user_id)
    name = account["full_name"] if account else None
    return name, display_timestamp(stamp)


def settings_context():
    """Everything Screen 13 renders beyond the shared role context.

    One key, `security`. Adding more would mean this file had started reporting
    figures for panes whose controls are still disabled, and a screen that shows
    a live number under a dead input is the exact confusion the disabled fieldset
    was built to avoid.
    """
    stats = get_audit_stats()
    users = get_all_users()
    last_logins = get_last_logins()
    recent_name, recent_stamp = _most_recent_sign_in(last_logins, users)

    return {
        "security": {
            "sign_ins": stats["logins"],
            "sign_ins_today": stats["logins_today"],
            "refused": stats["failed_logins"],
            "refused_today": stats["failed_logins_today"],
            "accounts_signed_in": len(last_logins),
            "total_accounts": len(users),
            "most_recent_name": recent_name,
            "most_recent_at": recent_stamp,
        }
    }

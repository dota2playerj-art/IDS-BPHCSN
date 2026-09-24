"""A person's name, reduced to the two letters an avatar circle shows.

WHY THIS IS ONE FUNCTION NOW, AND WHAT IT COST TO FIND OUT
-----------------------------------------------------------
It was three. utils/context.py drew the initials in the sidebar and the profile
chip, routes/audit_views.py drew them beside every row of the audit trail, and
routes/user_views.py drew them on the User Management roster -- three
implementations of one rule, in three files, for one person's name.

They did not agree, and the disagreement was visible on screen. Correcting the
Administrator's persona to "Kagawad Antonio Acido" meant adding "kagawad" to the
list of titles the rule skips, so the circle reads the person's initials rather
than their honorific. Two of the three copies were updated. The third was not,
and the same account rendered

    AA   in the header, on every screen
    AA   on every audit entry it had ever written
    KA   on the User Management roster

with nothing in any of the three files hinting that the other two existed. The
roster's copy had in fact never agreed with the other two: it skipped no titles
at all and merely replaced full stops with spaces, so the previous persona
rendered "DR" there against "JR" everywhere else. The persona change did not
introduce that; it made it visible.

So the rule lives here, once. A future title -- another honorific, a rank, a
religious form of address -- is added to TITLES and every circle in the
application changes with it, rather than two of them changing and somebody
noticing the third months later.

WHAT THE RULE IS
----------------
Skip anything in TITLES, then take the first letter of the first remaining word
and the first letter of the last. One remaining word gives its first two
letters. Nothing left gives `empty`, which the caller chooses -- see below.

TITLES HOLDS HONORIFICS THAT PRECEDE A NAME, AND ONLY THOSE. "Kagawad" is here
because an elected barangay councilor's title is written in front of their name
exactly as "Dr." is, and an avatar reading "KA" names the office rather than the
person.

"Hon." was deliberately NOT here until 2026-09-05, and the reason it is here now
is the one this docstring already gave for keeping it out: "no account in this
system carries it ... It belongs in this list on the day such an account exists,
not before." That day arrived. The Barangay Official demo account was given the
persona "Hon. Michael Flores" by migrate_demo_data_hygiene.py, so an account now
carries the honorific and the avatar would otherwise read "HF" -- the title and
the surname -- instead of "MF".

Worth keeping the sequence visible, because it is the rule working: the entry was
added in the same commit as the account that needs it, rather than on speculation
years earlier or as a fix months later when somebody noticed the wrong initials.
"""
import re


TITLES = frozenset({
    "dr.", "dr", "mr.", "mrs.", "ms.", "engr.", "kagawad", "hon.", "hon",
})

# The comparison form. Full stops are stripped from the name before the words
# are compared, so they are stripped from the list too and "Dr." and "Dr" are
# one entry rather than two that could come to disagree. TITLES above stays
# readable as the list a person maintains; this is what the loop actually asks.
_TITLE_WORDS = frozenset(title.rstrip(".") for title in TITLES)

_PARENTHETICAL = re.compile(r"\([^)]*\)")


def initials(name, empty=""):
    """'Kagawad Antonio Acido' -> 'AA'. Titles skipped so the circle reads as a person.

    `empty` is what comes back when the name is blank, or is nothing but
    titles. It is a parameter rather than a fixed string because the three
    callers already disagreed about it and both answers are right where they
    are: the sidebar renders an empty circle for a signed-out visitor, because
    there is no person to abbreviate and a "?" would look like a failure to read
    one; the audit trail and the roster render "?", because every row there
    names an account that definitely exists, so a blank would read as the name
    having gone missing rather than as there being nobody.
    """
    # A parenthetical is a note about the name, not part of it: the demo Doctor
    # account is "RHU Physician (demo)" until the physician's real name is
    # confirmed, and its circle should read "RP", not "R(".
    bare = _PARENTHETICAL.sub(" ", str(name or ""))
    parts = [
        word
        for word in bare.replace(".", " ").split()
        if word.lower() not in _TITLE_WORDS
    ]
    if not parts:
        return empty
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

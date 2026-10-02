"""A person's name, reduced to the two letters an avatar circle shows."""
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

"""The small-count rule for rankings and breakdowns (Task 5d, D1).

The Administrator can see who is waiting in the queue and when. The Barangay
Official sees the same reports. In a ranking by diagnosis, complaint, condition or
medicine, a count of 1 over a short date range can point at one person. So for
those two roles every row whose count is from 1 up to SMALL_COUNT_THRESHOLD - 1
folds into one row, "Other (each fewer than 5)". Totals stay exact: only the names
of small groups are held back, and what they add up to is still counted.

The Doctor sees every count. Anyone else, and anyone whose role is unknown, gets
the rule: it fails closed.

ONE HELPER, USED WHERE THE RANKING IS BUILT. Every ranking in the project is
built in models/consultations.py, models/dispensing.py or models/patients.py, and
each calls fold_small_counts() before it returns. The screens, charts, Excel and
PDF files and print views only print what the builder returned, so a new screen
cannot show an unfolded ranking and a new export cannot skip the rule.
"""
from config import SMALL_COUNT_THRESHOLD
from utils.roles import is_care_team

OTHER_LABEL = f"Other (each fewer than {SMALL_COUNT_THRESHOLD})"

SMALL_COUNT_NOTE = (
    f" Rows with fewer than {SMALL_COUNT_THRESHOLD} are grouped under Other, so no "
    "one can be picked out of a small count. Totals are exact."
)

SMALL_COUNT_TEXT = f"Fewer than {SMALL_COUNT_THRESHOLD}"


def folds_small_counts(viewer_role):
    """True for every role outside the care team: the Administrator and the Official."""
    return not is_care_team(viewer_role)


def is_small(count):
    """A count the rule hides: 1 up to one less than the threshold. Zero is not small."""
    return 0 < count < SMALL_COUNT_THRESHOLD


def fold_small_counts(entries, viewer_role, *, label_key, sum_keys, count_key=None,
                      extra=None):
    """Return `entries` with every small row folded into one Other row.

    `entries` are dicts, most common first. `count_key` (default: the first of
    `sum_keys`) is the number tested against the threshold. The Other row adds up
    every key in `sum_keys` over the folded rows, carries `extra` for any other
    key the template reads, is flagged `other: True`, and is placed last. The named
    rows keep their order. Nothing is added when no row is small. The care team's
    list comes back untouched.
    """
    if not folds_small_counts(viewer_role):
        return list(entries)
    count_key = count_key or sum_keys[0]
    named = [entry for entry in entries if not is_small(entry[count_key])]
    small = [entry for entry in entries if is_small(entry[count_key])]
    if not small:
        return named
    other = {label_key: OTHER_LABEL, "other": True}
    other.update(extra or {})
    for key in sum_keys:
        other[key] = sum(entry.get(key) or 0 for entry in small)
    return named + [other]


def shown_count(count, viewer_role):
    """A count printed on its own line, not in a ranking: the number, or the words.

    For a count that would identify a small group by itself, such as how many
    restricted visits a range holds. Zero is shown as 0.
    """
    if folds_small_counts(viewer_role) and is_small(count):
        return SMALL_COUNT_TEXT
    return count


def ranking_note(entries, withheld, what):
    """The sentences a ranking's note adds about sealed visits and folded rows.

    One function for the screen, the print view, the Excel file and the PDF, so
    they cannot word it differently. `entries` is the ranking as built, `withheld`
    is how many sealed visits it holds, and `what` is the word for what is not
    shown ("diagnoses", "complaints"). It says nothing the rows do not show: a
    sealed visit is "counted under Confidential" when that row is there, and
    "counted in Other" when the rule folded it.
    """
    note = ""
    if any(entry.get("confidential") for entry in entries):
        note += (" Restricted consultations are counted under Confidential. "
                 f"Their {what} are not shown.")
    elif withheld and any(entry.get("other") for entry in entries):
        note += (" Restricted consultations are counted in Other. "
                 f"Their {what} are not shown.")
    if any(entry.get("other") for entry in entries):
        note += SMALL_COUNT_NOTE
    return note


def small_count_note(entries):
    """Only the folded-rows sentence, for a ranking that has no sealed visits."""
    return SMALL_COUNT_NOTE if any(entry.get("other") for entry in entries) else ""


def register_small_count_helpers(app):
    """Make the two note functions available to every template."""
    app.jinja_env.globals["ranking_note"] = ranking_note
    app.jinja_env.globals["small_count_note"] = small_count_note

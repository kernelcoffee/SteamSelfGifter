"""Text helpers shared by SQL queries and their pure-Python mirrors."""

_ASCII_UPPER_TO_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def ascii_lower(value: str) -> str:
    """Lowercase ASCII letters only, exactly like SQLite's built-in ``lower()``.

    Python's ``str.lower()`` also folds non-ASCII letters ("É" -> "é") while
    SQLite's ``lower()`` leaves them unchanged. Code that must agree with a
    SQL ``lower(...)`` comparison condition for condition (the genre
    exclusion in ``services.eligibility`` and
    ``GiveawayRepository.get_eligible``) lowercases with this instead.
    """
    return value.translate(_ASCII_UPPER_TO_LOWER)

"""Text helpers."""

_ASCII_UPPER_TO_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def ascii_lower(value: str) -> str:
    """Lowercase ASCII letters only, exactly like SQLite's built-in ``lower()``.

    Python's ``str.lower()`` also folds non-ASCII letters ("É" -> "é") while
    SQLite's ``lower()`` leaves them unchanged. The genre filters in
    ``services.eligibility`` and the genre-list normaliser in
    ``services.settings_service`` fold with this, so a genre the normaliser
    keeps as distinct is matched as distinct, and the match stays the one
    SQLite's ``lower()`` would give.
    """
    return value.translate(_ASCII_UPPER_TO_LOWER)

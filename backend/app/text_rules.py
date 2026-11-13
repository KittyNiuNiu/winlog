"""Rules for free text in requests: characters the database cannot store, and blank text.

`AGENTS.md` asks for all input to be validated at the API boundary. Two kinds of character
pass JSON parsing but cannot be stored, so without this check they reach PostgreSQL or the
driver and cause a 500:

- NUL (U+0000). PostgreSQL text cannot hold it.
- An unpaired surrogate (U+D800 to U+DFFF on its own, for example the JSON escape `\\ud800`).
  It has no UTF-8 form, so the text cannot be sent to the database.

Request models check every text field with `reject_unstorable_characters`, so such input gets
the shared validation error naming the field. Messages never contain the submitted text.

Maximum lengths (issue #43): `at_most` builds the check for a field's limit. Lengths are
counted in Unicode characters (code points), as Python's `len` counts a `str`, so an emoji
counts as one character, as in the contract and the frontend.
"""

import unicodedata
from collections.abc import Callable

from pydantic_core import PydanticCustomError

# The whitespace of ECMAScript's `\s`, which the `pattern: '\S'` rules in openapi.yaml use:
# tab, line feed, vertical tab, form feed, carriage return, the byte order mark, the line and
# paragraph separators, and every space separator (Unicode category Zs, for example U+0020,
# U+00A0 and U+3000).
_ECMA_WHITESPACE = frozenset("\t\n\v\f\r﻿  ")


def has_unstorable_characters(value: str) -> bool:
    """True if the text contains NUL or an unpaired surrogate."""
    if "\x00" in value:
        return True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


def reject_unstorable_characters(value: str) -> str:
    """Pydantic validator: the text unchanged, or a validation error naming the field."""
    if has_unstorable_characters(value):
        raise PydanticCustomError(
            "invalid_character",
            "Contains a character that cannot be stored (NUL or an unpaired surrogate).",
        )
    return value


def is_blank(value: str) -> bool:
    """True if the text is empty or only whitespace, as `pattern: '\\S'` defines it."""
    return all(char in _ECMA_WHITESPACE or unicodedata.category(char) == "Zs" for char in value)


def at_most(limit: int, what: str) -> Callable[[str], str]:
    """Pydantic validator: the text unchanged, or a validation error if it is longer than limit.

    `what` starts the message, for example "Text" gives "Text must be at most 2,000
    characters.". The message never contains the submitted text.
    """

    def check(value: str) -> str:
        if len(value) > limit:
            raise PydanticCustomError("too_long", f"{what} must be at most {limit:,} characters.")
        return value

    return check

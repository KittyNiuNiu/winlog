"""The password rule (issue #6) and argon2 hashing.

The rule is also written in openapi.yaml (components.schemas.Registration).

Character classes, from the Unicode general category of each character:
- uppercase letter: category `Lu`, for example `A` or `Ä`. Symbols that Python's
  `str.isupper()` also accepts, such as `Ⓐ` (category `So`), do not count.
- letter: any category starting with `L` (the same set as `str.isalpha()`).
- digit: only `0`-`9`.
- special character: any character that is neither a letter nor `0`-`9`, so `²`, `１`,
  `٣` and `Ⓐ` are special characters.
"""

import unicodedata

from argon2 import PasswordHasher

MIN_LENGTH = 10
MAX_LENGTH = 128
DIGITS = "0123456789"

_hasher = PasswordHasher()


def _is_uppercase_letter(char: str) -> bool:
    return unicodedata.category(char) == "Lu"


def _is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _is_special(char: str) -> bool:
    return not _is_letter(char) and char not in DIGITS


def _is_valid_text(password: str) -> bool:
    """False for an unpaired surrogate, which JSON allows but no UTF-8 text can hold."""
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def password_problems(password: str) -> list[str]:
    """Return what the password is missing. An empty list means it meets the rule.

    Length is counted in characters, not bytes. The password is checked exactly as typed.
    """
    problems = []
    if not _is_valid_text(password):
        problems.append("contains an invalid character (an unpaired surrogate)")
    if len(password) < MIN_LENGTH:
        problems.append(f"is too short: use at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"is too long: use at most {MAX_LENGTH} characters")
    if not any(_is_uppercase_letter(char) for char in password):
        problems.append("needs at least one uppercase letter")
    if not any(char in DIGITS for char in password):
        problems.append("needs at least one digit (0-9)")
    if not any(_is_special(char) for char in password):
        problems.append("needs at least one special character, such as ! # - or a space")
    return problems


def hash_password(password: str) -> str:
    """An argon2id hash. The plain password is never stored."""
    return _hasher.hash(password)

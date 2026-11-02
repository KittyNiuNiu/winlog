"""The password rule (issue #6) and argon2 hashing.

The rule is also written in openapi.yaml (components.schemas.Registration).
"""

from argon2 import PasswordHasher

MIN_LENGTH = 10
MAX_LENGTH = 128

_hasher = PasswordHasher()


def password_problems(password: str) -> list[str]:
    """Return what the password is missing. An empty list means it meets the rule.

    Length is counted in characters, not bytes. The password is checked exactly as typed.
    """
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"is too short: use at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"is too long: use at most {MAX_LENGTH} characters")
    if not any(char.isupper() for char in password):
        problems.append("needs at least one uppercase letter")
    if not any(char in "0123456789" for char in password):
        problems.append("needs at least one digit (0-9)")
    if all(char.isalpha() or char.isdigit() for char in password):
        problems.append("needs at least one special character, such as ! # - or a space")
    return problems


def hash_password(password: str) -> str:
    """An argon2id hash. The plain password is never stored."""
    return _hasher.hash(password)

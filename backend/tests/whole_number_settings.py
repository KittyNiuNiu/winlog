"""Checks shared by the tests of the strict whole-number settings (issue #108).

Every whole-number setting goes through `_whole_number` in `app/settings.py`, so each accepts
and refuses the same spellings and gives the same message: "must be a whole number from MIN
to MAX". These helpers give the values to try for one setting's range, and check that a
refused value stops the backend at startup with that message.
"""

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.settings import Settings, SettingsError

# A number of 5,000 digits: more than int() converts (4,300 digits), so pydantic's own
# parsing refuses it with its own text instead of the range message.
VERY_LONG_NUMBER = "9" * 5000


def accepted_values(minimum: int, maximum: int) -> list[tuple[str, int]]:
    """Values a setting with this range accepts, each with the number it is read as."""
    return [(str(minimum), minimum), (str(maximum), maximum), (" 30 ", 30), ("007", 7)]


def refused_values(minimum: int, maximum: int) -> list[str]:
    """Values a setting with this range refuses."""
    return [
        # Accepted by pydantic's lax integer parsing before issue #108.
        "+5",
        "1_0",
        "10.0",
        str(minimum - 1),
        str(maximum + 1),
        "-1",
        "-0",
        "7.5",
        "1e1",
        "0x10",
        "٣",  # ARABIC-INDIC DIGIT THREE
        "soon",
        "",
        " ",
        VERY_LONG_NUMBER,
    ]


def value_id(value: str) -> str:
    """A short pytest id, so the 5,000-digit value does not fill the test report."""
    return "5000-digits" if value == VERY_LONG_NUMBER else repr(value)


def assert_stops_at_startup(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, minimum: int, maximum: int
) -> None:
    """With `variable` set to `value`, the backend stops at startup with the range message."""
    monkeypatch.setenv(variable, value)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert message.startswith("Invalid configuration: ")
    assert f"{variable} is invalid: " in message
    assert f"must be a whole number from {minimum} to {maximum}" in message
    # The message never repeats the value. Values of one character, such as "0" or "1", are
    # part of the range message itself, so only longer values can be checked.
    if len(value.strip()) > 1:
        assert value.strip() not in message


def assert_range_applies_in_code(field: str, minimum: int, maximum: int, **required: object):
    """Settings built in code take an int inside the range, and refuse anything else."""

    def build(value: object) -> Settings:
        return Settings(_env_file=None, **required, **{field: value})

    assert getattr(build(minimum), field) == minimum
    assert getattr(build(maximum), field) == maximum
    for value in (minimum - 1, maximum + 1, 10.0, True):
        with pytest.raises(
            ValidationError, match=f"must be a whole number from {minimum} to {maximum}"
        ):
            build(value)

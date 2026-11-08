"""Registration input validation (FR-A1). These requests are rejected before any database use."""

import pytest
from fastapi.testclient import TestClient

from app.passwords import password_problems

VALID_EMAIL = "alice@example.com"


def _register(client: TestClient, **body) -> dict:
    response = client.post("/auth/register", json=body)
    assert response.status_code == 422
    return response.json()


def _reasons(body: dict, field: str) -> str:
    return " ".join(item["reason"] for item in body["fields"] if item["field"] == field)


# --- The password rule --------------------------------------------------------------------


def test_fr_a1_password_of_exactly_10_characters_meeting_every_requirement_is_accepted():
    assert password_problems("Abcdefg1!x") == []


def test_fr_a1_uppercase_letters_outside_ascii_count():
    assert password_problems("Äbcdefg1!x") == []


def test_fr_a1_password_is_checked_exactly_as_typed():
    # The surrounding spaces are part of the password; they are its special characters here.
    assert password_problems(" Abcdefg1 ") == []


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("Abcdef1!x", "too short"),  # 9 characters
        ("A1!" + "a" * 126, "too long"),  # 129 characters
        ("abcdefg1!x", "uppercase letter"),
        ("Abcdefgh!x", "digit"),
        ("Abcdefgh1x", "special character"),
    ],
)
def test_fr_a1_password_breaking_the_rule_is_rejected_with_the_missing_requirement(
    client: TestClient, contract, password: str, expected: str
):
    body = _register(client, email=VALID_EMAIL, password=password)

    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    reason = _reasons(body, "password")
    assert expected in reason
    # Only the missing requirement is named.
    others = {"too short", "too long", "uppercase letter", "digit", "special character"}
    assert not [other for other in others - {expected} if other in reason]


def test_fr_a1_every_missing_requirement_is_named(client: TestClient):
    body = _register(client, email=VALID_EMAIL, password="abc")

    reason = _reasons(body, "password")
    for expected in ["too short", "uppercase letter", "digit", "special character"]:
        assert expected in reason


def test_fr_a1_length_is_counted_in_characters_not_bytes():
    # 10 characters, but 19 bytes in UTF-8.
    assert password_problems("Äöüäöüä1!x") == []


# --- Which characters count (product owner decision on #6, 2026-11-08) -------------------
# Uppercase letter: Unicode general category Lu. Letter: any category L*. Digit: 0-9 only.
# Special character: anything that is neither a letter nor 0-9.


@pytest.mark.parametrize(
    "special",
    [
        "²",  # superscript two: a digit to Python, but not 0-9
        "１",  # fullwidth digit one
        "٣",  # Arabic-Indic digit three
        "Ⓐ",  # circled Latin capital A: a symbol (So), not a letter
        "́",  # combining acute accent: a mark (Mn), not a letter
    ],
)
def test_fr_a1_character_that_is_neither_a_letter_nor_0_to_9_is_a_special_character(
    special: str,
):
    assert password_problems("Abcdefgh1" + special) == []


@pytest.mark.parametrize("digit", ["²", "１", "٣"])
def test_fr_a1_digit_outside_0_to_9_does_not_count_as_the_digit(digit: str):
    assert password_problems("Abcdefgh!" + digit) == ["needs at least one digit (0-9)"]


@pytest.mark.parametrize(
    "symbol",
    [
        "Ⓐ",  # circled Latin capital A (So)
        "Ⅰ",  # Roman numeral one (Nl)
        "\U0001f130",  # squared Latin capital A (So)
    ],
)
def test_fr_a1_symbol_that_looks_uppercase_is_not_the_uppercase_letter(symbol: str):
    assert symbol.isupper()  # Python's isupper() accepts it; the rule does not
    assert password_problems(symbol + "bcdefgh12") == ["needs at least one uppercase letter"]


def test_fr_a1_circled_capital_a_password_is_rejected_for_the_missing_uppercase_letter(
    client: TestClient, contract
):
    body = _register(client, email=VALID_EMAIL, password="Ⓐbcdefgh12")

    contract("Error").validate(body)
    reason = _reasons(body, "password")
    assert "needs at least one uppercase letter" in reason
    assert "special character" not in reason


@pytest.mark.parametrize("letter", ["Α", "ẞ", "Д"])
def test_fr_a1_uppercase_letter_is_any_unicode_lu_letter(letter: str):
    # Greek capital alpha, Latin capital sharp s, Cyrillic capital de.
    assert password_problems(letter + "bcdefg1!x") == []


def test_fr_a1_titlecase_letter_is_a_letter_but_not_the_uppercase_letter():
    # U+01C5 (D with small z with caron) is titlecase (Lt), not uppercase (Lu). Being a
    # letter, it is not a special character either.
    assert password_problems("ǅbcdefg1xy") == [
        "needs at least one uppercase letter",
        "needs at least one special character, such as ! # - or a space",
    ]


# --- Input that is not valid text ---------------------------------------------------------


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_fr_a1_unpaired_surrogate_in_password_is_rejected(surrogate: str):
    assert password_problems("Abcdefgh1" + surrogate) == [
        "contains an invalid character (an unpaired surrogate)"
    ]


def _post_raw_json(client: TestClient, raw: str):
    # httpx cannot encode a lone surrogate, so the JSON escape is sent as written.
    return client.post(
        "/auth/register", content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )


@pytest.mark.parametrize("surrogate", ["\\ud800", "\\udfff"])
def test_fr_a1_unpaired_surrogate_in_password_returns_the_validation_error(
    client: TestClient, contract, surrogate: str
):
    response = _post_raw_json(
        client, '{"email": "alice@example.com", "password": "Abcdefgh1' + surrogate + '"}'
    )

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert [item["field"] for item in body["fields"]] == ["password"]
    assert "invalid character" in _reasons(body, "password")
    assert "Abcdefgh1" not in response.text


def test_fr_a1_unpaired_surrogate_in_email_returns_the_validation_error(
    client: TestClient, contract
):
    response = _post_raw_json(
        client, '{"email": "alice\\ud800@example.com", "password": "Abcdefg1!x"}'
    )

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert [item["field"] for item in body["fields"]] == ["email"]


def test_rejected_password_is_never_echoed(client: TestClient):
    response = client.post(
        "/auth/register", json={"email": VALID_EMAIL, "password": "nouppercase-secret-1"}
    )

    assert response.status_code == 422
    assert "nouppercase-secret-1" not in response.text


# --- Email and missing fields -------------------------------------------------------------


@pytest.mark.parametrize("email", ["not-an-email", "alice@", "@example.com", "alice@@example.com"])
def test_fr_a1_invalid_email_is_rejected(client: TestClient, contract, email: str):
    body = _register(client, email=email, password="Abcdefg1!x")

    contract("Error").validate(body)
    assert _reasons(body, "email")


@pytest.mark.parametrize("missing", ["email", "password"])
def test_fr_a1_missing_field_is_named(client: TestClient, contract, missing: str):
    body = {"email": VALID_EMAIL, "password": "Abcdefg1!x"}
    del body[missing]

    result = _register(client, **body)

    contract("Error").validate(result)
    assert [item["field"] for item in result["fields"]] == [missing]

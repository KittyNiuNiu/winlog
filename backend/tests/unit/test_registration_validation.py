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

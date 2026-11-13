"""The demo account without a database (FR-X1, issue #21).

Operation `demoLogin` and the `demo_account_not_deletable` error of `deleteAccount` in
openapi.yaml: the contract, the `DEMO_EMAIL` setting, demo-login, the order of the checks on
account deletion, the random password and the sample data rules. The login and the database
session are replaced by fakes. Tests against PostgreSQL, including the seed script, are in
tests/integration/test_demo.py.
"""

import calendar
import datetime as dt
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from app import accounts, demo, demo_seed
from app.accounts import Registration
from app.ai import get_ai_provider
from app.ai.limits import get_limited_ai
from app.auth import CurrentLogin, get_current_login
from app.db import get_session
from app.demo_seed import SAMPLE_ENTRIES, SAMPLE_SUMMARIES, random_password, sample_tag_names
from app.entries import EntryInput
from app.main import create_app
from app.models import CATEGORIES, User
from app.passwords import MAX_LENGTH, hash_password, password_problems
from app.settings import Settings, SettingsError, load_settings
from app.summaries import SummaryFilter, SummaryUpdate
from app.tags import normalise_tag_name
from scripts import seed_demo

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
DEMO_EMAIL = "demo@example.com"
PASSWORD = "Correct-Horse-7"
# Hashed once, because argon2 is slow on purpose.
PASSWORD_HASH = hash_password(PASSWORD)
DEMO_ERROR = {
    "code": "demo_account_not_deletable",
    "message": "The demo account cannot be deleted.",
}


@pytest.fixture
def demo_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"demo_email": DEMO_EMAIL})


@pytest.fixture
def session() -> MagicMock:
    return MagicMock()


def _app(settings: Settings, session: MagicMock, user: User | None = None):
    app = create_app(settings)
    app.dependency_overrides[get_session] = lambda: session
    if user is not None:
        app.dependency_overrides[get_current_login] = lambda: CurrentLogin(
            token_id=uuid.uuid4(), user=user
        )
    return app


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email, password_hash=PASSWORD_HASH)


def _calls(dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


def _route(router, path: str):
    [route] = [route for route in router.routes if route.path == path]
    return route


# --- Contract -----------------------------------------------------------------------------


def test_fr_x1_demo_login_operation_matches_the_contract(settings):
    generated = create_app(settings).openapi()["paths"]["/auth/demo"]["post"]
    expected = OPENAPI["paths"]["/auth/demo"]["post"]

    assert generated["operationId"] == expected["operationId"] == "demoLogin"
    # No authentication and no request body.
    assert expected["security"] == []
    assert "security" not in generated
    assert "requestBody" not in generated
    assert "requestBody" not in expected
    assert {"200", "404"} <= set(generated["responses"])
    assert {"200", "404", "500"} <= set(expected["responses"])
    ok = generated["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/DemoLoginResult"}
    assert expected["responses"]["200"]["content"]["application/json"]["schema"] == ok


def test_fr_x1_demo_login_result_schema_matches_the_contract(settings):
    generated = create_app(settings).openapi()["components"]["schemas"]["DemoLoginResult"]
    expected = OPENAPI["components"]["schemas"]["DemoLoginResult"]
    login = OPENAPI["components"]["schemas"]["LoginResult"]

    assert (
        set(generated["required"]) == set(expected["required"]) == {"token", "expires_at", "demo"}
    )
    assert set(generated["properties"]) == set(expected["properties"])
    # Like login, plus the field that marks a demo session.
    assert set(expected["properties"]) == set(login["properties"]) | {"demo"}
    assert expected["properties"]["demo"]["type"] == "boolean"
    assert expected["properties"]["demo"]["const"] is True


def test_fr_x1_delete_account_documents_the_demo_error(settings, contract):
    expected = OPENAPI["paths"]["/account"]["delete"]["responses"]
    generated = create_app(settings).openapi()["paths"]["/account"]["delete"]["responses"]

    assert expected["409"] == {"$ref": "#/components/responses/DemoAccountNotDeletable"}
    assert "409" in generated
    # Its own status: no other error of the operation uses 409.
    assert set(expected) == {"204", "401", "403", "409", "422", "429", "500"}
    example = OPENAPI["components"]["responses"]["DemoAccountNotDeletable"]["content"][
        "application/json"
    ]["example"]
    assert example == DEMO_ERROR
    contract("Error").validate(example)
    codes = OPENAPI["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    assert codes.count("demo_account_not_deletable") == 1


def test_fr_x1_demo_routes_never_depend_on_the_ai():
    for route in demo.router.routes:
        calls = _calls(route.dependant)
        assert get_ai_provider not in calls
        assert get_limited_ai not in calls


# --- Setting ------------------------------------------------------------------------------


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


def test_fr_x1_demo_is_off_without_demo_email(no_env_file, monkeypatch):
    _base_env(monkeypatch)

    assert load_settings().demo_email is None


@pytest.mark.parametrize("value", ["", "   "])
def test_fr_x1_empty_demo_email_turns_the_demo_off(no_env_file, monkeypatch, value: str):
    _base_env(monkeypatch)
    monkeypatch.setenv("DEMO_EMAIL", value)

    assert load_settings().demo_email is None


def test_fr_x1_demo_email_is_stored_in_lower_case(no_env_file, monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("DEMO_EMAIL", "  Demo.Visitor@Example.COM ")

    assert load_settings().demo_email == "demo.visitor@example.com"


@pytest.mark.parametrize("value", ["not-an-email", "demo@", "@example.com", "demo example.com"])
def test_fr_x1_invalid_demo_email_stops_the_backend(no_env_file, monkeypatch, value: str):
    _base_env(monkeypatch)
    monkeypatch.setenv("DEMO_EMAIL", value)

    with pytest.raises(SettingsError) as error:
        load_settings()

    assert "DEMO_EMAIL is invalid" in str(error.value)
    assert value not in str(error.value)


def test_fr_x1_demo_email_is_documented_in_env_example():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    # Empty by default, so the demo is off unless it is configured.
    assert "\nDEMO_EMAIL=\n" in env_example


def test_fr_x1_seed_script_is_listed_in_agents_md():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "uv run python -m scripts.seed_demo" in agents


# --- Demo-login ---------------------------------------------------------------------------


def test_fr_x1_demo_login_when_turned_off_returns_not_found(
    settings: Settings, session: MagicMock, contract
):
    response = TestClient(_app(settings, session)).post("/auth/demo")

    assert response.status_code == 404
    contract("Error").validate(response.json())
    assert response.json() == {"code": "not_found", "message": "The demo is not available."}
    session.scalars.assert_not_called()
    session.commit.assert_not_called()


def test_fr_x1_demo_login_before_the_account_exists_returns_not_found(
    demo_settings: Settings, session: MagicMock, contract
):
    session.scalars.return_value.one_or_none.return_value = None

    response = TestClient(_app(demo_settings, session)).post("/auth/demo")

    assert response.status_code == 404
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_found"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_fr_x1_demo_login_returns_token(demo_settings: Settings, session: MagicMock, contract):
    user_id = uuid.uuid4()
    session.scalars.return_value.one_or_none.return_value = user_id
    before = dt.datetime.now(dt.UTC)

    response = TestClient(_app(demo_settings, session)).post("/auth/demo")

    assert response.status_code == 200
    body = response.json()
    contract("DemoLoginResult").validate(body)
    assert body["demo"] is True
    assert len(body["token"]) >= 43
    expires_at = dt.datetime.fromisoformat(body["expires_at"])
    lifetime = dt.timedelta(days=demo_settings.token_lifetime_days)
    assert before + lifetime <= expires_at <= dt.datetime.now(dt.UTC) + lifetime
    # The token row is for the demo user, and is committed once.
    [row] = [call.args[0] for call in session.add.call_args_list]
    assert row.user_id == user_id
    session.commit.assert_called_once()


def test_fr_x1_demo_login_uses_the_same_token_function_as_login(
    demo_settings: Settings, session: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    user_id = uuid.uuid4()
    session.scalars.return_value.one_or_none.return_value = user_id
    calls = []

    def create_token(session, user_id, lifetime):
        calls.append((user_id, lifetime))
        return "t" * 43, MagicMock(expires_at=dt.datetime.now(dt.UTC) + lifetime)

    assert demo.create_token is accounts.create_token
    monkeypatch.setattr(demo, "create_token", create_token)

    assert TestClient(_app(demo_settings, session)).post("/auth/demo").status_code == 200
    assert calls == [(user_id, dt.timedelta(days=demo_settings.token_lifetime_days))]


def test_fr_x1_demo_login_ignores_a_body(demo_settings: Settings, session: MagicMock):
    session.scalars.return_value.one_or_none.return_value = uuid.uuid4()

    response = TestClient(_app(demo_settings, session)).post(
        "/auth/demo", json={"email": "alice@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["demo"] is True


# --- Account deletion ---------------------------------------------------------------------


DEMO_BODIES = [
    pytest.param({"json": {"current_password": PASSWORD}}, id="correct-password"),
    pytest.param({"json": {"current_password": "Wrong-Horse-8"}}, id="wrong-password"),
    pytest.param({"json": {}}, id="missing-password"),
    pytest.param({"json": {"current_password": ""}}, id="empty-password"),
    pytest.param({"json": {"current_password": None}}, id="null-password"),
    pytest.param({"json": {"current_password": "A1!" + "a" * MAX_LENGTH}}, id="too-long"),
    pytest.param({"json": ["not", "an", "object"]}, id="not-an-object"),
    pytest.param({}, id="no-body"),
    pytest.param(
        {"content": b'{"current_password": ', "headers": {"content-type": "application/json"}},
        id="invalid-json",
    ),
    pytest.param(
        {"content": b"\xff\xfe", "headers": {"content-type": "application/json"}},
        id="not-utf-8",
    ),
    pytest.param(
        {
            "content": b'{"current_password": "Surrogate-7\\ud800"}',
            "headers": {"content-type": "application/json"},
        },
        id="unpaired-surrogate",
    ),
    pytest.param(
        {"content": b"Correct-Horse-7", "headers": {"content-type": "text/plain"}}, id="text"
    ),
]


@pytest.mark.parametrize("kwargs", DEMO_BODIES)
def test_fr_x1_deleting_the_demo_account_returns_the_demo_error_whatever_the_body(
    demo_settings: Settings,
    session: MagicMock,
    contract,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict,
):
    checked = []
    monkeypatch.setattr(accounts, "verify_password", lambda *args: checked.append(args) or True)
    client = TestClient(_app(demo_settings, session, _user(DEMO_EMAIL)))
    headers = {"Authorization": "Bearer t", **kwargs.pop("headers", {})}

    response = client.request("DELETE", "/account", headers=headers, **kwargs)

    assert response.status_code == 409
    contract("Error").validate(response.json())
    assert response.json() == DEMO_ERROR
    # Before the password check, and nothing is deleted.
    assert checked == []
    session.execute.assert_not_called()
    session.commit.assert_not_called()
    assert PASSWORD not in response.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"current_password": PASSWORD}},
        {},
        {"content": b'{"current_password": ', "headers": {"content-type": "application/json"}},
    ],
)
def test_fr_x1_deleting_without_a_valid_token_returns_not_authenticated_first(
    demo_settings: Settings, session: MagicMock, contract, kwargs: dict
):
    # The real login check, with a fake session that finds no token.
    session.execute.return_value.one_or_none.return_value = None

    response = TestClient(_app(demo_settings, session)).request("DELETE", "/account", **kwargs)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    session.commit.assert_not_called()


def test_fr_x1_demo_email_with_other_case_is_still_the_demo_account(
    settings: Settings, session: MagicMock
):
    # The setting is normalised to lower case, as registration stores every email.
    mixed = Settings(
        _env_file=None,
        database_url=settings.database_url,
        cors_allowed_origins=settings.cors_allowed_origins,
        ai_provider="mock",
        demo_email="Demo@Example.com",
    )
    client = TestClient(_app(mixed, session, _user(DEMO_EMAIL)))

    response = client.request("DELETE", "/account", headers={"Authorization": "Bearer t"}, json={})

    assert response.status_code == 409
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    ("password", "status"), [(PASSWORD, 204), ("Wrong-Horse-8", 403), (None, 422)]
)
def test_fr_x1_other_users_delete_as_before_when_the_demo_is_on(
    demo_settings: Settings, session: MagicMock, password: str | None, status: int
):
    client = TestClient(_app(demo_settings, session, _user("alice@example.com")))
    body = {} if password is None else {"current_password": password}

    response = client.request(
        "DELETE", "/account", headers={"Authorization": "Bearer t"}, json=body
    )

    assert response.status_code == status


def test_fr_x1_demo_user_can_be_deleted_once_the_demo_is_turned_off(
    settings: Settings, session: MagicMock
):
    # With DEMO_EMAIL empty, the old demo user is an ordinary account.
    client = TestClient(_app(settings, session, _user(DEMO_EMAIL)))

    response = client.request(
        "DELETE",
        "/account",
        headers={"Authorization": "Bearer t"},
        json={"current_password": PASSWORD},
    )

    assert response.status_code == 204
    session.commit.assert_called_once()


def test_fr_x1_demo_check_runs_before_the_body_and_after_the_token():
    route = _route(accounts.router, "/account")

    # A route-level dependency that itself needs the login: FastAPI runs it before it
    # reports an invalid body, and AuthenticateFirstRoute runs it for a body it cannot read.
    [first, *_] = route.dependant.dependencies
    assert first.call is demo.refuse_demo_account
    assert get_current_login in _calls(first)


# --- Random password ----------------------------------------------------------------------


def test_fr_x1_random_password_always_meets_the_password_rule():
    for _ in range(2000):
        password = random_password()

        assert password_problems(password) == []
        # So creating the user can never fail registration's validation.
        Registration(email=DEMO_EMAIL, password=password)
        assert len(password) <= MAX_LENGTH


def test_fr_x1_random_password_is_new_every_time():
    passwords = {random_password() for _ in range(500)}

    assert len(passwords) == 500
    assert min(len(password) for password in passwords) >= 40


# --- Sample data --------------------------------------------------------------------------


def _months_before(day: dt.date, months: int) -> dt.date:
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _dates(today: dt.date) -> list[dt.date]:
    return [today - dt.timedelta(days=sample.days_ago) for sample in SAMPLE_ENTRIES]


def test_fr_x1_sample_data_has_at_least_20_entries_in_all_four_categories():
    assert len(SAMPLE_ENTRIES) >= 20
    assert {sample.category for sample in SAMPLE_ENTRIES} == set(CATEGORIES)


def test_fr_x1_sample_data_has_at_least_5_tags():
    names = sample_tag_names()

    assert len(names) >= 5
    # Unique ignoring case, as the tags table requires.
    assert len({name.casefold() for name in names}) == len(names)


def test_fr_x1_sample_data_has_entries_with_result_impact():
    with_result = [sample for sample in SAMPLE_ENTRIES if sample.result_impact]

    assert len(with_result) >= 2
    assert len(with_result) < len(SAMPLE_ENTRIES)


def test_fr_x1_sample_data_has_an_entry_in_another_language():
    other = [sample for sample in SAMPLE_ENTRIES if sample.language != "en"]

    assert other
    # The marked entries really are not English: they use letters English does not.
    assert all(any(not char.isascii() for char in sample.text) for sample in other)


@pytest.mark.parametrize(
    "today",
    [dt.date(2026, 11, 10), dt.date(2026, 8, 31), dt.date(2027, 3, 1), dt.date(2028, 2, 29)],
)
def test_fr_x1_sample_dates_spread_over_the_6_months_before_the_run(today: dt.date):
    dates = _dates(today)

    assert max(dates) == today - dt.timedelta(days=2)
    assert min(dates) >= _months_before(today, 6)
    # Every month of those 6 has entries.
    for months in range(6):
        start, end = _months_before(today, months + 1), _months_before(today, months)
        assert any(start <= day < end for day in dates), (start, end)


def test_fr_x1_sample_dates_fit_every_day_of_two_years():
    # 2028 is a leap year, so every month length and February 29 are covered.
    for offset in range(731):
        day = dt.date(2027, 1, 1) + dt.timedelta(days=offset)
        dates = _dates(day)
        assert max(dates) == day - dt.timedelta(days=2)
        assert min(dates) >= _months_before(day, 6)


def test_fr_x1_sample_entries_pass_the_entry_rules():
    today = dt.date(2026, 11, 10)
    for sample, day in zip(SAMPLE_ENTRIES, _dates(today), strict=True):
        entry = EntryInput(
            text=sample.text,
            date=day.isoformat(),
            category=sample.category,
            tags=list(sample.tags),
            result_impact=sample.result_impact,
        )
        # Stored exactly as the API would store it.
        assert entry.text == sample.text
        assert entry.tags == list(sample.tags)
        assert entry.result_impact == sample.result_impact
        assert all(normalise_tag_name(name) == name for name in sample.tags)


def test_fr_x1_sample_data_has_a_summary_whose_filter_matches_sample_entries():
    assert len(SAMPLE_SUMMARIES) >= 1
    today = dt.date(2026, 11, 10)
    for summary in SAMPLE_SUMMARIES:
        start = today - dt.timedelta(days=summary.start_days_ago)
        end = today - dt.timedelta(days=summary.end_days_ago)
        # A valid filter and a valid text, by the API's own rules.
        SummaryFilter(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            categories=list(summary.categories),
            tags=list(summary.tags),
        )
        assert SummaryUpdate(text=summary.text).text == summary.text
        assert start <= end
        assert set(summary.tags) <= set(sample_tag_names())
        matching = [
            sample
            for sample, day in zip(SAMPLE_ENTRIES, _dates(today), strict=True)
            if start <= day <= end
            and (not summary.categories or sample.category in summary.categories)
            and (not summary.tags or set(summary.tags) & set(sample.tags))
        ]
        assert len(matching) >= 2


def test_fr_x1_seeding_never_calls_the_ai():
    source = Path(demo_seed.__file__).read_text(encoding="utf-8")

    assert "app.ai" not in source
    assert "from app import ai" not in source


# --- Script -------------------------------------------------------------------------------


def test_fr_x1_script_changes_nothing_when_the_demo_is_off(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    def no_database(settings):
        raise AssertionError("must not connect")

    monkeypatch.setattr(seed_demo, "create_db_engine", no_database)

    assert seed_demo.run(settings) == (
        "The demo is turned off (DEMO_EMAIL is not set). Nothing was changed."
    )


def test_fr_x1_script_reports_invalid_settings(no_env_file, capsys):
    assert seed_demo.main() == 2

    assert "DATABASE_URL is required" in capsys.readouterr().err

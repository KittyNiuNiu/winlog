"""Data isolation between users, checked across the whole API (issue #22, FR-A3, §7.1).

The suite is driven by openapi.yaml: it reads the contract's operations, checks that the app
serves exactly those, and sends every protected operation without a valid token. Requests
that need an id or a body take them from the tables below, so a new operation without an
example fails with a message that says what to add, instead of going untested.

Two users, A and B, each have entries, tags, summaries and AI usage. Everything goes through
the real API against PostgreSQL. Every AI call goes to the mock provider.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import pytest
import yaml
from fastapi import APIRouter
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, inspect, text

from app.ai import MockProvider, Suggestion
from app.auth import hash_token
from app.main import create_app
from app.models import Token
from app.settings import Settings
from tests.conftest import OPENAPI_PATH
from tests.integration.conftest import ALLOWED_ORIGIN, APP_TABLES

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
PASSWORD = "Correct-Horse-7"
PERIOD = {"period_start": "2026-01-01", "period_end": "2026-12-31"}

# Every piece of A's data that B could see carries this marker; B's carries its own.
A_MARK = "ALICE-ONLY"
B_MARK = "BOB-ONLY"
# A tag of A's whose name B also uses later, spelled differently (FR-E3 matches ignoring case).
SHARED_TAG_A = "Project APOLLO"
SHARED_TAG_B = "project apollo"

NOT_FOUND = {"code": "not_found", "message": "Not found."}

# Daily limits for this suite: high enough for the setup and A's requests after B's are used up.
SUGGESTIONS_PER_USER = 3
SUMMARIES_PER_USER = 4
GLOBAL_REQUESTS = 1000

PUBLIC_OPERATIONS = {"getHealth", "register", "login", "demoLogin"}


# --- The contract ---------------------------------------------------------------------------


def _load_contract() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


CONTRACT = _load_contract()


def _contract_operations(spec: dict) -> dict[str, dict[str, Any]]:
    """operationId -> method, path, whether it needs authentication, and the operation."""
    default_security = spec.get("security", [])
    operations = {}
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue  # for example path-level parameters
            operations[operation["operationId"]] = {
                "method": method.upper(),
                "path": path,
                "needs_auth": bool(operation.get("security", default_security)),
                "operation": operation,
            }
    return operations


OPERATIONS = _contract_operations(CONTRACT)
PROTECTED = sorted(op_id for op_id, op in OPERATIONS.items() if op["needs_auth"])


def _body_schema(operation: dict) -> str | None:
    """The name of the operation's JSON request body schema, or None without a body."""
    body = operation.get("requestBody")
    if body is None:
        return None
    ref = body["content"]["application/json"]["schema"]["$ref"]
    return ref.rsplit("/", 1)[-1]


# A valid body for each request body schema in the contract. Every one is checked against the
# contract, so a rejected request is rejected for its token, not for its body.
SAMPLE_BODIES: dict[str, dict[str, Any]] = {
    "Registration": {"email": "someone-new@example.com", "password": PASSWORD},
    "Credentials": {"email": "unknown@example.com", "password": PASSWORD},
    "AccountDeletion": {"current_password": PASSWORD},
    "EntryInput": {
        "text": "Intruder text",
        "date": "2026-06-01",
        "category": "Learning",
        "tags": ["Intruder tag", SHARED_TAG_B],
        "result_impact": "Intruder impact",
    },
    "SummaryFilter": {**PERIOD, "categories": ["Achievement"], "tags": [SHARED_TAG_A]},
    "SummaryUpdate": {"text": "Intruder summary text"},
    "SuggestionRequest": {"text": "Intruder suggestion text"},
}


def _sample_body(op_id: str) -> dict[str, Any] | None:
    schema = _body_schema(OPERATIONS[op_id]["operation"])
    if schema is None:
        return None
    assert schema in SAMPLE_BODIES, (
        f"{op_id} takes a {schema} body: add a valid example to SAMPLE_BODIES in this file"
    )
    return SAMPLE_BODIES[schema]


def _url(op_id: str, ids: dict[str, str]) -> str:
    """The operation's path with each path parameter replaced by the given id."""
    url = OPERATIONS[op_id]["path"]
    for name, value in ids.items():
        url = url.replace("{" + name + "}", value)
    assert "{" not in url, (
        f"{op_id} has a path parameter this suite does not fill in: {url}. Give it one of A's "
        "ids in this file."
    )
    return url


def _path_parameters(op_id: str) -> set[str]:
    path = OPERATIONS[op_id]["path"]
    return {part[1:-1] for part in path.split("/") if part.startswith("{")}


# --- Helpers --------------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client: TestClient, email: str) -> tuple[uuid.UUID, str]:
    registered = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201
    logged_in = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert logged_in.status_code == 200
    return uuid.UUID(registered.json()["id"]), logged_in.json()["token"]


def _create_entry(client: TestClient, token: str, **fields: Any) -> dict:
    response = client.post("/entries", json=fields, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def _generate_summary(
    client: TestClient, token: str, summary_text: str, **filter_fields: Any
) -> dict:
    provider = _provider(client)
    provider.return_summary(summary_text)
    try:
        response = client.post("/summaries", json={**PERIOD, **filter_fields}, headers=_auth(token))
    finally:
        provider.reset()
    assert response.status_code == 201, response.text
    return response.json()


def _suggest(client: TestClient, token: str, suggestion_text: str):
    return client.post("/suggestions", json={"text": suggestion_text}, headers=_auth(token))


def _provider(client: TestClient) -> MockProvider:
    provider = client.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    return provider


def _ai_calls(client: TestClient) -> tuple[int, int]:
    provider = _provider(client)
    return len(provider.suggest_calls), len(provider.summarise_calls)


def _database(engine: Engine) -> dict[str, list[str]]:
    """Every row of every table, so a test can show that a request changed nothing."""
    with engine.connect() as connection:
        names = sorted(inspect(connection).get_table_names())
        return {
            name: sorted(
                repr(tuple(row)) for row in connection.execute(text(f'SELECT * FROM "{name}"'))
            )
            for name in names
        }


# One query per table that holds user data, selecting one user's rows.
_USER_ROWS = {
    "users": "SELECT * FROM users WHERE id = :user_id",
    "tokens": "SELECT * FROM tokens WHERE user_id = :user_id",
    "entries": "SELECT * FROM entries WHERE user_id = :user_id",
    "tags": "SELECT * FROM tags WHERE user_id = :user_id",
    "entry_tags": (
        "SELECT * FROM entry_tags"
        " WHERE entry_id IN (SELECT id FROM entries WHERE user_id = :user_id)"
    ),
    "summaries": "SELECT * FROM summaries WHERE user_id = :user_id",
    "ai_usage": "SELECT * FROM ai_usage WHERE user_id = :user_id",
}


def _user_rows(engine: Engine, user_id: uuid.UUID) -> dict[str, list[str]]:
    """All of one user's rows in every table that holds user data."""
    # ai_usage_global and login_attempts (only SHA-256 hashes, FR-A4) have no user id; every
    # other application table must be listed above.
    assert set(_USER_ROWS) == APP_TABLES - {"ai_usage_global", "login_attempts"}
    with engine.connect() as connection:
        return {
            name: sorted(
                repr(tuple(row)) for row in connection.execute(text(query), {"user_id": user_id})
            )
            for name, query in _USER_ROWS.items()
        }


def _views(client: TestClient, token: str) -> dict[str, Any]:
    """What the user sees through every read operation (the export time left out)."""
    headers = _auth(token)
    exported = client.get("/export/json", headers=headers).json()
    exported.pop("exported_at")
    entries = client.get("/entries", headers=headers).json()["entries"]
    summaries = client.get("/summaries", headers=headers).json()["summaries"]
    return {
        "entries": entries,
        "entry_details": [
            client.get(f"/entries/{e['id']}", headers=headers).json() for e in entries
        ],
        "tags": client.get("/tags", headers=headers).json(),
        "summaries": summaries,
        "summary_details": [
            client.get(f"/summaries/{s['id']}", headers=headers).json() for s in summaries
        ],
        "export_json": exported,
        # The Markdown export's second line is the export date.
        "export_markdown": client.get("/export/markdown", headers=headers).text.splitlines()[3:],
    }


def _assert_not_authenticated(response, contract, label: str) -> None:
    assert response.status_code == 401, f"{label}: {response.status_code} {response.text}"
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated", label
    assert response.headers["WWW-Authenticate"] == "Bearer", label


# --- Fixtures -------------------------------------------------------------------------------


@pytest.fixture
def api(test_database_url: str, migrated_db: Engine) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        ai_daily_suggestions_per_user=SUGGESTIONS_PER_USER,
        ai_daily_summaries_per_user=SUMMARIES_PER_USER,
        ai_daily_requests_global=GLOBAL_REQUESTS,
    )
    return TestClient(create_app(settings))


class World:
    """Users A and B, each with entries, tags, summaries and AI usage."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.a_email = f"alice-{uuid.uuid4()}@example.com"
        self.a_id, self.a_token = _register_and_login(client, self.a_email)
        self.b_id, self.b_token = _register_and_login(client, f"bob-{uuid.uuid4()}@example.com")

        self.a_entries = [
            _create_entry(
                client,
                self.a_token,
                text=f"{A_MARK} migrated the billing cluster",
                date="2026-03-02",
                category="Achievement",
                tags=[SHARED_TAG_A, f"{A_MARK} tag"],
                result_impact=f"{A_MARK} impact: costs down 40%",
            ),
            _create_entry(
                client,
                self.a_token,
                text=f"{A_MARK} learned Rust",
                date="2026-04-10",
                category="Learning",
                tags=[SHARED_TAG_A],
            ),
            _create_entry(
                client,
                self.a_token,
                text=f"{A_MARK} praised by the team lead",
                date="2026-05-01",
                category="Feedback",
            ),
        ]
        self.b_entries = [
            _create_entry(
                client,
                self.b_token,
                text=f"{B_MARK} fixed the login page",
                date="2026-03-05",
                category="Achievement",
                tags=[f"{B_MARK} tag"],
                result_impact=f"{B_MARK} impact",
            )
        ]
        self.a_summaries = [
            _generate_summary(client, self.a_token, f"{A_MARK} summary of the year"),
            _generate_summary(
                client, self.a_token, f"{A_MARK} summary of Apollo", tags=[SHARED_TAG_A]
            ),
        ]
        self.b_summaries = [_generate_summary(client, self.b_token, f"{B_MARK} summary")]
        assert _suggest(client, self.a_token, f"{A_MARK} suggestion text").status_code == 200
        assert _suggest(client, self.b_token, f"{B_MARK} suggestion text").status_code == 200

    def a_markers(self) -> list[str]:
        """Strings that only A's data contains: the marker, A's tag spelling and A's ids."""
        ids = [item["id"] for item in [*self.a_entries, *self.a_summaries]]
        return [A_MARK, SHARED_TAG_A, str(self.a_id), *ids]


@pytest.fixture
def world(api: TestClient) -> World:
    return World(api)


# --- Coverage of every endpoint -------------------------------------------------------------


def _served_routes(app) -> list:
    """Every route the app serves, with the routes of included routers listed one by one.

    `iter_route_contexts` is what FastAPI's own OpenAPI generator walks, so it sees the same
    routes, plus any route left out of the generated schema.
    """
    return list(iter_route_contexts(app.routes))


def _app_routes(app) -> dict[tuple[str, str], str | None]:
    """(method, path) -> operation id of every route the app serves, without the docs routes."""
    docs = {app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url}
    routes: dict[tuple[str, str], str | None] = {}
    for route in _served_routes(app):
        if route.path in docs:
            continue
        methods = route.methods
        if not methods:
            routes[("ANY", str(route.path))] = None  # for example a mounted app
            continue
        original = route.original_route
        operation_id = original.operation_id if isinstance(original, APIRoute) else None
        for method in methods - {"HEAD"}:  # Starlette adds HEAD to every plain GET route
            routes[(method, route.path)] = operation_id
    return routes


def test_fr_a3_app_routes_and_contract_operations_match_exactly(api: TestClient):
    app_routes = _app_routes(api.app)
    contract_routes = {(op["method"], op["path"]): op_id for op_id, op in OPERATIONS.items()}

    missing_from_contract = sorted(set(app_routes) - set(contract_routes))
    missing_from_app = sorted(set(contract_routes) - set(app_routes))
    assert missing_from_contract == [], "routes the app serves that openapi.yaml does not define"
    assert missing_from_app == [], "operations in openapi.yaml that the app does not serve"
    assert app_routes == contract_routes, "operation ids differ between the app and the contract"


def test_fr_a3_route_check_ignores_only_the_documentation_routes(api: TestClient):
    """The check above leaves out exactly FastAPI's own documentation routes."""
    every_path = {route.path for route in _served_routes(api.app)}
    ignored = every_path - {path for _, path in _app_routes(api.app)}
    assert ignored == {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def test_fr_a3_route_check_finds_a_route_missing_from_the_contract(api: TestClient):
    """The check is not blind to routers: a route added through a router is found."""
    extra = APIRouter()
    extra.add_api_route("/not-in-the-contract", lambda: {}, methods=["GET"])
    api.app.include_router(extra)

    assert ("GET", "/not-in-the-contract") in _app_routes(api.app)


def test_fr_a3_only_health_register_login_and_demo_login_need_no_authentication(
    api: TestClient,
):
    public_in_contract = {op_id for op_id, op in OPERATIONS.items() if not op["needs_auth"]}
    public_in_app = {
        op_id
        for op_id, op in _contract_operations(api.app.openapi()).items()
        if not op["needs_auth"]
    }

    assert public_in_contract == PUBLIC_OPERATIONS
    assert public_in_app == PUBLIC_OPERATIONS
    # The default is "needs a token", so a new operation is protected unless it opts out.
    assert CONTRACT["security"] == [{"bearerAuth": []}]


@pytest.mark.parametrize("op_id", sorted(PUBLIC_OPERATIONS))
def test_fr_a3_public_operations_work_without_a_token(api: TestClient, op_id: str):
    response = api.request(OPERATIONS[op_id]["method"], _url(op_id, {}), json=_sample_body(op_id))
    # Login with an unknown email is 401 too, but never with the not_authenticated code;
    # demo-login is 404 here because this app has no demo account.
    assert response.status_code != 401 or response.json()["code"] != "not_authenticated"
    assert response.status_code < 500


def test_fr_a3_sample_bodies_are_valid_for_the_contract(contract):
    """A request rejected below is rejected for its token, never for its body."""
    for op_id in OPERATIONS:
        body = _sample_body(op_id)
        if body is not None:
            contract(_body_schema(OPERATIONS[op_id]["operation"])).validate(body)


def _invalid_authorizations(client: TestClient, engine: Engine, world: World) -> dict:
    """Authorization headers that must all be rejected, by label. None sends no header."""
    # A token that was valid and is logged out.
    logged_in = client.post("/auth/login", json={"email": world.a_email, "password": PASSWORD})
    logged_out = logged_in.json()["token"]
    assert client.post("/auth/logout", headers=_auth(logged_out)).status_code == 204
    # A token that has expired. Inserted after the login, which deletes expired tokens.
    expired = f"expired-{uuid.uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            insert(Token).values(
                user_id=world.a_id,
                token_hash=hash_token(expired),
                expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1),
            )
        )
    return {
        "no header": None,
        "unknown token": f"Bearer unknown-{uuid.uuid4()}",
        "empty token": "Bearer ",
        "wrong scheme with a valid token": f"Basic {world.a_token}",
        "expired token": f"Bearer {expired}",
        "logged-out token": f"Bearer {logged_out}",
    }


@pytest.mark.parametrize("op_id", PROTECTED)
def test_fr_a3_protected_operation_without_a_valid_token_is_not_authenticated(
    world: World, migrated_db: Engine, contract, op_id: str
):
    client = world.client
    authorizations = _invalid_authorizations(client, migrated_db, world)
    ids = {"entryId": world.a_entries[0]["id"], "summaryId": world.a_summaries[0]["id"]}
    url = _url(op_id, ids)
    body = _sample_body(op_id)
    database = _database(migrated_db)
    ai_calls = _ai_calls(client)

    for label, authorization in authorizations.items():
        headers = {} if authorization is None else {"Authorization": authorization}
        response = client.request(OPERATIONS[op_id]["method"], url, json=body, headers=headers)

        _assert_not_authenticated(response, contract, f"{op_id} with {label}")
        assert _database(migrated_db) == database, f"{op_id} with {label} changed data"
        assert _ai_calls(client) == ai_calls, f"{op_id} with {label} called the AI"


# --- Cross-user access ----------------------------------------------------------------------

ID_OPERATIONS = sorted(op_id for op_id in PROTECTED if _path_parameters(op_id))


def test_fr_a3_every_operation_on_one_entry_or_summary_is_checked():
    """The cross-user test below covers every operation that takes an entry or summary id."""
    assert set(ID_OPERATIONS) == {
        "getEntry",
        "updateEntry",
        "deleteEntry",
        "getSummary",
        "updateSummary",
        "deleteSummary",
    }


@pytest.mark.parametrize("op_id", ID_OPERATIONS)
def test_fr_a3_user_cannot_read_change_or_delete_other_users_entry_or_summary(
    world: World, migrated_db: Engine, contract, op_id: str
):
    client = world.client
    (parameter,) = _path_parameters(op_id)
    items = {"entryId": world.a_entries, "summaryId": world.a_summaries}[parameter]
    a_views = _views(client, world.a_token)
    database = _database(migrated_db)
    ai_calls = _ai_calls(client)

    for item in items:
        response = client.request(
            OPERATIONS[op_id]["method"],
            _url(op_id, {parameter: item["id"]}),
            json=_sample_body(op_id),
            headers=_auth(world.b_token),
        )

        assert response.status_code == 404, f"{op_id} on A's {item['id']}: {response.text}"
        contract("Error").validate(response.json())
        assert response.json() == NOT_FOUND
        for marker in world.a_markers():
            assert marker not in response.text

    assert _database(migrated_db) == database
    assert _ai_calls(client) == ai_calls
    assert _views(client, world.a_token) == a_views


def test_fr_a3_user_cannot_read_other_users_entry(world: World):
    """The plain case, for readability: B asks for A's entry and gets what a missing id gets."""
    client = world.client
    a_entry = world.a_entries[0]["id"]

    by_b = client.get(f"/entries/{a_entry}", headers=_auth(world.b_token))
    missing = client.get(f"/entries/{uuid.uuid4()}", headers=_auth(world.b_token))
    by_a = client.get(f"/entries/{a_entry}", headers=_auth(world.a_token))

    assert by_b.status_code == 404
    assert by_b.json() == missing.json() == NOT_FOUND
    assert by_a.status_code == 200
    assert by_a.json()["text"] == world.a_entries[0]["text"]


LIST_OPERATIONS = sorted(
    op_id
    for op_id in PROTECTED
    if OPERATIONS[op_id]["method"] == "GET" and not _path_parameters(op_id)
)


def test_fr_a3_every_list_and_export_is_checked():
    """The test below covers every read operation that returns more than one item."""
    assert set(LIST_OPERATIONS) == {
        "listEntries",
        "listTags",
        "listSummaries",
        "exportJson",
        "exportMarkdown",
    }


@pytest.mark.parametrize("op_id", LIST_OPERATIONS)
def test_fr_a3_lists_and_exports_never_contain_other_users_data(world: World, op_id: str):
    client = world.client
    url = _url(op_id, {})

    as_b = client.get(url, headers=_auth(world.b_token))
    as_a = client.get(url, headers=_auth(world.a_token))

    assert as_b.status_code == 200
    for marker in world.a_markers():
        assert marker not in as_b.text, f"{op_id} shows B a piece of A's data: {marker}"
    # Not empty: B sees B's own data, and A sees A's but not B's.
    assert B_MARK in as_b.text
    assert A_MARK in as_a.text
    assert B_MARK not in as_a.text


def test_fr_a3_lists_and_exports_hold_exactly_the_users_own_items(world: World):
    client = world.client
    for user, token, entries, summaries in [
        ("A", world.a_token, world.a_entries, world.a_summaries),
        ("B", world.b_token, world.b_entries, world.b_summaries),
    ]:
        headers = _auth(token)
        entry_ids = {entry["id"] for entry in entries}
        summary_ids = {summary["id"] for summary in summaries}
        exported = client.get("/export/json", headers=headers).json()

        listed = client.get("/entries", headers=headers).json()["entries"]
        assert {entry["id"] for entry in listed} == entry_ids, user
        listed = client.get("/summaries", headers=headers).json()["summaries"]
        assert {summary["id"] for summary in listed} == summary_ids, user
        assert {entry["id"] for entry in exported["entries"]} == entry_ids, user
        assert {summary["id"] for summary in exported["summaries"]} == summary_ids, user

    assert client.get("/tags", headers=_auth(world.b_token)).json() == {"tags": [f"{B_MARK} tag"]}


@pytest.mark.parametrize("tag", [SHARED_TAG_A, SHARED_TAG_B, f"{A_MARK} tag"])
def test_fr_a3_filtering_by_other_users_tag_gets_no_entries(world: World, tag: str):
    client = world.client

    as_b = client.get("/entries", params={"tag": tag}, headers=_auth(world.b_token))
    as_a = client.get("/entries", params={"tag": tag}, headers=_auth(world.a_token))

    assert as_b.status_code == 200
    assert as_b.json() == {"entries": []}
    assert as_a.json()["entries"] != []  # the name does match A's own entries


@pytest.mark.parametrize("tag", [SHARED_TAG_A, SHARED_TAG_B, f"{A_MARK} tag"])
def test_fr_a3_summary_with_other_users_tag_gets_no_matching_entries(
    world: World, migrated_db: Engine, contract, tag: str
):
    client = world.client
    database = _database(migrated_db)
    ai_calls = _ai_calls(client)

    response = client.post(
        "/summaries", json={**PERIOD, "tags": [tag]}, headers=_auth(world.b_token)
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "no_matching_entries"
    # No AI call, no usage counted and nothing saved (§7.4).
    assert _ai_calls(client) == ai_calls
    assert _database(migrated_db) == database


def test_fr_a3_suggestions_never_return_other_users_tag_spelling(world: World):
    client = world.client
    _provider(client).return_suggestion(
        Suggestion(category="Achievement", tags=[SHARED_TAG_B, f"{A_MARK.lower()} TAG"])
    )

    as_b = _suggest(client, world.b_token, "Shipped Apollo")
    as_a = _suggest(client, world.a_token, "Shipped Apollo")

    assert as_b.status_code == 200
    assert as_b.json()["tags"] == [SHARED_TAG_B, f"{A_MARK.lower()} TAG"]
    # The same suggestion gets A's stored spelling only for A.
    assert as_a.json()["tags"] == [SHARED_TAG_A, f"{A_MARK} tag"]


def test_fr_a3_saving_an_entry_with_other_users_tag_name_creates_own_tag(
    world: World, migrated_db: Engine
):
    client = world.client
    a_rows = _user_rows(migrated_db, world.a_id)
    a_views = _views(client, world.a_token)

    created = _create_entry(
        client,
        world.b_token,
        text=f"{B_MARK} shipped Apollo",
        date="2026-06-01",
        category="Achievement",
        tags=[SHARED_TAG_B],
    )

    assert created["tags"] == [SHARED_TAG_B]
    b_tags = client.get("/tags", headers=_auth(world.b_token)).json()["tags"]
    assert b_tags == [f"{B_MARK} tag", SHARED_TAG_B]
    with migrated_db.connect() as connection:
        owners = dict(
            connection.execute(
                text("SELECT user_id, name FROM tags WHERE lower(name) = lower(:name)"),
                {"name": SHARED_TAG_B},
            ).all()
        )
    assert owners == {world.a_id: SHARED_TAG_A, world.b_id: SHARED_TAG_B}
    # B's tag is B's own: filtering finds only B's entry for B and only A's entries for A.
    by_b = client.get("/entries", params={"tag": SHARED_TAG_A}, headers=_auth(world.b_token))
    assert [entry["id"] for entry in by_b.json()["entries"]] == [created["id"]]
    by_a = client.get("/entries", params={"tag": SHARED_TAG_B}, headers=_auth(world.a_token))
    assert {entry["id"] for entry in by_a.json()["entries"]} == {
        world.a_entries[0]["id"],
        world.a_entries[1]["id"],
    }
    assert _user_rows(migrated_db, world.a_id) == a_rows
    assert _views(client, world.a_token) == a_views


def test_fr_a3_other_users_logout_does_not_affect_token_or_data(world: World, migrated_db: Engine):
    client = world.client
    a_rows = _user_rows(migrated_db, world.a_id)
    a_views = _views(client, world.a_token)

    assert client.post("/auth/logout", headers=_auth(world.b_token)).status_code == 204

    assert client.get("/entries", headers=_auth(world.b_token)).status_code == 401
    assert _user_rows(migrated_db, world.a_id) == a_rows
    assert _views(client, world.a_token) == a_views  # A's token still works


def test_fr_a3_other_users_account_deletion_does_not_affect_token_or_data(
    world: World, migrated_db: Engine
):
    client = world.client
    a_rows = _user_rows(migrated_db, world.a_id)
    a_views = _views(client, world.a_token)

    response = client.request(
        "DELETE", "/account", json={"current_password": PASSWORD}, headers=_auth(world.b_token)
    )

    assert response.status_code == 204
    assert all(rows == [] for rows in _user_rows(migrated_db, world.b_id).values())
    assert _user_rows(migrated_db, world.a_id) == a_rows
    assert _views(client, world.a_token) == a_views  # A's token still works


def _use_up(client: TestClient, request: Callable[[], Any], limit: str) -> None:
    """Send the request until the user's own daily limit is reached."""
    for _ in range(SUGGESTIONS_PER_USER + SUMMARIES_PER_USER):
        response = request()
        if response.status_code == 429:
            assert response.json()["limit"] == limit
            return
        assert response.status_code in (200, 201), response.text
    pytest.fail(f"the {limit} limit was never reached")


def test_fr_a3_other_user_reaching_an_ai_limit_does_not_block_user(
    world: World, migrated_db: Engine
):
    client = world.client
    b_headers = _auth(world.b_token)
    _use_up(client, lambda: _suggest(client, world.b_token, "More"), "user_suggestions")
    _use_up(
        client, lambda: client.post("/summaries", json=PERIOD, headers=b_headers), "user_summaries"
    )
    a_rows = _user_rows(migrated_db, world.a_id)

    # B is blocked for both kinds of request, A for neither.
    assert _suggest(client, world.b_token, "Again").status_code == 429
    assert client.post("/summaries", json=PERIOD, headers=b_headers).status_code == 429
    assert _user_rows(migrated_db, world.a_id) == a_rows  # B's requests counted nothing for A
    assert _suggest(client, world.a_token, f"{A_MARK} after B").status_code == 200
    summary = client.post("/summaries", json=PERIOD, headers=_auth(world.a_token))
    assert summary.status_code == 201

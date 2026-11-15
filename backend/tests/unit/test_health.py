import socket
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import git_commit
from app.health import check_database
from app.main import create_app
from app.settings import Settings
from tests.unit.conftest import ALLOWED_ORIGIN


def _client_for(database_url: str, timeout_seconds: int = 2) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        database_connect_timeout_seconds=timeout_seconds,
    )
    return TestClient(create_app(settings))


@pytest.fixture
def closed_port() -> int:
    """A local port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def silent_port() -> Iterator[int]:
    """A local port that accepts TCP connections but never answers, like a stuck database."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(5)
        yield sock.getsockname()[1]


def test_health_returns_documented_body_when_database_is_up(client: TestClient, contract):
    response = client.get("/health")

    assert response.status_code == 200
    # The tests run from a checkout, which records no commit (#102).
    assert response.json() == {"status": "ok", "database": "ok", "commit": None}
    contract("Health").validate(response.json())


# --- The commit the backend was built from (#102) ------------------------------------------

COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def commit_file(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """The file the image records its commit in (/app/git-commit), here a temporary one."""
    path = tmp_path / "git-commit"
    monkeypatch.setattr(git_commit, "GIT_COMMIT_FILE", path)
    return path


def test_health_commit_file_is_next_to_the_app_package_and_missing_in_a_checkout():
    # /app/git-commit in the image, where backend/Dockerfile writes it.
    backend = git_commit.GIT_COMMIT_FILE.parent
    assert git_commit.GIT_COMMIT_FILE.name == "git-commit"
    assert (backend / "app" / "git_commit.py").is_file()
    assert not git_commit.GIT_COMMIT_FILE.exists()


def test_health_commit_is_null_when_the_backend_was_built_without_one(
    client: TestClient, commit_file, contract
):
    # No file: `uv run uvicorn` and the tests, in a checkout.
    assert not commit_file.exists()
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "commit": None}
    contract("Health").validate(response.json())


def test_health_commit_names_the_recorded_commit(client: TestClient, commit_file, contract):
    commit_file.write_text(COMMIT, encoding="ascii")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "commit": COMMIT}
    contract("Health").validate(response.json())


@pytest.mark.parametrize(
    "recorded",
    [
        pytest.param("", id="empty"),  # a Docker Compose build, without the build argument
        pytest.param(COMMIT[:39], id="39-characters"),
        pytest.param(COMMIT + "0", id="41-characters"),
        pytest.param(COMMIT.upper(), id="upper-case"),
        pytest.param("g" + COMMIT[1:], id="a-g-in-it"),
        pytest.param(COMMIT + "\n", id="a-trailing-newline"),
        pytest.param(" " + COMMIT, id="a-leading-space"),
        pytest.param("sha-" + COMMIT, id="a-prefix"),
    ],
)
def test_health_commit_is_null_when_the_recorded_value_is_not_a_valid_commit(
    client: TestClient, commit_file, contract, recorded: str
):
    commit_file.write_text(recorded, encoding="ascii")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "commit": None}
    contract("Health").validate(response.json())


def test_health_commit_is_null_when_the_recorded_file_cannot_be_read(
    client: TestClient, commit_file, contract
):
    commit_file.write_bytes(b"\xff" * 40)  # not ASCII
    assert client.get("/health").json()["commit"] is None
    commit_file.unlink()
    commit_file.mkdir()  # not a file
    assert client.get("/health").json()["commit"] is None


def test_health_commit_comes_from_the_image_not_from_an_environment_variable(
    client: TestClient, commit_file, monkeypatch: pytest.MonkeyPatch
):
    # No value on Render, in Docker Compose or in .env can change what /health reports.
    for name in ("GIT_COMMIT", "RENDER_GIT_COMMIT", "COMMIT", "SOURCE_COMMIT", "GITHUB_SHA"):
        monkeypatch.setenv(name, COMMIT)
    assert client.get("/health").json()["commit"] is None
    assert "commit" not in Settings.model_fields
    assert not [name for name in Settings.model_fields if "commit" in name]


def test_health_commit_schema_matches_the_backend_rule(contract):
    validator = contract("Health")
    validator.validate({"status": "ok", "database": "ok", "commit": COMMIT})
    validator.validate({"status": "ok", "database": "ok", "commit": None})
    for invalid in ("", COMMIT[:39], COMMIT + "0", COMMIT.upper(), "g" + COMMIT[1:]):
        assert not validator.is_valid({"status": "ok", "database": "ok", "commit": invalid})
    # The field is required.
    assert not validator.is_valid({"status": "ok", "database": "ok"})


def test_health_commit_is_not_in_the_503_answer(closed_port: int, commit_file, contract):
    commit_file.write_text(COMMIT, encoding="ascii")
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{closed_port}/winlog")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "code": "database_unreachable",
        "message": "The database is not reachable.",
    }
    contract("Error").validate(response.json())


def test_health_reports_unreachable_database(closed_port: int, contract):
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{closed_port}/winlog")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    contract("Error").validate(response.json())


def test_health_gives_up_after_the_timeout_instead_of_hanging(silent_port: int):
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{silent_port}/winlog", 2)

    started = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    assert elapsed < 10


def test_health_gives_up_when_an_open_connection_never_answers(
    closed_port: int, monkeypatch: pytest.MonkeyPatch
):
    """Like a pooled connection to a paused database: no error, no answer, no time limit.

    The integration tests reproduce this with real PostgreSQL behind a paused proxy.
    """
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{closed_port}/winlog", 2)
    answer = threading.Event()

    def connect_that_never_answers():
        answer.wait(15)  # the test fails instead of hanging if nothing gives up earlier
        raise OperationalError("SELECT 1", {}, ConnectionError("no answer"))

    monkeypatch.setattr(client.app.state.engine, "connect", connect_that_never_answers)
    try:
        started = time.monotonic()
        response = client.get("/health")
        elapsed = time.monotonic() - started
    finally:
        answer.set()

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    assert elapsed < 5


def test_module_level_app_serves_health():
    """`uvicorn app.main:app` uses this object."""
    from app.main import app

    app.dependency_overrides[check_database] = lambda: True
    try:
        assert TestClient(app).get("/health").status_code == 200
    finally:
        app.dependency_overrides.clear()

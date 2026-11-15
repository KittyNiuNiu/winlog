"""The backend's settings under Docker Compose, without Docker (issue #61).

`docker-compose.yml` passes every variable in the repository-root `.env` to the backend
container with `env_file`, and keeps six entries under `environment:` that take precedence over
`.env`. No requirement ID covers Docker Compose (product-spec.md §9 "Reproducibility" has none),
so the test names describe the behaviour. `docker compose config` and the running system are
checked by CI's Full system job; the last test here reads that job's step that starts the
backend with the openai-compatible settings and the demo.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
CI = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))

# The entries Compose sets itself or requires; everything else comes from .env.
OVERRIDES = {
    "DATABASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "HSTS_MAX_AGE_SECONDS",
    "AI_PROVIDER",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "PORT",
}
CI_STEP = "Backend starts with the openai-compatible settings and the demo"


def test_docker_compose_passes_env_file_to_the_backend():
    services = COMPOSE["services"]

    # The short form: Compose needs .env, as it does for its ${…:?…} values.
    assert services["backend"]["env_file"] == ".env"
    for name in ("db", "lgtm", "frontend"):
        assert "env_file" not in services[name], name


def test_docker_compose_backend_overrides_only_what_compose_sets_or_requires():
    backend = COMPOSE["services"]["backend"]
    environment = backend["environment"]

    assert set(environment) == OVERRIDES
    # The container port that `ports:` publishes, whatever PORT in .env says. A string, as
    # Compose passes every value.
    assert environment["PORT"] == "8000"
    assert backend["ports"] == ["${BACKEND_HOST_PORT:-8000}:8000"]
    # 0 when .env has no value: no HSTS header over plain HTTP (#99).
    assert environment["HSTS_MAX_AGE_SECONDS"] == "${HSTS_MAX_AGE_SECONDS:-0}"
    # The db and lgtm services, not the host addresses in .env.
    assert urlsplit(environment["DATABASE_URL"]).hostname == "db"
    assert environment["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://lgtm:4318"
    # Required: Compose stops before anything starts when .env has no value.
    for name in ("CORS_ALLOWED_ORIGINS", "AI_PROVIDER"):
        assert environment[name] == f"${{{name}:?set {name} in .env}}"


def test_every_backend_setting_has_a_line_in_env_example():
    """Through `env_file`, a setting documented in .env.example then reaches Compose."""
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE, re.MULTILINE))
    settings = [name.upper() for name in Settings.model_fields]

    assert settings
    assert [name for name in settings if name not in documented] == []


def test_docker_compose_ci_check_of_the_openai_compatible_settings_makes_no_ai_request():
    """The product owner approved exactly this step on #61; a change needs that approval again."""
    steps = CI["jobs"]["full-system"]["steps"]
    names = [step.get("name") for step in steps]
    position = names.index(CI_STEP)
    step = steps[position]
    run = step["run"]

    # After the telemetry check, and followed only by the failure and clean-up steps.
    assert names[position - 1] == "Telemetry reached the local stack"
    assert [later.get("if") for later in steps[position + 1 :]] == [
        "failure()",
        "failure()",
        "always()",
    ]
    assert set(step) == {"name", "run"}
    # Exactly four lines of .env change: a placeholder key and a local address where nothing
    # listens, never a real provider or key.
    edits = re.findall(r"-e 's\|\^([A-Z_]+)=\.\*\|([A-Z_]+)=([^|]*)\|'", run)
    assert edits == [
        ("AI_PROVIDER", "AI_PROVIDER", "openai-compatible"),
        ("AI_API_KEY", "AI_API_KEY", "not-a-real-key"),
        ("AI_BASE_URL", "AI_BASE_URL", "http://127.0.0.1:9/v1"),
        ("DEMO_EMAIL", "DEMO_EMAIL", "demo@example.com"),
    ]
    assert run.count("sed ") == 1 and '[ "$changed" = 4 ]' in run
    # Only the backend is recreated, from the image the job built.
    assert "docker compose up -d --no-build --no-deps --force-recreate backend" in run
    assert "--build " not in run
    # The only requests: GET /health and POST /auth/demo on the local backend.
    curls = [line for line in run.splitlines() if "curl " in line]
    assert len(curls) == 2
    assert "-X" not in curls[0] and curls[0].count("http://localhost:8000/health") == 1
    assert "-X POST http://localhost:8000/auth/demo" in curls[1]
    assert set(re.findall(r"https?://[^\s'\"|]+", run)) == {
        "http://127.0.0.1:9/v1",
        "http://localhost:8000/health",
        "http://localhost:8000/auth/demo",
    }
    for path in ("/suggestions", "/summaries", "/entries"):
        assert path not in run
    # The three checks, each printed.
    assert "start: demo account reset" in run
    assert '[ "$status" = "200" ]' in run and '[ "$demo" != true ]' in run

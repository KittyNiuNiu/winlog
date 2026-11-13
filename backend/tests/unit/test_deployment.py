"""Production deployment on Render (issue #38, product-spec.md §7.7, §10.2 and §10.4).

Checks the Render Blueprint (`render.yaml`), the backend's start script (`start.sh`) and what
the backend image contains. The start script and the static site's build command run here
with stand-ins for alembic, python, uvicorn, node and npm, so no database, server or network
is needed. The real image and the real start are checked by CI's Full system job.
"""

import os
import shlex
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
START_SCRIPT = BACKEND / "start.sh"
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))

SECRETS = {"DATABASE_URL", "AI_API_KEY"}
# The production values the issue lists, as plain values in render.yaml.
PLAIN_BACKEND_VALUES = {
    "AI_PROVIDER": "openai-compatible",
    "AI_BASE_URL": "https://openrouter.ai/api/v1",
    "AI_MODEL": "anthropic/claude-haiku-5.5",
    "AI_SUGGESTION_TIMEOUT_SECONDS": "15",
    "AI_SUMMARY_TIMEOUT_SECONDS": "60",
    "AI_SUMMARY_MAX_TOKENS": "16000",
    "AI_SUMMARY_MAX_INPUT_CHARACTERS": "50000",
    "AI_DAILY_SUGGESTIONS_PER_USER": "10",
    "AI_DAILY_SUMMARIES_PER_USER": "2",
    "AI_DAILY_REQUESTS_GLOBAL": "100",
    "LOGIN_MAX_FAILED_ATTEMPTS": "10",
    "LOGIN_ATTEMPT_WINDOW_MINUTES": "15",
    "DEMO_LOGIN_MAX_ATTEMPTS": "20",
    "DEMO_LOGIN_WINDOW_MINUTES": "60",
    "TOKEN_LIFETIME_DAYS": "7",
    "DATABASE_CONNECT_TIMEOUT_SECONDS": "3",
    "DEMO_EMAIL": "demo@example.com",
}


def _service(runtime: str) -> dict:
    [service] = [s for s in BLUEPRINT["services"] if s["runtime"] == runtime]
    return service


def _env_vars(service: dict) -> dict[str, dict]:
    return {var["key"]: var for var in service["envVars"]}


def _plain_values(service: dict) -> dict[str, str]:
    return {key: str(var["value"]) for key, var in _env_vars(service).items() if "value" in var}


def _is_public_url(value: str) -> bool:
    return value.startswith("https://") and "/" not in value.removeprefix("https://")


# --- render.yaml ---------------------------------------------------------------------------


def test_deploy_blueprint_has_a_docker_backend_and_a_static_site():
    assert [(s["type"], s["runtime"]) for s in BLUEPRINT["services"]] == [
        ("web", "docker"),
        ("web", "static"),
    ]
    backend = _service("docker")
    assert backend["dockerfilePath"] == "./backend/Dockerfile"
    assert backend["dockerContext"] == "./backend"
    assert backend["healthCheckPath"] == "/health"
    # Free instance in the Render region closest to Neon's AWS eu-central-1 (Frankfurt).
    # Static sites take no plan and no region in a Blueprint: they are free and served from
    # Render's CDN.
    assert backend["plan"] == "free"
    assert backend["region"] == "frankfurt"
    assert "plan" not in _service("static") and "region" not in _service("static")
    # The image's own start (start.sh) runs on Render too.
    assert "dockerCommand" not in backend and "startCommand" not in backend


def test_deploy_both_services_deploy_from_main_after_checks_pass():
    for service in BLUEPRINT["services"]:
        assert service["branch"] == "main"
        assert service["autoDeployTrigger"] == "checksPass"


def test_deploy_only_the_two_secrets_are_entered_in_the_dashboard():
    synced_by_hand = {
        var["key"]
        for service in BLUEPRINT["services"]
        for var in service["envVars"]
        if var.get("sync") is False
    }
    assert synced_by_hand == SECRETS
    backend_vars = _env_vars(_service("docker"))
    for key in SECRETS:
        assert backend_vars[key] == {"key": key, "sync": False}


def test_deploy_backend_production_values_are_plain_values():
    values = _plain_values(_service("docker"))
    assert {key: values.get(key) for key in PLAIN_BACKEND_VALUES} == PLAIN_BACKEND_VALUES
    assert set(values) == set(PLAIN_BACKEND_VALUES) | {"CORS_ALLOWED_ORIGINS"}


def test_deploy_public_urls_point_at_the_other_service():
    backend, static = _service("docker"), _service("static")
    cors = _plain_values(backend)["CORS_ALLOWED_ORIGINS"]
    api = _plain_values(static)["VITE_API_BASE_URL"]
    assert _is_public_url(cors) and _is_public_url(api)
    assert cors == f"https://{static['name']}.onrender.com"
    assert api == f"https://{backend['name']}.onrender.com"


def test_deploy_no_telemetry_compose_or_test_variables_on_render():
    keys = {var["key"] for service in BLUEPRINT["services"] for var in service["envVars"]}
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in keys
    assert "TEST_DATABASE_URL" not in keys
    assert "PORT" not in keys
    assert not [key for key in keys if key.startswith("POSTGRES_") or key.endswith("_HOST_PORT")]


def test_deploy_backend_values_are_valid_settings(monkeypatch):
    """The backend starts with exactly the values in render.yaml plus the two secrets."""
    for key in list(os.environ):
        monkeypatch.delenv(key)
    for key, value in _plain_values(_service("docker")).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:placeholder@db.invalid/winlog")
    monkeypatch.setenv("AI_API_KEY", "placeholder")

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "openai-compatible"
    assert settings.cors_allowed_origins == ["https://winlog-app.onrender.com"]
    assert settings.demo_email == "demo@example.com"
    assert settings.otel_exporter_otlp_endpoint is None


def test_deploy_static_site_publishes_the_build_with_the_pinned_node_and_spa_rewrite():
    static = _service("static")
    assert static["staticPublishPath"] == "./frontend/dist"
    nvmrc = (ROOT / "frontend" / ".nvmrc").read_text(encoding="utf-8").strip()
    assert _plain_values(static)["NODE_VERSION"] == nvmrc
    assert static["routes"] == [{"type": "rewrite", "source": "/*", "destination": "/index.html"}]


def _fake_tool(directory: Path, name: str, body: str) -> None:
    tool = directory / name
    tool.write_text(f'#!/bin/sh\necho "{name} $*" >> "$CALLS"\n{body}\n', encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)


def _run_static_build(tmp_path: Path, api_url: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "frontend").mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    _fake_tool(bin_dir, "npm", "")
    _fake_tool(bin_dir, "node", 'echo "v26.13.0"')
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "CALLS": str(calls),
        "VITE_API_BASE_URL": api_url,
    }
    result = subprocess.run(
        ["sh", "-c", _service("static")["buildCommand"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, calls.read_text(encoding="utf-8")


def test_deploy_static_build_runs_npm_ci_and_build(tmp_path):
    result, calls = _run_static_build(tmp_path, "https://example.onrender.com")

    assert result.returncode == 0, result.stderr
    assert "Node v26.13.0" in result.stdout
    assert calls.splitlines() == ["node --version", "npm ci --no-audit --no-fund", "npm run build"]


def test_deploy_static_build_fails_clearly_without_api_url(tmp_path):
    result, calls = _run_static_build(tmp_path, "")

    assert result.returncode != 0
    assert "VITE_API_BASE_URL is required" in result.stderr
    assert "npm" not in calls


# --- backend/start.sh ----------------------------------------------------------------------


def _run_start(
    tmp_path: Path, env: dict[str, str], fail: str | None = None, reset_prints: str = ""
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run start.sh with stand-ins that record their calls; `fail` names one that fails."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    for tool in ("alembic", "python", "uvicorn"):
        body = "exit 3" if tool == fail else ""
        if tool == "python" and reset_prints:
            body = f'echo "{reset_prints}"\n{body}'
        _fake_tool(bin_dir, tool, body)
    result = subprocess.run(
        ["sh", str(START_SCRIPT)],
        cwd=tmp_path,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALLS": str(calls), **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, calls.read_text(encoding="utf-8").splitlines()


def test_fr_x1_start_migrates_then_resets_the_demo_then_serves_on_port(tmp_path):
    result, calls = _run_start(tmp_path, {"PORT": "10000", "DEMO_EMAIL": "demo@example.com"})

    assert result.returncode == 0, result.stderr
    assert calls == [
        "alembic upgrade head",
        "python -m scripts.seed_demo",
        "uvicorn app.main:app --host 0.0.0.0 --port 10000",
    ]
    assert result.stdout.splitlines() == [
        "start: applying database migrations",
        "start: resetting the demo account",
        "start: demo account reset",
        "start: starting the server on port 10000",
    ]


@pytest.mark.parametrize("env", [{}, {"DEMO_EMAIL": "", "PORT": ""}])
def test_fr_x1_start_without_demo_email_skips_reset_and_serves_on_8000(tmp_path, env):
    result, calls = _run_start(tmp_path, env)

    assert result.returncode == 0, result.stderr
    assert calls == [
        "alembic upgrade head",
        "uvicorn app.main:app --host 0.0.0.0 --port 8000",
    ]
    assert "skipping the demo reset" in result.stdout


@pytest.mark.parametrize("failing", ["alembic", "python"])
def test_fr_x1_start_stops_without_server_when_a_step_fails(tmp_path, failing):
    result, calls = _run_start(tmp_path, {"DEMO_EMAIL": "demo@example.com"}, fail=failing)

    assert result.returncode != 0
    assert not [call for call in calls if call.startswith("uvicorn")]
    assert "starting the server" not in result.stdout


def test_deploy_start_keeps_the_access_log_off_and_prints_no_email(tmp_path):
    lines = START_SCRIPT.read_text(encoding="utf-8").splitlines()
    code = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    commands = [shlex.split(line) for line in lines if line.startswith("exec ")]
    assert commands == [["exec", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$port"]]
    assert "--access-log" not in code and "--log-config" not in code

    # The reset's own summary line names the demo email, so it is not printed.
    result, _ = _run_start(
        tmp_path,
        {"DEMO_EMAIL": "demo@example.com"},
        reset_prints="Reset the demo account demo@example.com to the sample data",
    )
    assert result.returncode == 0, result.stderr
    assert "demo@example.com" not in result.stdout + result.stderr


# --- backend image -------------------------------------------------------------------------


def test_deploy_image_contains_the_demo_reset_but_not_the_model_comparison():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    copies = [line for line in dockerfile.splitlines() if line.startswith("COPY ")]
    assert "COPY scripts/__init__.py scripts/seed_demo.py ./scripts/" in copies
    assert "COPY start.sh ./" in copies
    assert not [line for line in copies if "model_comparison" in line or line == "COPY . ."]
    assert not [line for line in copies if line.startswith("COPY scripts ")]
    assert 'CMD ["sh", "/app/start.sh"]' in dockerfile

    dockerignore = (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "scripts/model_comparison/" in dockerignore


def test_deploy_port_is_documented_in_env_example():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    # Empty by default: the start script then uses 8000, as Docker Compose expects.
    assert "\nPORT=\n" in env_example


# --- ops/deployment.md ---------------------------------------------------------------------


def test_deploy_guide_lists_every_render_variable_and_no_secret():
    guide = (ROOT / "ops" / "deployment.md").read_text(encoding="utf-8")
    keys = {var["key"] for service in BLUEPRINT["services"] for var in service["envVars"]}
    assert [key for key in sorted(keys) if f"| `{key}` |" not in guide] == []
    # The only connection string is the placeholder pattern, never a real one.
    assert "postgresql://<user>:<password>@" in guide
    assert "npm run test:e2e" in guide and "sslmode=require" in guide
    for secret_prefix in ("sk-or-", "npg_"):
        assert secret_prefix not in guide

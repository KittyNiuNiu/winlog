"""Deployment on Render: dev and production (issues #38 and #39, product-spec.md §7.7, §10.2
and §10.4).

Checks the Render Blueprint (`render.yaml`), the CI and Deploy workflows, the backend's start
script (`start.sh`) and what the backend image contains. The start script, the static site's
build command and the deploy steps run here with stand-ins for alembic, python, uvicorn, node,
npm and docker, and with a local HTTP server in place of Render's deploy hooks, so no database,
server, registry or network is needed. The real image is built and checked by CI's Backend
image job, and the real start by its Full system job.
"""

import http.server
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import threading
from pathlib import Path

import pytest
import yaml

from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
START_SCRIPT = BACKEND / "start.sh"
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
WORKFLOWS = ROOT / ".github" / "workflows"
CI = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
DEPLOY_TEXT = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
DEPLOY = yaml.safe_load(DEPLOY_TEXT)

IMAGE = "ghcr.io/kittyniuniu/winlog-backend"
PROD_API, PROD_APP = "winlog-api", "winlog-app"
DEV_API, DEV_APP = "winlog-api-dev", "winlog-app-dev"
# Production's secrets, and dev's only one.
SECRETS = {"DATABASE_URL", "AI_API_KEY"}
DEV_SECRETS = {"DATABASE_URL"}
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
# Dev differs from production only in these: the mock AI and no real AI settings (#39).
DEV_ONLY_AI = {"AI_PROVIDER": "mock"}
REAL_AI_ONLY = {"AI_BASE_URL", "AI_MODEL", "AI_API_KEY"}


def _service(name: str) -> dict:
    [service] = [s for s in BLUEPRINT["services"] if s["name"] == name]
    return service


def _env_vars(service: dict) -> dict[str, dict]:
    return {var["key"]: var for var in service["envVars"]}


def _plain_values(service: dict) -> dict[str, str]:
    return {key: str(var["value"]) for key, var in _env_vars(service).items() if "value" in var}


def _synced_by_hand(service: dict) -> set[str]:
    return {var["key"] for var in service["envVars"] if var.get("sync") is False}


def _is_public_url(value: str) -> bool:
    return value.startswith("https://") and "/" not in value.removeprefix("https://")


def _run_steps(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


# --- render.yaml ---------------------------------------------------------------------------


def test_deploy_blueprint_has_two_image_backends_and_two_static_sites():
    assert [(s["name"], s["type"], s["runtime"]) for s in BLUEPRINT["services"]] == [
        (PROD_API, "web", "image"),
        (DEV_API, "web", "image"),
        (PROD_APP, "web", "static"),
        (DEV_APP, "web", "static"),
    ]
    for name in (PROD_API, DEV_API):
        backend = _service(name)
        assert backend["healthCheckPath"] == "/health"
        # Free instance in the Render region closest to Neon's AWS eu-central-1 (Frankfurt).
        assert backend["plan"] == "free"
        assert backend["region"] == "frankfurt"
        # The image's own start (start.sh) runs on Render too.
        assert "dockerCommand" not in backend and "startCommand" not in backend
        # Render builds nothing: no Dockerfile, no repository, no branch.
        for field in ("dockerfilePath", "dockerContext", "repo", "branch", "buildCommand"):
            assert field not in backend
    # Static sites take no plan and no region in a Blueprint: they are free and served from
    # Render's CDN.
    for name in (PROD_APP, DEV_APP):
        assert "plan" not in _service(name) and "region" not in _service(name)


def test_deploy_backends_pull_their_environment_tag_of_the_public_ghcr_image():
    # A deploy that names no image gets the tag the pipeline moved last (#39).
    assert _service(PROD_API)["image"] == {"url": f"{IMAGE}:production"}
    assert _service(DEV_API)["image"] == {"url": f"{IMAGE}:dev"}
    # The package is public: no registry credential anywhere.
    assert not [s for s in BLUEPRINT["services"] if "registryCredential" in s]


def test_deploy_no_service_deploys_by_itself():
    assert "checksPass" not in (ROOT / "render.yaml").read_text(encoding="utf-8")
    for name in (PROD_APP, DEV_APP):
        static = _service(name)
        assert static["branch"] == "main"
        # Quoted in the file: a bare off would be read as a boolean.
        assert static["autoDeployTrigger"] == "off"
    for name in (PROD_API, DEV_API):
        # Image services never auto-deploy, and the field has no effect on them.
        assert "autoDeployTrigger" not in _service(name)
        assert "autoDeploy" not in _service(name)


def test_deploy_only_the_secrets_are_entered_in_the_dashboard():
    assert _synced_by_hand(_service(PROD_API)) == SECRETS
    assert _synced_by_hand(_service(DEV_API)) == DEV_SECRETS
    assert _synced_by_hand(_service(PROD_APP)) == set()
    assert _synced_by_hand(_service(DEV_APP)) == set()
    for name, keys in ((PROD_API, SECRETS), (DEV_API, DEV_SECRETS)):
        backend_vars = _env_vars(_service(name))
        for key in keys:
            assert backend_vars[key] == {"key": key, "sync": False}


def test_deploy_backend_production_values_are_plain_values():
    values = _plain_values(_service(PROD_API))
    assert {key: values.get(key) for key in PLAIN_BACKEND_VALUES} == PLAIN_BACKEND_VALUES
    assert set(values) == set(PLAIN_BACKEND_VALUES) | {"CORS_ALLOWED_ORIGINS"}


def test_deploy_dev_backend_has_production_values_but_the_mock_ai():
    production = _plain_values(_service(PROD_API))
    dev = _plain_values(_service(DEV_API))
    expected = {
        key: value
        for key, value in production.items()
        if key not in REAL_AI_ONLY and key != "CORS_ALLOWED_ORIGINS"
    } | DEV_ONLY_AI
    assert {key: value for key, value in dev.items() if key != "CORS_ALLOWED_ORIGINS"} == expected
    assert not REAL_AI_ONLY & set(_env_vars(_service(DEV_API)))


def test_deploy_public_urls_point_at_the_other_service_of_the_same_environment():
    for backend_name, static_name in ((PROD_API, PROD_APP), (DEV_API, DEV_APP)):
        backend, static = _service(backend_name), _service(static_name)
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
    """Each backend starts with exactly the values in render.yaml plus its secrets."""
    for name, secrets, provider, origin in (
        (PROD_API, SECRETS, "openai-compatible", "https://winlog-app.onrender.com"),
        (DEV_API, DEV_SECRETS, "mock", "https://winlog-app-dev.onrender.com"),
    ):
        for key in list(os.environ):
            monkeypatch.delenv(key)
        for key, value in _plain_values(_service(name)).items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:placeholder@db.invalid/winlog")
        if "AI_API_KEY" in secrets:
            monkeypatch.setenv("AI_API_KEY", "placeholder")

        settings = Settings(_env_file=None)

        assert settings.ai_provider == provider
        assert settings.cors_allowed_origins == [origin]
        assert settings.demo_email == "demo@example.com"
        assert settings.otel_exporter_otlp_endpoint is None


def test_deploy_static_sites_are_the_same_build_with_their_own_api_url():
    production, dev = _service(PROD_APP), _service(DEV_APP)
    for field in ("buildCommand", "staticPublishPath", "routes", "branch", "autoDeployTrigger"):
        assert production[field] == dev[field]
    assert _plain_values(production)["NODE_VERSION"] == _plain_values(dev)["NODE_VERSION"]
    assert (
        set(_plain_values(production))
        == set(_plain_values(dev))
        == {
            "VITE_API_BASE_URL",
            "NODE_VERSION",
        }
    )


def test_deploy_static_site_publishes_the_build_with_the_pinned_node_and_spa_rewrite():
    static = _service(PROD_APP)
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
        ["sh", "-c", _service(PROD_APP)["buildCommand"]],
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


# --- CI and Deploy workflows (#39) ---------------------------------------------------------


def _on(workflow: dict) -> dict:
    # PyYAML reads the key `on` as the boolean True.
    return workflow.get("on", workflow.get(True))


def test_deploy_ci_runs_on_every_push_and_never_skips_a_job_on_main():
    assert CI["name"] == "CI"
    assert _on(CI) == {"push": {"branches": ["**"]}}
    # A skipped job does not fail a run, so no CI job may have a condition at all.
    assert [name for name, job in CI["jobs"].items() if "if" in job] == []
    assert "image" in CI["jobs"] and "full-system" in CI["jobs"]


def test_deploy_ci_builds_and_checks_the_image_but_pushes_nothing():
    image = CI["jobs"]["image"]
    build = _run_steps(image)
    assert "docker buildx build" in build and "--platform linux/amd64" in build
    # The context is backend/ (the last word of the build command).
    [build_step] = [step for step in image["steps"] if step.get("name") == "Build the image"]
    assert build_step["run"].split()[-1] == "backend"
    assert "--provenance=false" in build
    assert "-name '.env*'" in build and "-xdev" in build
    assert "org.opencontainers.image.source" in build
    # CI holds no registry rights and pushes nothing, on any branch.
    ci_text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "docker push" not in ci_text and "docker login" not in ci_text
    assert "packages: write" not in ci_text and "${{ secrets." not in ci_text
    assert CI["permissions"] == {"contents": "read"}
    # Only on main is the checked image kept for the Deploy workflow; the checks run everywhere.
    conditional = [step for step in image["steps"] if "if" in step]
    assert [step["if"] for step in conditional] == ["github.ref == 'refs/heads/main'"] * 2
    assert {step.get("uses") for step in conditional} == {None, "actions/upload-artifact@v7"}
    assert not [step for step in conditional if ".env" in step.get("run", "")]


def test_deploy_workflow_runs_only_after_a_passing_ci_run_on_main():
    assert _on(DEPLOY) == {
        "workflow_run": {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]},
        "push": {"branches-ignore": ["main"]},
    }
    condition = DEPLOY["jobs"]["publish"]["if"]
    for part in (
        "github.event_name == 'workflow_run'",
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert part in condition
    jobs = DEPLOY["jobs"]
    assert list(jobs) == ["publish", "deploy-dev", "deploy-production"]
    assert jobs["deploy-dev"]["needs"] == "publish"
    assert jobs["deploy-production"]["needs"] == ["publish", "deploy-dev"]
    # The image is the one CI built for the commit CI checked; nothing is built here.
    assert not re.search(r"docker (buildx )?build\b", DEPLOY_TEXT)
    assert DEPLOY["jobs"]["publish"]["env"]["SHA"] == "${{ github.event.workflow_run.head_sha }}"


def test_deploy_workflow_grants_registry_rights_only_to_jobs_that_push_or_tag():
    assert DEPLOY["permissions"] == {}
    jobs = DEPLOY["jobs"]
    assert jobs["publish"]["permissions"] == {"actions": "read", "packages": "write"}
    assert jobs["deploy-dev"]["permissions"] == {"packages": "write"}
    assert jobs["deploy-production"]["permissions"] == {"packages": "write"}
    # GHCR is reached with the workflow's own token, never a personal access token.
    assert DEPLOY_TEXT.count("docker login ghcr.io") == 2
    assert "GITHUB_TOKEN: ${{ github.token }}" in DEPLOY_TEXT


def test_deploy_jobs_use_their_environments_and_are_never_cancelled():
    jobs = DEPLOY["jobs"]
    assert "concurrency" not in DEPLOY
    assert jobs["deploy-dev"]["environment"]["name"] == "dev"
    assert jobs["deploy-production"]["environment"]["name"] == "production"
    assert jobs["deploy-dev"]["concurrency"] == {"group": "deploy-dev", "cancel-in-progress": False}
    assert jobs["deploy-production"]["concurrency"] == {
        "group": "deploy-production",
        "cancel-in-progress": False,
    }


def test_deploy_production_repeats_the_dev_steps_with_the_same_digest_and_commit():
    dev, production = DEPLOY["jobs"]["deploy-dev"], DEPLOY["jobs"]["deploy-production"]
    assert production["steps"] == dev["steps"]
    for key in ("SHA", "DIGEST"):
        assert production["env"][key] == dev["env"][key]
    assert dev["env"]["DIGEST"] == "${{ needs.publish.outputs.digest }}"
    expected = {
        "deploy-dev": ("dev", DEV_API, DEV_APP),
        "deploy-production": ("production", PROD_API, PROD_APP),
    }
    for job_name, (tag, api, app) in expected.items():
        env = DEPLOY["jobs"][job_name]["env"]
        assert (env["TAG"], env["API_SERVICE"], env["APP_SERVICE"]) == (tag, api, app)
        # The health wait checks the URLs render.yaml gives the services.
        assert env["API_URL"] == f"https://{api}.onrender.com"
        assert env["APP_URL"] == f"https://{app}.onrender.com"
        assert _service(api)["image"]["url"] == f"{IMAGE}:{tag}"


def test_deploy_github_holds_only_the_hook_secrets_and_never_prints_them():
    assert set(re.findall(r"secrets\.([A-Z_]+)", DEPLOY_TEXT)) == {
        "RENDER_API_DEPLOY_HOOK",
        "RENDER_APP_DEPLOY_HOOK",
    }
    scripts = _run_steps(DEPLOY["jobs"]["deploy-dev"]) + _run_steps(DEPLOY["jobs"]["publish"])
    assert "set -x" not in scripts and "curl -v" not in scripts and "--verbose" not in scripts
    assert not re.search(r"echo[^\n]*\$\{?(RENDER_|url\b)", scripts)
    # The hook URL reaches curl on its standard input, never on its command line.
    assert "curl --config -" in scripts


def test_deploy_dockerfile_links_the_image_to_the_repository():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8").splitlines()
    label = "LABEL org.opencontainers.image.source=https://github.com/KittyNiuNiu/winlog"
    assert label in dockerfile


# --- The deploy steps, run against a stand-in for Render's deploy hooks ---------------------

DIGEST = "sha256:" + "ab" * 32
SHA = "0123456789abcdef0123456789abcdef01234567"


class _Hooks(http.server.BaseHTTPRequestHandler):
    """Answers like Render's deploy hooks: the URL's key chooses the answer."""

    requests: list[str] = []

    def do_POST(self):  # noqa: N802 (the http.server method name)
        self.requests.append(self.path)
        if "key=fail" in self.path:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"deploy": {"id": "dep-stand-in"}}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def hooks():
    _Hooks.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hooks)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _Hooks.requests
    server.shutdown()


def _step(name: str) -> str:
    [step] = [s for s in DEPLOY["jobs"]["deploy-dev"]["steps"] if s.get("name") == name]
    return step["run"]


def _run_deploy_step(tmp_path: Path, name: str, secrets: dict[str, str], tag: str = "dev"):
    if not (shutil.which("bash") and shutil.which("curl")):
        pytest.skip("needs bash and curl")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    # docker: records its calls; `imagetools inspect` answers with the digest it was given.
    _fake_tool(bin_dir, "docker", f"""echo '{{"digest": "{DIGEST}"}}'""")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS": str(calls),
        "RUNNER_TEMP": str(tmp_path),
        "NO_PROXY": "127.0.0.1",
        "IMAGE": IMAGE,
        "ENVIRONMENT": tag,
        "TAG": tag,
        "API_SERVICE": "winlog-api-x",
        "APP_SERVICE": "winlog-app-x",
        "SHA": SHA,
        "DIGEST": DIGEST,
        **secrets,
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step(name)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, calls.read_text(encoding="utf-8").splitlines()


DEPLOY_STEP = "Deploy the backend image and the static site"


def test_deploy_step_deploys_the_digest_moves_the_tag_then_deploys_the_commit(tmp_path, hooks):
    base, requests = hooks
    secrets = {
        "RENDER_API_DEPLOY_HOOK": f"{base}/deploy/srv-api?key=secret-api-key",
        "RENDER_APP_DEPLOY_HOOK": f"{base}/deploy/srv-app?key=secret-app-key",
    }
    result, calls = _run_deploy_step(tmp_path, DEPLOY_STEP, secrets, tag="production")

    assert result.returncode == 0, result.stdout + result.stderr
    encoded = "ghcr.io%2Fkittyniuniu%2Fwinlog-backend%40sha256%3A" + "ab" * 32
    assert requests == [
        f"/deploy/srv-api?key=secret-api-key&imgURL={encoded}",
        f"/deploy/srv-app?key=secret-app-key&ref={SHA}",
    ]
    assert calls[0] == (
        f"docker buildx imagetools create --prefer-index=false --tag {IMAGE}:production "
        f"{IMAGE}@{DIGEST}"
    )
    assert calls[1].startswith(f"docker buildx imagetools inspect {IMAGE}:production")
    output = result.stdout + result.stderr
    assert "Render accepted the deploy of winlog-api-x (HTTP 200, deploy dep-stand-in)" in output
    for secret in ("secret-api-key", "secret-app-key", base):
        assert secret not in output


def test_deploy_step_fails_on_a_hook_error_without_printing_the_url(tmp_path, hooks):
    base, requests = hooks
    secrets = {
        "RENDER_API_DEPLOY_HOOK": f"{base}/deploy/srv-api?key=fail-secret",
        "RENDER_APP_DEPLOY_HOOK": f"{base}/deploy/srv-app?key=secret-app-key",
    }
    result, calls = _run_deploy_step(tmp_path, DEPLOY_STEP, secrets)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "deploy hook of winlog-api-x (RENDER_API_DEPLOY_HOOK) failed with HTTP 404" in output
    assert "fail-secret" not in output and base not in output
    # Nothing more is deployed, and the tag stays where it was.
    assert len(requests) == 1 and calls == []


def test_deploy_step_fails_when_render_does_not_answer(tmp_path):
    secrets = {
        "RENDER_API_DEPLOY_HOOK": "http://127.0.0.1:9/deploy/srv-api?key=secret-api-key",
        "RENDER_APP_DEPLOY_HOOK": "http://127.0.0.1:9/deploy/srv-app?key=secret-app-key",
    }
    result, calls = _run_deploy_step(tmp_path, DEPLOY_STEP, secrets)

    assert result.returncode != 0
    assert "failed with no answer" in result.stdout
    assert "secret-api-key" not in result.stdout + result.stderr
    assert calls == []


@pytest.mark.parametrize("missing", ["RENDER_API_DEPLOY_HOOK", "RENDER_APP_DEPLOY_HOOK"])
def test_deploy_missing_hook_secret_fails_and_names_it(tmp_path, missing):
    secrets = {
        "RENDER_API_DEPLOY_HOOK": "https://hooks.invalid/a?key=secret-a",
        "RENDER_APP_DEPLOY_HOOK": "https://hooks.invalid/b?key=secret-b",
        missing: "",
    }
    result, _ = _run_deploy_step(tmp_path, "Check the deploy hook secrets", secrets)

    assert result.returncode != 0
    assert f"The secret {missing} is not set in the GitHub environment 'dev'" in result.stdout
    assert "secret-a" not in result.stdout and "secret-b" not in result.stdout

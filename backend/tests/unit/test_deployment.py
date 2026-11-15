"""Deployment on Render: dev and production (issues #38, #39 and #102, product-spec.md §7.7,
§10.2 and §10.4).

Checks the Render Blueprint (`render.yaml`), the CI and Deploy workflows, the backend's start
script (`start.sh`) and what the backend image contains. The start script, the static site's
build command and the deploy steps run here with stand-ins for alembic, python, uvicorn, node,
npm and docker, and with local HTTP servers in place of Render's deploy hooks and of the
deployed services, so no database, server, registry or network is needed. The real image is
built and checked by CI's Backend image job, and the real start by its Full system job.
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
import time
from pathlib import Path

import pytest
import yaml

from app import git_commit
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
    "DATABASE_QUERY_TIMEOUT_SECONDS": "10",
    "REQUEST_BODY_MAX_BYTES": "262144",
    "HSTS_MAX_AGE_SECONDS": "31536000",
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


def _guide_section(heading: str) -> str:
    guide = (ROOT / "ops" / "deployment.md").read_text(encoding="utf-8")
    start = guide.index(f"\n{heading}\n")
    end = guide.find("\n## ", start + 1)
    return guide[start : end if end != -1 else len(guide)]


def _flat(text: str) -> str:
    """The text with every run of whitespace as one space, so line wrapping does not matter."""
    return " ".join(text.split())


def _numbered_steps(text: str) -> dict[int, str]:
    """The top-level numbered steps of a guide passage (`1. **…`), by number."""
    parts = re.split(r"^ ?(\d+)\. (?=\*\*)", text, flags=re.MULTILINE)
    pairs = zip(parts[1::2], parts[2::2], strict=True)
    return {int(number): _flat(body) for number, body in pairs}


def test_deploy_guide_migration_turns_production_auto_deploy_off_before_the_merge():
    # Until the migration, winlog-api and winlog-app still had #38's checksPass, so Render
    # would have deployed the merge commit to production without approval and without dev.
    migration = _guide_section("## The one-off migration of the live production (#39)")
    before_merge, after_merge = migration.split("**The merge into `main`.**")
    first_step = before_merge.split("\n1. ")[1].split("\n2. ")[0]
    assert "`winlog-api`" in first_step and "`winlog-app`" in first_step
    assert "**Auto-Deploy** → **Off**" in first_step
    # Auto Sync is turned off before the merge too, but after Auto-Deploy.
    assert "**Auto Sync** to **No**" in before_merge.split("\n2. ")[1]
    # Nothing else was merged until the Blueprint sync, the last Render step, was done.
    assert "nothing else was merged into `main` until step 15 was done" in _flat(after_merge)
    assert "\n15. **Render: Manual Sync of the Blueprint.**" in after_merge
    # The steps are numbered 1 to 16 in order, with no gap.
    numbers = [int(n) for n in re.findall(r"^ ?(\d+)\. \*\*", migration, flags=re.MULTILINE)]
    assert numbers == list(range(1, 17))


def test_deploy_guide_migration_record_matches_what_was_done():
    # #39 section B, done on 2026-11-14 with the product owner's Option A: the Blueprint sync
    # was refused while :dev and :production did not exist, so dev was created by hand first.
    migration = _guide_section("## The one-off migration of the live production (#39)")
    flat = _flat(migration)
    assert "**Done on 14 November 2026.**" in flat
    steps = _numbered_steps(migration)
    # Steps 1 to 6 are the ones that worked as written; set-up from scratch reuses 3 to 5.
    assert "**GitHub: create the environment `dev`.**" in steps[3]
    assert "**GitHub: create the environment `production`.**" in steps[4]
    assert "**GHCR: make the package public.**" in steps[5]
    assert "**Neon: create the dev project.**" in steps[6]
    assert '"backend images not found"' in flat
    # Dev first, by hand, from the image the pipeline published for the merge commit.
    assert "create `winlog-api-dev`" in steps[7]
    assert re.search(r"winlog-backend:sha-[0-9a-f]{40}", steps[7])
    assert "pre-fills the **Name**" in steps[7]
    assert "create `winlog-app-dev`" in steps[8] and "**Auto-Deploy** **Off**" in steps[8]
    assert "the dev hooks" in steps[9]
    assert "**Re-run failed jobs**" in steps[10]
    assert "Events" in steps[11] and "named the digest" in steps[11]
    # Then production's source, to the digest dev runs, before its hooks and the approval.
    assert "**Update Source**" in steps[12] and "winlog-backend@sha256:" in steps[12]
    assert "the production hooks" in steps[13]
    assert "**Approve.**" in steps[14] and "`:production`" in steps[14]
    # The sync came last and took over the services Render already had.
    assert "Manual Sync" in steps[15]
    assert steps[15].count("**associated** (not new)") == 2
    assert "`winlog-app`: not listed" in steps[15]
    assert "freeze ended" in steps[16]
    # The one accepted deviation is stated, with whose decision it was.
    deviation = flat.split("**The one accepted deviation.**")[1].split("**Before the")[0]
    assert "started by hand" in deviation and "product owner's decision" in deviation
    # What turned out wrong is gone: the sync applying first, and first deploys that fail.
    assert "**fails**" not in migration
    guide = (ROOT / "ops" / "deployment.md").read_text(encoding="utf-8")
    assert "keeps the current value" not in _flat(guide)


def test_deploy_guide_set_up_creates_the_services_before_the_blueprint():
    setup = _guide_section("## Set up from scratch")
    dev = setup.split("### 4. Render: the dev services")[1].split("\n### 5.")[0]
    production = setup.split("### 5. Render: the production services and the approval\n")[1]
    production = production.split("\n### 6.")[0]
    blueprint = setup.split("### 6. Render: the Blueprint")[1]
    flat = _flat(setup)
    assert "A Blueprint sync is refused while an image tag it names does not exist" in flat
    # Dev first, from the sha-<commit> image, with the pre-filled name overwritten.
    assert "winlog-backend:sha-<commit>" in dev
    assert "**Overwrite the pre-filled Name with `winlog-api-dev` before" in _flat(dev)
    assert "**Re-run failed jobs**" in _flat(dev) and "do not approve it yet" in _flat(dev)
    # Production only after dev has been checked; the approval creates the tag.
    assert production.lstrip().startswith("Only after dev has been checked")
    assert "creates `:production`" in _flat(production)
    # The Blueprint last, once both tags exist, and only if it takes over the services.
    assert blueprint.lstrip().startswith("Now that both tags exist")
    assert "not observed" in _flat(blueprint)
    assert "**do not deploy the Blueprint**" in _flat(blueprint)
    # The URL comes from the name the service had when it was created.
    urls = _flat(_guide_section("## The public URLs"))
    assert "pre-fills the **Name**" in urls
    assert "renaming the service later does not change it" in urls


def _hand_entered_keys(step: str, service: dict) -> set[str]:
    return set(re.findall(r"`([A-Z_]+)`", step)) & set(_env_vars(service))


def test_deploy_guide_set_up_hand_entered_values_and_backend_defaults_give_render_yaml():
    """A backend created by hand runs with render.yaml's values before the Blueprint sync."""
    setup = _guide_section("## Set up from scratch")
    dev_step = setup.split("### 4. Render: the dev services")[1].split("\n2. ")[0]
    production_step = setup.split("### 5. Render: the production services")[1].split("\n2. ")[0]
    for name, step in ((DEV_API, dev_step), (PROD_API, production_step)):
        service = _service(name)
        entered = _hand_entered_keys(step, service)
        assert _synced_by_hand(service) <= entered
        for key, value in _plain_values(service).items():
            if key in entered:
                continue
            default = Settings.model_fields[key.lower()].default
            assert str(default) == value, f"{name}: enter {key} by hand, or change its default"


def test_deploy_guide_says_the_wait_passes_only_when_both_services_name_the_run_commit():
    # Until #102 the wait accepted any 200 and passed on the previous deploys (2026-11-14).
    pipeline = _guide_section("## The pipeline")
    steps = pipeline.split("\n   2. **Deploy to dev**")[1]
    dev, production = (_flat(part) for part in steps.split("\n   3. **Deploy to production**"))
    production = production.split("A deploy hook that does not answer 2xx")[0]
    assert (
        "**The wait passes only when `GET https://winlog-api-dev.onrender.com/health` and "
        "`https://winlog-app-dev.onrender.com/version.json` both name the run's commit**" in dev
    )
    assert "within 15 minutes" in dev and "polls every 10 seconds" in dev
    assert "A 200 alone does not count" in dev
    assert (
        "Until #102 the wait accepted any 200 and passed on the previous deploys (on 14 November "
        "2026, after 40 seconds in dev and 1 second in production)." in dev
    )
    assert "the job fails, and the run's production step is not offered" in dev
    assert "[When the wait fails](#when-the-wait-fails)" in dev
    assert (
        "`https://winlog-api.onrender.com/health` and "
        "`https://winlog-app.onrender.com/version.json` name the run's commit, within 15 minutes"
        in production
    )
    assert "[When the wait fails](#when-the-wait-fails)" in production
    flat = _flat(pipeline)
    # The old wording is gone.
    assert "can pass on the previous deploy" not in flat
    assert "This wait does not show that the new deploy is live" not in flat
    assert "up to 10 minutes" not in flat
    cannot_see = flat.split("**What the pipeline cannot see.**")[1].split("**One deploy")[0]
    assert "The wait sees only that commit." in cannot_see
    assert "deploy status or logs, why a deploy failed, or which digest runs" in cannot_see
    assert (
        "Two images of the same commit look the same to the wait, and only a CI re-run of that "
        "commit builds a second one." in cannot_see
    )
    guide = _flat((ROOT / "ops" / "deployment.md").read_text(encoding="utf-8"))
    assert "The deploy jobs wait up to 15 minutes" in guide
    assert "wait up to 10 minutes" not in guide


def test_deploy_guide_says_what_to_do_when_the_wait_fails():
    section = _guide_section("## The pipeline").split("\n### When the wait fails\n")[1]
    section = section.split("\n### ")[0]
    dev = _flat(section.split("- **In dev:**")[1].split("- **In production:**")[0])
    production = _flat(section.split("- **In production:**")[1])
    assert "the run's production step is not offered" in dev
    assert "**Events** and **Logs**" in dev and "slower than 15 minutes" in dev
    assert "Render keeps the previous deploy live" in dev
    assert "a new commit on `main` deploys again" in dev
    assert "**Re-run failed jobs** in the run deploys the same commit and digest again" in dev
    assert "`:production` already points to the new digest" in production
    link = "[Promote an earlier image again](#promote-an-earlier-image-again-preferred)"
    assert link in production
    assert "a deploy that names no image would now pull the failed image" in production
    assert "nothing more is needed once **Events** show it live" in production


def test_deploy_guide_promotion_keeps_the_events_check_for_a_new_reason():
    promote = _guide_section("## Promote to production")
    check_dev = _flat(promote.split("\n3. ")[1].split("\n4. ")[0])
    # The checks stay the same; only the reason changes.
    reason = "The green **Deploy to dev** job shows that both dev services answer with this commit"
    assert reason in check_dev
    assert "**Events** also show the digest" in check_dev
    assert "`winlog-api-dev` → **Events**: the deploy of exactly this digest" in check_dev
    assert "`winlog-app-dev` → **Events**: the deploy of this commit is live" in check_dev
    assert "**Try the demo**" in check_dev
    assert "can pass on the previous deploy" not in check_dev
    watch = _flat(promote.split("\n5. ")[1])
    assert "It finishes only when both production services answer with this commit" in watch
    assert "**Events**, which also show the digest" in watch
    # The job's summary says what the wait saw, names commit and digest, and points to Events.
    summary = _step("Summary")
    assert "The backend and the static site answered with this commit" in summary
    assert "The production step of this run deploys exactly this commit and this digest." in summary
    assert "check that the Events of" in summary and "$DIGEST" in summary and "$SHA" in summary


def test_deploy_guide_approve_only_the_newest_production_step():
    rule = (
        "**Approve only the newest run's waiting production step, and reject every older "
        "production step that is still waiting.**"
    )
    exception = (
        "The one deliberate exception is [Promote an earlier image again]"
        "(#promote-an-earlier-image-again-preferred): a re-run of an earlier run's production "
        "step, on purpose."
    )
    older = "would send production an older image than the one dev runs"
    holds = "holds the `deploy-production` concurrency group until it is approved or rejected"
    promote = _flat(_guide_section("## Promote to production").split("\n1. ")[0])
    assert rule in promote and exception in promote and older in promote and holds in promote
    pipeline = _flat(_guide_section("## The pipeline"))
    one_at_a_time = pipeline.split("**One deploy per environment at a time.**")[1]
    one_at_a_time = one_at_a_time.split("**Deploys that name no image.**")[0]
    assert rule in one_at_a_time and exception in one_at_a_time and older in one_at_a_time
    for phrase in (
        f"{holds}, and so blocks every later run's production step",
        "GitHub cancels only a *pending* job in the group, not the waiting one",
        "run 43653076300's production step waited unapproved overnight",
        "run 43654635673's production job was pending behind it, and GitHub cancelled it when run "
        "43692182612's arrived",
        "run 43692182612's production step stayed blocked until 43653076300's was rejected",
    ):
        assert phrase in one_at_a_time, phrase
    # The production job's concurrency comment says the same.
    assert "so approve only the newest\n    # run's production step" in DEPLOY_TEXT


def test_deploy_guide_proof_paragraph_is_the_record_of_the_proof_run():
    migration = _guide_section("## The one-off migration of the live production (#39)")
    proof = _flat(migration.split("**The proof (#39, section B)**")[1])
    for phrase in (
        "The proof run was the merge of PR #101 (commit `ff76738`, 14 November 2026)",
        "CI run 43642206653 finished at 21:26:37 UTC.",
        "In Deploy run 43642838583, both dev deploys started at about 21:27 UTC, with the digest "
        "`sha256:c2816c1c…` and the commit `ff76738`.",
        "Production showed no new deploy until the approval at about 21:36 UTC.",
        "Then `winlog-api` deployed the same digest and `winlog-app` the same commit.",
        "https://github.com/KittyNiuNiu/winlog/issues/39#issuecomment-6884765919",
    ):
        assert phrase in proof, phrase
    # A record in the past tense, no longer a list of what to report.
    assert "report" not in proof
    # Step 10 of the record still links to the explanation of the old wait.
    step_10 = _numbered_steps(migration)[10]
    assert "on the deploys that were already live ([The pipeline](#the-pipeline))" in step_10
    assert "Until #102 the wait accepted any 200" in _flat(_guide_section("## The pipeline"))


def test_deploy_guide_live_checks_show_the_commit_of_the_deploy_run():
    checks = _flat(_guide_section("## Live checks after a deploy"))
    commit = checks.split("The commit both services name (#102")[1]
    assert (
        "After a dev deploy, `curl -sS https://winlog-api-dev.onrender.com/health` and "
        "`curl -sS https://winlog-app-dev.onrender.com/version.json` both show the commit of "
        "that Deploy run" in commit
    )
    assert (
        "the same check runs on `https://winlog-api.onrender.com/health` and "
        "`https://winlog-app.onrender.com/version.json`" in commit
    )


def _comment_text(text: str) -> str:
    """The text of YAML comment lines, as one line."""
    return _flat(" ".join(line.strip().removeprefix("#") for line in text.splitlines()))


def test_deploy_workflow_comments_describe_the_new_wait():
    header = _comment_text(DEPLOY_TEXT.split("\nname: Deploy\n")[0])
    assert "waits until both answer with that commit (#102)" in header
    assert "If they do not name the commit within WAIT_TIMEOUT_SECONDS (15 minutes)" in header
    assert (
        "No AI calls: the jobs call only Render's deploy hooks, GHCR, the backend's GET /health "
        "and the static site's / and /version.json." in header
    )
    assert "does not prove which version is live" not in DEPLOY_TEXT
    step = DEPLOY_TEXT.split("- name: Wait until the backend and the static site answer\n")[1]
    comment = _comment_text(step.split("run: |")[0])
    assert "Passes only when both services answer with the run's commit (#102)" in comment
    assert "a query string that differs on each request" in comment
    assert "never a hook" in comment


def test_deploy_guide_blueprint_syncs_stay_manual_and_explain_the_backends_trigger():
    syncs = _flat(_guide_section("## Blueprint syncs"))
    assert "**Auto Sync stays No, and both static sites' Auto-Deploy stays Off.**" in syncs
    assert "**Manual Sync**" in syncs
    assert "refused as a whole while an image tag it names does not exist" in syncs
    # The sync set "commit" on the image services, which render.yaml leaves unset.
    assert 'set both backends to "commit". This is harmless.' in syncs
    # Every sync so far listed three changes render.yaml does not make (#102); #109 follows up.
    repeated = syncs.split("**Three changes come back in every sync.**")[1]
    for phrase in (
        "Both Manual Syncs so far, on 14 and 15 November 2026, listed three changes that "
        "`render.yaml` does not make",
        '"auto-deploy trigger → commit" for `winlog-api` and `winlog-api-dev`',
        '"static publish path → `./frontend/dist`" for `winlog-app-dev`',
        "They are harmless.",
        "`./frontend/dist` is the directory the site already publishes",
        "A sync review does not stop on these three. Every other change in the list is read as "
        "before.",
        "stops listing them is #109.",
    ):
        assert phrase in repeated, phrase
    assert _service(DEV_APP)["staticPublishPath"] == "./frontend/dist"
    for name in (PROD_API, DEV_API):
        assert "autoDeployTrigger" not in _service(name)
    # Every other passage that syncs the Blueprint points here.
    guide = (ROOT / "ops" / "deployment.md").read_text(encoding="utf-8")
    assert "migration step 14" not in guide
    assert guide.count("[Blueprint syncs](#blueprint-syncs)") >= 4


def test_deploy_guide_by_hand_hook_call_keeps_the_url_off_the_command_line():
    section = _guide_section("### When GitHub Actions is down")
    [block] = re.findall(r"```\n(.*?)```", section, flags=re.DOTALL)
    assert "read -rs HOOK" in block and "unset HOOK" in block
    # The URL goes to curl through a builtin on its standard input, as in the pipeline.
    assert "--config -" in block
    curl_lines = [line for line in block.splitlines() if "curl " in line]
    assert curl_lines and not [line for line in curl_lines if "HOOK" in line]


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


def _image_step(name: str) -> dict:
    [step] = [step for step in CI["jobs"]["image"]["steps"] if step.get("name") == name]
    return step


IMAGE_COMMIT_CHECK = "The image records its commit"


def test_deploy_ci_passes_the_commit_into_the_image_and_checks_it():
    # GET /health names the commit the image was built from, and the Deploy workflow waits for
    # it (#102). CI passes the same commit as the revision label into the build.
    steps = CI["jobs"]["image"]["steps"]
    build = _image_step("Build the image")
    assert '--label "org.opencontainers.image.revision=$GITHUB_SHA"' in build["run"]
    assert '--build-arg "GIT_COMMIT=$GITHUB_SHA"' in build["run"]
    check = _image_step(IMAGE_COMMIT_CHECK)
    # On every branch, right after the build, without a database: the backend's own code says
    # what /health would report.
    assert "if" not in check
    assert steps.index(check) == steps.index(build) + 1
    assert (
        "docker run --rm --entrypoint python winlog-backend:ci -c "
        "'from app.git_commit import recorded_commit; print(recorded_commit())'" in check["run"]
    )
    assert '"$recorded" != "$GITHUB_SHA"' in check["run"]
    assert '"$revision" != "$GITHUB_SHA"' in check["run"]


def _run_image_commit_check(tmp_path: Path, recorded: str, revision: str, sha: str):
    """The CI check, with a stand-in for docker that answers like the built image."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    calls = tmp_path / "calls.log"
    calls.touch()
    _fake_tool(
        bin_dir,
        "docker",
        f'case "$1" in run) echo "{recorded}" ;; inspect) echo "{revision}" ;; esac',
    )
    return subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            _image_step(IMAGE_COMMIT_CHECK)["run"],
        ],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALLS": str(calls), "GITHUB_SHA": sha},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_deploy_ci_image_commit_check_passes_only_for_exactly_the_built_commit(tmp_path):
    other = "fedcba9876543210fedcba9876543210fedcba98"
    for case, (recorded, revision, passes) in {
        "same": (SHA, SHA, True),
        "none": ("None", SHA, False),
        "another": (other, SHA, False),
        "another-label": (SHA, other, False),
    }.items():
        result = _run_image_commit_check(tmp_path / case, recorded, revision, SHA)
        assert (result.returncode == 0) == passes, case
        if not passes:
            assert f"::error::The image records commit '{recorded}'" in result.stdout, case


def test_deploy_dockerfile_records_the_commit_after_the_dependency_install():
    lines = (BACKEND / "Dockerfile").read_text(encoding="utf-8").splitlines()
    install = lines.index("RUN uv sync --locked --no-dev --no-cache")
    argument = lines.index("ARG GIT_COMMIT=")
    record = lines.index("RUN printf '%s' \"$GIT_COMMIT\" > /app/git-commit")
    # After the dependency install and the code, so a new commit reinstalls nothing.
    assert install < argument < record
    assert argument > max(i for i, line in enumerate(lines) if line.startswith("COPY "))
    # The file app/git_commit.py reads: next to the app package, /app in the image.
    assert lines.index("WORKDIR /app") < install
    assert git_commit.GIT_COMMIT_FILE == BACKEND / "git-commit"
    # Build metadata, not configuration: no environment variable carries the commit.
    assert not [line for line in lines if line.startswith("ENV") and "COMMIT" in line]
    for config in ("render.yaml", "docker-compose.yml", ".env.example"):
        assert "COMMIT" not in (ROOT / config).read_text(encoding="utf-8"), config
    assert "COMMIT" not in (BACKEND / "start.sh").read_text(encoding="utf-8")


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


# --- The wait, run against stand-ins for the backend and the static site (#102) -------------

WAIT_STEP = "Wait until the backend and the static site answer"
OLD_SHA = "fedcba9876543210fedcba9876543210fedcba98"
WAIT_TIMEOUT_SECONDS = 900
WAIT_INTERVAL_SECONDS = 10


def _json(body: object) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(body).encode()


def _health(commit: str | None) -> tuple[int, str, bytes]:
    return _json({"status": "ok", "database": "ok", "commit": commit})


def _version(commit: str | None) -> tuple[int, str, bytes]:
    return _json({"commit": commit})


# What the live services answered before the first deploy after #102: /health without a
# commit, and /version.json with index.html, through the static sites' SPA rewrite.
HEALTH_WITHOUT_COMMIT = _json({"status": "ok", "database": "ok"})
INDEX_HTML = (200, "text/html", b"<!doctype html>\n<title>Winlog</title>\n")
DATABASE_UNREACHABLE = (
    503,
    "application/json",
    json.dumps(
        {"code": "database_unreachable", "message": "The database is not reachable."}
    ).encode(),
)


class _Service(http.server.BaseHTTPRequestHandler):
    """A stand-in for a deployed service. Each path has a list of answers, one per request in
    turn; the last one repeats. Every request is recorded as (path, query)."""

    def do_GET(self):  # noqa: N802 (the http.server method name)
        path, _, query = self.path.partition("?")
        self.server.requests.append((path, query))
        answers = self.server.answers.get(path, [(404, "text/plain", b"Not Found")])
        status, content_type, body = answers.pop(0) if len(answers) > 1 else answers[0]
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def services():
    """Starts stand-ins: services({path: [answers]}) returns the server; its URL is _url()."""
    servers = []

    def start(answers: dict[str, list]):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Service)
        server.answers = {path: list(items) for path, items in answers.items()}
        server.requests = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _url(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def _paths(server, path: str) -> list[tuple[str, str]]:
    return [request for request in server.requests if request[0] == path]


def _run_wait(
    tmp_path: Path, api_url: str, app_url: str, timeout_seconds: int = 20
) -> tuple[subprocess.CompletedProcess, float]:
    """Runs the wait as GitHub runs a step, with a short time limit and poll interval."""
    if not (shutil.which("bash") and shutil.which("curl") and shutil.which("python3")):
        pytest.skip("needs bash, curl and python3")
    env = {
        "PATH": os.environ["PATH"],
        "RUNNER_TEMP": str(tmp_path),
        "NO_PROXY": "127.0.0.1",
        "API_SERVICE": "winlog-api-x",
        "APP_SERVICE": "winlog-app-x",
        "API_URL": api_url,
        "APP_URL": app_url,
        "SHA": SHA,
        "WAIT_TIMEOUT_SECONDS": str(timeout_seconds),
        "WAIT_INTERVAL_SECONDS": "0.05",
    }
    started = time.monotonic()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step(WAIT_STEP)],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 30,
    )
    return result, time.monotonic() - started


def _changes(result: subprocess.CompletedProcess, service: str) -> list[str]:
    """The log lines about one service, without their "[+<seconds> s] " prefix."""
    lines = []
    for line in result.stdout.splitlines():
        match = re.fullmatch(r"\[\+\d+ s\] (.*)", line)
        if match and match.group(1).startswith(f"{service}: "):
            lines.append(match.group(1))
    return lines


def _errors(result: subprocess.CompletedProcess) -> list[str]:
    return [line for line in result.stdout.splitlines() if line.startswith("::error::")]


def test_deploy_wait_passes_when_both_answer_with_the_run_commit_at_once(tmp_path, services):
    api = services({"/health": [_health(SHA)]})
    app = services({"/": [INDEX_HTML], "/version.json": [_version(SHA)]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _changes(result, "winlog-api-x") == [
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 200, commit {SHA}"
    ]
    assert _changes(result, "winlog-app-x") == [
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 200; "
        f"GET {_url(app)}/version.json -> HTTP 200, commit {SHA}"
    ]
    # On success, the log names both URLs and the commit.
    last = result.stdout.splitlines()[-1]
    assert f"both services answer with commit {SHA}" in last
    assert f"GET {_url(api)}/health" in last and f"GET {_url(app)}/version.json" in last
    assert _errors(result) == []
    # Each service is checked until it matches, and then no longer.
    assert len(_paths(api, "/health")) == 1
    assert len(_paths(app, "/")) == len(_paths(app, "/version.json")) == 1


def test_deploy_wait_passes_only_after_both_name_the_commit_and_logs_each_change_once(
    tmp_path, services
):
    # The first deploy after #102: the previous deploys name no commit, and neither static site
    # has a version.json yet. The backend's new deploy goes live first, the static site later.
    api = services({"/health": [HEALTH_WITHOUT_COMMIT] * 3 + [_health(SHA)]})
    app = services({"/": [INDEX_HTML], "/version.json": [INDEX_HTML] * 6 + [_version(SHA)]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _changes(result, "winlog-api-x") == [
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 200, no commit",
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 200, commit {SHA}",
    ]
    assert _changes(result, "winlog-app-x") == [
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 200; "
        f"GET {_url(app)}/version.json -> HTTP 200, no commit (the body is not JSON)",
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 200; "
        f"GET {_url(app)}/version.json -> HTTP 200, commit {SHA}",
    ]
    # The backend matched after 4 polls and was not asked again; the static site after 7.
    assert len(_paths(api, "/health")) == 4
    versions = _paths(app, "/version.json")
    assert len(versions) == len(_paths(app, "/")) == 7
    # Each request for /version.json has its own query string, so no CDN copy can answer it.
    queries = [query for _, query in versions]
    assert all(queries) and len(set(queries)) == len(queries)
    assert [query for _, query in _paths(api, "/health")] == [""] * 4
    assert result.stdout.splitlines()[-1].startswith("After ")


def test_deploy_wait_keeps_polling_while_the_backend_answers_503(tmp_path, services):
    api = services({"/health": [DATABASE_UNREACHABLE] * 4 + [_health(SHA)]})
    app = services({"/": [INDEX_HTML], "/version.json": [_version(SHA)]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _changes(result, "winlog-api-x") == [
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 503, no commit",
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 200, commit {SHA}",
    ]
    assert len(_paths(api, "/health")) == 5


def test_deploy_wait_fails_when_the_static_site_keeps_an_older_commit(tmp_path, services):
    api = services({"/health": [_health(SHA)]})
    app = services({"/": [INDEX_HTML], "/version.json": [_version(OLD_SHA)]})

    result, elapsed = _run_wait(tmp_path, _url(api), _url(app), timeout_seconds=2)

    assert result.returncode != 0
    # Not before the time limit (the shell counts whole seconds).
    assert elapsed >= 1
    [error] = _errors(result)
    assert error.startswith(
        f"::error::After 2 seconds, not every service answers with commit {SHA}."
    )
    assert (
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 200; "
        f"GET {_url(app)}/version.json -> HTTP 200, commit {OLD_SHA}; expected commit {SHA}."
    ) in error
    # The backend matched, so the error does not name it.
    assert "winlog-api-x" not in error and _url(api) not in error
    assert len(_paths(api, "/health")) == 1
    # The log has one line for the static site: what it answered never changed.
    assert len(_changes(result, "winlog-app-x")) == 1
    assert len(_paths(app, "/version.json")) > 2


def test_deploy_wait_fails_and_names_both_when_neither_matches(tmp_path, services):
    api = services({"/health": [HEALTH_WITHOUT_COMMIT]})
    app = services({"/": [INDEX_HTML], "/version.json": [INDEX_HTML]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app), timeout_seconds=2)

    assert result.returncode != 0
    [error] = _errors(result)
    assert (
        f"winlog-api-x: GET {_url(api)}/health -> HTTP 200, no commit; expected commit {SHA}."
        in error
    )
    assert (
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 200; GET {_url(app)}/version.json -> HTTP 200, "
        f"no commit (the body is not JSON); expected commit {SHA}."
    ) in error


@pytest.mark.parametrize(
    ("health", "expected"),
    [
        pytest.param(_health(None), "HTTP 200, no commit", id="commit-null"),
        pytest.param(_health(OLD_SHA), f"HTTP 200, commit {OLD_SHA}", id="another-commit"),
        pytest.param(_health(SHA.upper()), "HTTP 200, no valid commit", id="upper-case"),
        pytest.param(_health(SHA[:7]), "HTTP 200, no valid commit", id="short-sha"),
        pytest.param(_health(7), "HTTP 200, no valid commit", id="not-a-string"),
        pytest.param(
            _health("\n::warning::injected"), "HTTP 200, no valid commit", id="log-command"
        ),
        pytest.param(_json([SHA]), "HTTP 200, no commit", id="json-array"),
        pytest.param(
            (200, "application/json", b'{"commit": "' + SHA.encode()),
            "HTTP 200, no commit (the body is not JSON)",
            id="cut-off-json",
        ),
        pytest.param(
            (500, "application/json", json.dumps({"commit": SHA}).encode()),
            "HTTP 500, no commit",
            id="status-500-with-commit",
        ),
        pytest.param((301, "text/plain", b""), "HTTP 301, no commit", id="redirect"),
    ],
)
def test_deploy_wait_treats_every_other_backend_answer_as_not_live_yet(
    tmp_path, services, health, expected
):
    api = services({"/health": [health]})
    app = services({"/": [INDEX_HTML], "/version.json": [_version(SHA)]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app), timeout_seconds=1)

    assert result.returncode != 0
    [error] = _errors(result)
    assert f"winlog-api-x: GET {_url(api)}/health -> {expected}; expected commit {SHA}." in error
    # Nothing from a body reaches the log but a valid commit.
    assert "injected" not in result.stdout + result.stderr
    assert not [line for line in result.stdout.splitlines() if line.startswith("::warning")]


def test_deploy_wait_fails_when_a_service_does_not_answer(tmp_path, services):
    app = services({"/": [INDEX_HTML], "/version.json": [_version(SHA)]})
    # Nothing listens on port 9 here, as in test_deploy_step_fails_when_render_does_not_answer.
    result, _ = _run_wait(tmp_path, "http://127.0.0.1:9", _url(app), timeout_seconds=1)

    assert result.returncode != 0
    [error] = _errors(result)
    assert "winlog-api-x: GET http://127.0.0.1:9/health -> no answer, no commit;" in error
    assert "winlog-app-x" not in error


def test_deploy_wait_needs_the_static_site_page_too(tmp_path, services):
    api = services({"/health": [_health(SHA)]})
    app = services({"/": [(404, "text/plain", b"Not Found")], "/version.json": [_version(SHA)]})

    result, _ = _run_wait(tmp_path, _url(api), _url(app), timeout_seconds=1)

    assert result.returncode != 0
    [error] = _errors(result)
    assert (
        f"winlog-app-x: GET {_url(app)}/ -> HTTP 404; "
        f"GET {_url(app)}/version.json -> HTTP 200, commit {SHA}; expected commit {SHA}."
    ) in error


def test_deploy_wait_calls_only_the_public_urls_and_prints_no_secret():
    step = [s for s in DEPLOY["jobs"]["deploy-dev"]["steps"] if s.get("name") == WAIT_STEP][0]
    # No secret reaches the step: it reads only the job's env, with the public URLs.
    assert "env" not in step
    assert "secrets." not in step["run"] and "RENDER_" not in step["run"]
    curl_lines = [line for line in step["run"].splitlines() if "curl " in line]
    assert [re.findall(r'"([^"]+)"', line)[-1] for line in curl_lines] == ["$1", "$APP_URL/"]
    calls = re.findall(r'fetch "([^"]+)"', step["run"])
    assert calls == ["$API_URL/health", "$APP_URL/version.json?wait=$(date +%s%N)"]
    assert "set -x" not in step["run"] and "--verbose" not in step["run"]


def test_deploy_wait_has_the_same_time_limit_and_poll_interval_in_both_jobs():
    for name in ("deploy-dev", "deploy-production"):
        job = DEPLOY["jobs"][name]
        assert job["env"]["WAIT_TIMEOUT_SECONDS"] == WAIT_TIMEOUT_SECONDS == 15 * 60, name
        assert job["env"]["WAIT_INTERVAL_SECONDS"] == WAIT_INTERVAL_SECONDS, name
        # Room for the whole wait after the hooks: two hook calls of up to 60 s each, the tag
        # move, and the last round of polls (three requests of up to 30 s each).
        assert job["timeout-minutes"] * 60 >= WAIT_TIMEOUT_SECONDS + 5 * 60, name
    dev, production = DEPLOY["jobs"]["deploy-dev"], DEPLOY["jobs"]["deploy-production"]
    assert dev["timeout-minutes"] == production["timeout-minutes"]
    # The step reads them from the job's env, so the tests above can shorten them.
    wait = _step(WAIT_STEP)
    assert "deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))" in wait
    assert 'sleep "$WAIT_INTERVAL_SECONDS"' in wait
    assert "--max-time 30" in wait

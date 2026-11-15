# Winlog

Winlog is a personal success diary for professionals. It makes it easy to record work
achievements, learnings and feedback as they happen, so they are not forgotten when review
time comes, and turns these records into editable, AI-generated summaries for performance
reviews and appraisal conversations. It is a responsive web app that works in desktop and
mobile browsers.

Winlog is the final project for the AI Dev Tools Zoomcamp 2026.

## Live demo

Winlog runs at **[https://winlog-app.onrender.com](https://winlog-app.onrender.com)**.

- **Try the demo:** on the login page, click **Try the demo**. You need no registration and no
  password. It opens a shared account with sample entries, which anyone can see and change. You
  can use every feature except deleting the account. The daily AI limits are shared by all
  visitors (see [AI](#ai)). Do not enter personal information.
- **Changes do not last:** the demo data is reset to the sample data whenever the backend
  starts: on every deploy, and whenever the sleeping server wakes up.
- **Cold start:** after a period of inactivity, the first request can take up to about a
  minute while the server wakes up (43.7 s was measured on 2026-11-14).

## Features

- **Accounts:** register with an email address and a password, log in and log out. A login
  lasts 7 days by default. Repeated failed logins are slowed down. Each user sees only their
  own entries, tags and summaries.
- **Capture entries:** write an entry as free text, with a date, one category (Achievement,
  Learning, Feedback or Side project), up to 10 tags and an optional Result/Impact. Edit and
  delete entries.
- **AI suggestions:** ask the AI for a category and tags. Suggestions fill only the fields you
  have not filled in, and nothing is saved until you confirm.
- **Review:** filter entries by period, categories and tags, shown grouped by category, newest
  first.
- **Summaries:** generate an AI summary of the filtered entries. It is saved with its filter,
  and you can list, edit and delete it, and copy its text to the clipboard.
- **Writing nudge:** a banner invites you to write an entry when you have none dated in the last
  7 days.
- **Data control:** export all your entries and summaries as JSON or Markdown, and delete your
  account after confirming your password.
- **Demo account:** a shared account with sample entries (see [Live demo](#live-demo)).

Everything except generating suggestions and summaries works without the AI. The full
requirements are in [`docs/product-spec.md`](docs/product-spec.md) (§7).

## Architecture

```
Browser (desktop / mobile)
        │
        ▼
React + TypeScript frontend ──── HTTPS / JSON ────► FastAPI backend
                                                     │         │
                                                     ▼         ▼
                                               PostgreSQL   LLM router
                                                            (OpenAI-compatible API)
```

| Part | Technology |
|---|---|
| Frontend | React and TypeScript, built with Vite; all backend calls go through one API client (`frontend/src/api/`) |
| Backend | Python and FastAPI: REST API, bearer-token authentication, the AI adapter, AI usage limits and login attempt limits |
| API contract | [`openapi.yaml`](openapi.yaml), written before the code |
| Database | PostgreSQL, used through SQLAlchemy, with schema changes through Alembic migrations |
| AI | OpenRouter (OpenAI-compatible API); a mock provider for tests and local use |
| Containers | Docker and Docker Compose for local development and integration tests |
| Observability | OpenTelemetry in the backend; locally Grafana's all-in-one `otel-lgtm` image (deployed environments send no telemetry yet) |
| CI/CD | GitHub Actions, with the backend image in GitHub Container Registry |
| Hosting | Render (frontend static sites, backend web services) and Neon (PostgreSQL) |

The full overview, the components and the environments are in §10 of
[`docs/product-spec.md`](docs/product-spec.md).

## Quick start

You need Docker with Docker Compose 2.23.1 or later; `docker compose version` shows yours.
`docker-compose.yml` writes the test database's set-up script inline, with the `content:` of a
`configs:` entry, which Docker Compose supports from version 2.23.1 on. In the root of a clone of
this repository:

```sh
cp .env.example .env
docker compose up --build
```

Then open:

- the app: http://localhost:8080
- the backend's health check: http://localhost:8000/health
- local Grafana, with the backend's traces, metrics and logs: http://localhost:3000 (no login;
  see [`docs/observability.md`](docs/observability.md))

`.env.example` sets `AI_PROVIDER=mock`, so suggestions and summaries come from the mock AI
provider, which needs no API key.

With `.env` from `.env.example` there is no demo account (`DEMO_EMAIL` is empty), so **Try the
demo** shows "The demo isn't available right now." Click **Create an account** on the login page
and register instead. To turn the demo on, set `DEMO_EMAIL` in `.env` (for example
`demo@example.com`) and run `docker compose up` again. The backend then resets the demo account
to the sample data at every start.

Ctrl+C stops the system. `docker compose down -v` removes the containers and deletes the local
data (the database and the telemetry).

## Development and tests

For work outside the containers you need uv (it installs the Python version in
`backend/.python-version`), Node.js (the version in `frontend/.nvmrc`) and Docker for
PostgreSQL. Copy `.env.example` to `.env` in the repository root first.

Backend, in `backend/`:

| Task | Command |
|---|---|
| Install dependencies | `uv sync` |
| Apply migrations (start PostgreSQL first with `docker compose up -d db` in the repository root) | `uv run alembic upgrade head` |
| Dev server | `uv run uvicorn app.main:app --reload` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Unit tests | `uv run pytest tests/unit` |
| Integration tests (real PostgreSQL: `docker compose up -d db` in the repository root, and `TEST_DATABASE_URL` in `.env`) | `uv run pytest tests/integration` |

Frontend, in `frontend/`:

| Task | Command |
|---|---|
| Install dependencies | `npm ci` |
| Dev server | `npm run dev` |
| Lint | `npm run lint` |
| Tests | `npm test` |
| Build | `npm run build` |
| Viewport tests at 360×640 and 1280×800, with every API call mocked (needs Chromium once: `npx playwright install chromium`) | `npm run test:viewport` |
| End-to-end test of the main user flow, against a running system with `AI_PROVIDER=mock` (for example after `docker compose up --build -d`) | `npm run test:e2e` |

The end-to-end test starts nothing itself. It runs against `E2E_BASE_URL` (default
http://localhost:8080), registers a test account and drafts one summary. Never point it at
production, where it would call the real AI.

All unit and integration tests, in the repository root:

```sh
./test-all.sh
```

It runs the backend unit tests, the backend integration tests and the frontend tests, starts
the test database if needed, and exits with 0 only when all pass. It needs `.env`, Docker, uv
and `npm ci` done in `frontend/` first.

[`AGENTS.md`](AGENTS.md) is the full command reference, including new migrations, the demo seed
script and both ways to start the system for the end-to-end test.

## Configuration

All configuration comes from environment variables. [`.env.example`](.env.example) is the full
list, with each variable's default and what it does. Copy it to `.env` (git-ignored) and never
commit real secrets.

A backend you run on your computer (`uv run uvicorn app.main:app --reload` in `backend/`) reads
its settings from `.env` itself. Under Docker Compose, the backend container gets every variable
in `.env` (see the `backend` service in [`docker-compose.yml`](docker-compose.yml)), so every
backend setting there applies in the same way. Compose sets only these itself:

- `DATABASE_URL`: the `db` service;
- `OTEL_EXPORTER_OTLP_ENDPOINT`: the `lgtm` service;
- `PORT`: 8000;
- `HSTS_MAX_AGE_SECONDS`: 0 when `.env` has no value.

Under Docker Compose:

- Change backend settings in `.env`, not in the shell: a shell variable does not replace a value
  the backend gets from `.env`. After a change, `docker compose up` again recreates the backend
  container with the new values.
- With `AI_PROVIDER=openai-compatible` and a real `AI_API_KEY`, every suggestion and summary is
  a real AI call that costs money. The end-to-end test needs the mock (`AI_PROVIDER=mock`).
- `docker compose config` prints the values from `.env`, including `AI_API_KEY`, so do not
  share its output.

## AI

- **Adapter:** every AI call goes through one adapter in `backend/app/ai/`, with two operations:
  suggest a category and tags for an entry text, and summarise a list of entries. `AI_PROVIDER`
  selects the provider, `mock` or `openai-compatible`. The adapter checks every provider's
  output by the same rules, and the daily limits are checked before every AI call.
- **Mock provider:** `AI_PROVIDER=mock` needs no API key and makes no network call. Its output
  is deterministic and obviously fake: summaries start with "Mock summary" and the suggested
  tag is "Mock tag". The automated tests, local development and the hosted dev environment use
  it. Tests never call a real AI.
- **Real provider:** `openai-compatible` calls a real model through OpenRouter. Every request
  is routed only to model endpoints with zero-data retention, which the provider account's
  settings enforce as well. Only the data a request needs is sent: the entry text for a
  suggestion, and each filtered entry's date, category, text, Result/Impact and tags for a
  summary. User ids and email addresses are never sent.
- **Daily limits:**

  | Limit | Default |
  |---|---|
  | Suggestions per user | 10 |
  | Summaries per user | 2 |
  | AI requests in total, across all users | 100 |

  All counts reset at 00:00 UTC. The limits are configurable (see `.env.example`). Every
  attempted AI call counts, including calls that fail or time out. The demo account is limited
  like any other user, so its limits are shared by everyone who uses the demo.
- **Default model:** `anthropic/claude-haiku-5.5`, with `deepseek/deepseek-v4.1-flash` as the
  backup. The comparison that chose them is in
  [`docs/decisions/default-model.md`](docs/decisions/default-model.md).
- **Production** uses that default model, and its OpenRouter key has a spending limit (see
  [`ops/deployment.md`](ops/deployment.md)).

## Deployment

After every CI job has passed for a commit on `main`, GitHub Actions deploys it automatically
to a hosted dev environment, and production gets the same backend image and commit only after
the product owner approves. [`ops/deployment.md`](ops/deployment.md) describes the pipeline,
promotion to production, rollback and the set-up from scratch.

## Project documents

| Document | What it holds |
|---|---|
| [`docs/product-spec.md`](docs/product-spec.md) | The product specification: scope, requirements, acceptance criteria and architecture |
| [`openapi.yaml`](openapi.yaml) | The API contract between frontend and backend |
| [`DESIGN.md`](DESIGN.md) | The design system: colours, type, layout, components, icons and illustrations |
| [`PRODUCT.md`](PRODUCT.md) | The product facts that design work relies on |
| [`AGENTS.md`](AGENTS.md) | Instructions for AI coding agents: working rules, repository layout, conventions and all commands |
| [`docs/process.md`](docs/process.md) | The development process: roles, the issue lifecycle and status labels |
| [`docs/tasks.md`](docs/tasks.md) | The backlog in build order, with links to the GitHub issues |
| [`docs/ai-workflow.md`](docs/ai-workflow.md) | The log of every task: what was done, how it was verified and what was left open |

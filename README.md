# Winlog

Winlog is a personal success diary for professionals. You record work achievements, learnings
and feedback as they happen. At review time, Winlog turns them into editable, AI-generated
summaries for performance reviews and appraisal conversations. It is a responsive web app that
works in desktop and mobile browsers.

**Live app: [https://winlog-app.onrender.com](https://winlog-app.onrender.com).** Click **Try
the demo** on the login page; no registration is needed.

Winlog is the final project for the AI Dev Tools Zoomcamp 2026. A team of AI agents built it
(a PM, a UX designer, a software engineer and QA, coordinated by an orchestrator) for a human
product owner, through a public GitHub issue tracker.

## Project criteria at a glance

| Criterion | Where to find it |
|---|---|
| Problem description | [The problem](#the-problem) and [What Winlog does](#what-winlog-does) |
| Product specification | [`docs/product-spec.md`](docs/product-spec.md) (requirements with IDs and acceptance criteria) and the public tracker, [GitHub Issues](https://github.com/KittyNiuNiu/winlog/issues?q=is%3Aissue): see [Specification and task tracker](#specification-and-task-tracker) |
| Agent team | [Agent team and process](#agent-team-and-process), [`docs/process.md`](docs/process.md) and [`.claude/agents/`](.claude/agents/) |
| Context management | [`AGENTS.md`](AGENTS.md), which points to the modular docs: see [Context for the agents](#context-for-the-agents) |
| Application | React frontend → FastAPI backend → PostgreSQL: see [Architecture](#architecture) and [Run it locally](#run-it-locally) |
| Testing | Unit and integration tests, all with one command, `./test-all.sh`: see [Tests](#tests) |
| Containerization | The full system, database included, starts with `docker compose up --build`: see [Run it locally](#run-it-locally) |
| Deployment | Production at [https://winlog-app.onrender.com](https://winlog-app.onrender.com), with a demo account: see [Deployment](#deployment) |
| CI/CD | CI checks every push; CD deploys to dev automatically and to production after a manual approval: see [CI/CD](#cicd) |
| Observability | OpenTelemetry traces, metrics and structured logs that share a trace ID, viewable in Grafana (local and Grafana Cloud): see [Observability](#observability) |
| Alerting on user impact | An alert on the share of server errors, locally and for dev and production in Grafana Cloud, with email notification: see [Alerting on user impact](#alerting-on-user-impact) |

## The problem

When review time comes, most people struggle to remember what they achieved over the past
months. Achievements go unrecorded because writing them down feels like extra work, and the
notes that do exist tend to be scattered and unstructured. As a result, people undersell their
work in reviews and interviews.

Winlog is for individual professionals who want a lightweight record of their work to prepare
for performance reviews, appraisal talks and job interviews. Its goals
([`docs/product-spec.md`](docs/product-spec.md), §2 to §5):

- Capturing an entry takes less than a minute.
- Entries can be filtered and grouped by period, category and tags.
- A selection of entries can be turned into a review-ready summary that the user can edit and
  keep.
- The app stays fully usable when the AI is unavailable.
- Users stay in control of their data: they can edit, export and delete it.

## What Winlog does

A typical session: log in (or try the demo), write a few entries, ask the AI for a category and
tags, filter the entries for the review period on the Review page, generate a summary, edit it
and copy it into the review form.

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
  and you can list, edit and delete it, and copy its text to the clipboard. Editing or deleting
  an entry never changes a saved summary.
- **Writing nudge:** a banner invites you to write an entry when you have none dated in the last
  7 days.
- **Data control:** export all your entries and summaries as JSON or Markdown, and delete your
  account after confirming your password.
- **Demo account:** a shared account with sample entries (see [Deployment](#deployment)).

Expected behaviour:

- Everything except generating suggestions and summaries works without the AI.
- AI use has daily limits per user and in total, checked before every AI call (see [AI](#ai)).
- Not in v1: native mobile apps, sharing entries or summaries, single sign-on, and long-term
  pattern analysis (§4 of the spec).

The full requirements and their acceptance criteria are in
[`docs/product-spec.md`](docs/product-spec.md), §7 to §9.

## Deployment

Winlog runs in two hosted environments. Both are defined in one Render Blueprint,
[`render.yaml`](render.yaml), and are deployed by the [CI/CD](#cicd) pipeline.

| | Production | Dev |
|---|---|---|
| App (static site) | [https://winlog-app.onrender.com](https://winlog-app.onrender.com) | [https://winlog-app-dev.onrender.com](https://winlog-app-dev.onrender.com) |
| Backend | `https://winlog-api.onrender.com` | `https://winlog-api-dev.onrender.com` |
| Deployed | by CD, after the product owner approves | by CD, automatically after CI passes on `main` |
| AI | a real model through OpenRouter, with zero data retention | the mock provider: no API key, no cost |
| Database | Neon PostgreSQL, production project | Neon PostgreSQL, its own project, test data only |
| Telemetry and alerts | Grafana Cloud, environment `production` | the same Grafana Cloud stack, environment `dev` |

Both backends are Render web services that run the backend image from GitHub Container
Registry; both frontends are Render static sites. Render and Neon run on their free plans.

To try Winlog, use production. Dev is where each change is checked before it goes to
production.

- **Try the demo:** on the login page, click **Try the demo**. It opens a shared account with
  sample entries, which anyone can see and change. You need no registration and no password.
  You can use every feature except deleting the account. All visitors share the demo account's
  daily AI limits (see [AI](#ai)). Do not enter personal information.
- **Changes do not last:** the backend resets the demo data to the sample data whenever it
  starts: on every deploy, and whenever the sleeping server wakes up.
- **Cold start:** the free backends sleep after 15 minutes without requests. The first request
  after that wakes them, which takes up to about a minute (49 s measured on both backends on
  21 November 2026).
- **Which commit is live:** `GET /health` on a backend and `/version.json` on an app name the
  commit they were built from:

  ```sh
  curl https://winlog-api.onrender.com/health
  # {"status":"ok","database":"ok","commit":"<commit SHA>"}
  ```

[`ops/deployment.md`](ops/deployment.md) describes the pipeline, the promotion to production,
rollback, the secrets, the free-plan limits and the set-up from scratch.

## CI/CD

```
push to any branch ──► CI (6 jobs) ──► branch other than main: stop, nothing is deployed
                                   └─► main, every job passed: Deploy workflow
                                        1. Publish image ──► ghcr.io/kittyniuniu/winlog-backend:sha-<commit>
                                        2. Deploy to dev (automatic) ──► winlog-api-dev, winlog-app-dev
                                        3. Deploy to production (waits for the product owner's approval)
                                                                     ──► winlog-api, winlog-app
```

**CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push to every
branch, so the commits of every pull request are checked before it is merged. It needs no
secrets, and no job calls a real AI.

| Job | What it checks |
|---|---|
| Contract | Lints [`openapi.yaml`](openapi.yaml) with Redocly CLI |
| Backend | Ruff lint and format check; the backend starts with only the settings from `.env.example` |
| Frontend | The generated API types match `openapi.yaml`; lint; build; viewport tests at 360×640 and 1280×800 |
| Tests | `./test-all.sh`: backend unit tests, backend integration tests on real PostgreSQL, frontend tests |
| Backend image | Builds the image; checks that it records its commit, holds no `.env` file and is linked to the repository |
| Full system | `docker compose up --build`; health, migrations and frontend checks; the Playwright end-to-end test of the main user flow; the alert rule is loaded; telemetry reaches the local Grafana stack |

**CD** ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)) starts only after a CI
run for a push to `main` has passed:

1. **Publish image** pushes the exact image CI built and checked to GitHub Container Registry.
2. **Deploy to dev** (automatic) deploys that image, by digest, to the dev backend and builds the
   dev frontend from the same commit. It waits until both answer with that commit.
3. **Deploy to production** (manual) waits for the product owner's approval: the GitHub
   environment `production` has the product owner as required reviewer. It then deploys the
   same image digest and commit to production and waits the same way. Nothing is rebuilt.

Rollback: re-run the production job of an earlier Deploy run and approve it, which deploys
that run's image again, or use Render's own rollback
([`ops/deployment.md`](ops/deployment.md), "Rollback and emergencies").

The runs: [CI](https://github.com/KittyNiuNiu/winlog/actions/workflows/ci.yml) and
[Deploy](https://github.com/KittyNiuNiu/winlog/actions/workflows/deploy.yml).

## Architecture

```
Browser (desktop / mobile)
        │
        ▼
React + TypeScript frontend ── HTTPS / JSON ──► FastAPI backend ──► PostgreSQL
                                                  │       │
                                                  │       └──► LLM through OpenRouter (OpenAI-compatible API);
                                                  │            the mock provider in tests, locally and in dev
                                                  └──► OpenTelemetry (OTLP) ──► Grafana: local otel-lgtm or Grafana Cloud
```

| Part | Technology |
|---|---|
| Frontend | React and TypeScript, built with Vite; all backend calls go through one API client (`frontend/src/api/`), with types generated from `openapi.yaml` |
| Backend | Python and FastAPI: REST API, bearer-token authentication, the AI adapter, AI usage limits and login attempt limits |
| API contract | [`openapi.yaml`](openapi.yaml), written before the code |
| Database | PostgreSQL, used through SQLAlchemy, with schema changes through Alembic migrations |
| AI | OpenRouter (OpenAI-compatible API); a mock provider for tests, local use and dev |
| Containers | Docker and Docker Compose for local development, integration tests and CI |
| Observability | OpenTelemetry in the backend; locally Grafana's all-in-one `otel-lgtm` image, and Grafana Cloud for dev and production |
| CI/CD | GitHub Actions, with the backend image in GitHub Container Registry |
| Hosting | Render (static sites for the frontends, web services for the backends) and Neon (PostgreSQL) |

The full overview, the components and the environments are in §10 of
[`docs/product-spec.md`](docs/product-spec.md).

## Run it locally

You need Docker with Docker Compose 2.23.1 or later (`docker compose version` shows yours):
`docker-compose.yml` writes the test database's set-up script inline, which needs that version.
In the root of a clone of this repository:

```sh
cp .env.example .env
docker compose up --build
```

That one command starts the whole system:

| Service | What it is | Open |
|---|---|---|
| `frontend` | The React build, served by nginx | http://localhost:8080 |
| `backend` | FastAPI; applies the database migrations on every start | http://localhost:8000/health |
| `db` | PostgreSQL 18, with the app's database and a separate test database; data kept in the `db-data` volume | port 5432 |
| `lgtm` | Grafana's `otel-lgtm`: OpenTelemetry Collector, Prometheus, Tempo, Loki and Grafana, with the alert rule | http://localhost:3000 (no login) |

`.env.example` sets `AI_PROVIDER=mock`, so suggestions and summaries come from the mock AI
provider, which needs no API key.

With `.env` from `.env.example` there is no demo account (`DEMO_EMAIL` is empty), so **Try the
demo** shows "The demo isn't available right now." Click **Create an account** on the login page
and register instead. To turn the demo on, set `DEMO_EMAIL` in `.env` (for example
`demo@example.com`) and run `docker compose up` again. The backend then resets the demo account
to the sample data at every start.

Ctrl+C stops the system. `docker compose down -v` removes the containers and deletes the local
data (the database and the telemetry).

## Tests

All unit and integration tests run with one command in the repository root:

```sh
./test-all.sh
```

| Suite | Where | Runs against | Tests (21 November 2026) |
|---|---|---|---|
| Backend unit tests | `backend/tests/unit/` | no database, the mock AI | 1877 passed |
| Backend integration tests | `backend/tests/integration/` | real PostgreSQL in Docker Compose, never SQLite | 1202 passed |
| Frontend tests | `frontend/src/` (Vitest and React Testing Library) | every backend request mocked | 1421 passed |

`./test-all.sh` runs the three suites in order, runs every suite even after one fails, prints a
summary and exits with 0 only when all pass. It starts the test database if needed and stops it
again if it started it. It needs `.env` (copied from `.env.example`), Docker, uv and `npm ci`
done in `frontend/` first.

- Tests are named after the requirement they cover, for example
  `test_fr_e1_one_text_creates_one_entry` for FR-E1.
- Tests never call a real AI (they use the mock provider) and never need a running telemetry
  collector.
- Two more suites run in CI: the viewport tests (`npm run test:viewport`) and the end-to-end
  test of the main user flow against the running system (`npm run test:e2e`). See
  [Development commands](#development-commands).

## Specification and task tracker

- **Specification:** [`docs/product-spec.md`](docs/product-spec.md) holds the problem, goals,
  non-goals, target users, the functional requirements with IDs (for example FR-E1) and their
  acceptance criteria, the AI guardrails, the non-functional requirements, the
  architecture and environments, known limitations and a change log.
- **API contract:** [`openapi.yaml`](openapi.yaml), written before the code. CI lints it and
  checks that the frontend's generated types match it.
- **Public task tracker:** [GitHub Issues](https://github.com/KittyNiuNiu/winlog/issues?q=is%3Aissue).
  Every task is one issue. Before anyone builds it, the PM agent grooms it with
  [`docs/task-template.md`](docs/task-template.md): Goal, Acceptance criteria (checkboxes), Out
  of scope and Constraints. A status label shows where each issue is in the lifecycle (see
  [Agent team and process](#agent-team-and-process)).
- **Evidence that the agents used it:** each role posts its work on the issue: the PM's
  grooming and questions, the product owner's answers, the engineer's hand-over with the test
  results, and QA's PASS or FAIL against every acceptance criterion. For example,
  [#117](https://github.com/KittyNiuNiu/winlog/issues/117) (alert on server errors in Grafana
  Cloud).
- **Build order:** [`docs/tasks.md`](docs/tasks.md) lists the tasks in build order, each with a
  link to its issue.
- **Work log:** [`docs/ai-workflow.md`](docs/ai-workflow.md) has one entry per task: what was
  done, how it was verified and what was left open.

## Agent team and process

The team works in Claude Code. The main session is the orchestrator; the other roles are
subagents that only the orchestrator launches. The process is in
[`docs/process.md`](docs/process.md).

| Role | Responsibility | Defined in | Never does |
|---|---|---|---|
| Product owner (human) | Answers product questions, merges pull requests, approves production deploys, does the steps in the accounts (Render, Neon, OpenRouter, Grafana Cloud, GitHub) | [`docs/process.md`](docs/process.md) | |
| Orchestrator (main session, `/orchestrate`) | Picks the next issue, launches the roles, sets the status labels, relays questions to the product owner one at a time, closes issues | [`docs/process.md`](docs/process.md), [`.claude/skills/orchestrate/SKILL.md`](.claude/skills/orchestrate/SKILL.md) | Groom, design, implement or test itself |
| PM (`pm`) | Grooms one issue with the task template: goal, checkable acceptance criteria with the edge cases, out of scope (each item linked to a follow-up issue) and constraints | [`docs/pm.md`](docs/pm.md), [`.claude/agents/pm.md`](.claude/agents/pm.md) | Write code or launch agents |
| UX designer (`ux-designer`) | For a task that changes screens: a design note before the build, and a review of the built screens after QA | [`docs/ux-designer.md`](docs/ux-designer.md), [`DESIGN.md`](DESIGN.md), [`.claude/agents/ux-designer.md`](.claude/agents/ux-designer.md) | Change code |
| Software engineer (`software-engineer`) | Implements one groomed issue against its acceptance criteria, writes tests, makes lint and the whole test suite pass, commits and pushes, and comments on the issue what it did | [`docs/software-engineer.md`](docs/software-engineer.md), [`.claude/agents/software-engineer.md`](.claude/agents/software-engineer.md) | Close issues or merge |
| QA engineer (`qa-engineer`) | Checks the result against every acceptance criterion and posts PASS or FAIL | [`docs/qa-engineer.md`](docs/qa-engineer.md), [`.claude/agents/qa-engineer.md`](.claude/agents/qa-engineer.md) | Change code |

How an issue moves through the team:

```
open issue ──► PM grooms ──► designer's note (if screens change) ──► engineer implements ──► QA
                                                                          ▲                 │
                                                                          └──── FAIL ───────┤
                                                                          ▲                 │ PASS
                                                                          │                 ▼
                                                                          └── FAIL ── design review (if screens change)
                                                                                            │ PASS
                                                                                            ▼
                                                                         orchestrator closes the issue
```

- **Status labels:** `groomed`, `designed`, `implemented`, `qa-failed`, `qa-passed` and
  `design-failed`. The orchestrator sets one after each step; a new issue has none until it is
  groomed.
- **Stop points:** the orchestrator stops and asks the product owner when a role needs a
  product decision, an acceptance criterion is wrong or contradicts another, QA or the design
  review fails twice for the same issue, or the tests cannot run.
- **Open points:** when it closes an issue, the orchestrator posts each open point from the
  engineer, QA and the designer on the open issue it belongs to. If no issue fits, it asks the
  product owner.
- **Logging:** the PM, the engineer and the orchestrator each add an entry to
  [`docs/ai-workflow.md`](docs/ai-workflow.md). QA and the designer post their verdicts as issue
  comments.

The four `.claude/agents/impeccable-*.md` agents came with the Impeccable design skill. They
are design tools, not roles in the team.

## Context for the agents

[`AGENTS.md`](AGENTS.md) is the agents' entry point; [`CLAUDE.md`](CLAUDE.md) imports it
(`@AGENTS.md`) so Claude Code reads it as the project instructions, and each role's agent file
in `.claude/agents/` names the docs that role reads first. `AGENTS.md` describes the project and holds the working rules (spec first, contract first,
no real AI calls without the product owner's approval, a log entry after every task), the
repository layout, every command (the same as CI's), and the backend, frontend, testing,
security and git conventions. For everything else it points to modular docs:

| Document | What it holds |
|---|---|
| [`docs/product-spec.md`](docs/product-spec.md) | The product specification: scope, requirements, acceptance criteria and architecture |
| [`openapi.yaml`](openapi.yaml) | The API contract between frontend and backend |
| [`docs/process.md`](docs/process.md) | The team, the roles, the issue lifecycle, the status labels and the stop points |
| [`docs/pm.md`](docs/pm.md), [`docs/ux-designer.md`](docs/ux-designer.md), [`docs/software-engineer.md`](docs/software-engineer.md), [`docs/qa-engineer.md`](docs/qa-engineer.md) | Each role's instructions and definition of done |
| [`docs/task-template.md`](docs/task-template.md) | The template every groomed issue follows |
| [`docs/tasks.md`](docs/tasks.md) | The backlog in build order, with links to the GitHub issues |
| [`docs/ai-workflow.md`](docs/ai-workflow.md) | The log of every task: what was done, how it was verified and what was left open |
| [`DESIGN.md`](DESIGN.md), [`PRODUCT.md`](PRODUCT.md) | The design system, and the product facts that design work relies on |
| [`docs/observability.md`](docs/observability.md) | The telemetry, the privacy allowlist and the alerts |
| [`ops/deployment.md`](ops/deployment.md) | The pipeline, the hosted environments, rollback and set-up |
| [`docs/decisions/`](docs/decisions/) | Decision records, such as the choice of the default AI model |

## Observability

The backend sends traces, metrics and structured JSON logs with OpenTelemetry
(`backend/app/telemetry.py`). The full description is in
[`docs/observability.md`](docs/observability.md).

- **Key user journey:** generating a summary (`POST /summaries`) is instrumented in detail. Its
  trace has the request's SERVER span and four child spans: `summary.select_entries`,
  `ai.limits.reserve`, `ai.summarise` and `summary.save`. A counter records each generation's
  outcome (`created`, `limit_reached`, `ai_unavailable` and others), and a histogram records the
  AI call durations.
- **Every request** gets a SERVER span, an HTTP duration measurement and a `request finished`
  log line.
- **One trace ID:** each log line carries the `trace_id` and `span_id` of its request, so a
  trace's logs can be found in Loki with `| trace_id="<trace ID>"`.
- **Where to see it:** locally in Grafana at http://localhost:3000 (Tempo for traces, Loki for
  logs, Prometheus for metrics). The hosted dev and production backends send theirs to one
  Grafana Cloud stack, the product owner's, where every signal is marked with its environment.
- **No customer data:** telemetry holds only the fields in the allowlist in
  [`docs/observability.md`](docs/observability.md). Never entry text, Result/Impact, summary
  text, tag names, AI request or response content, email addresses, user ids, passwords,
  tokens, IP addresses or query strings.

See it locally:

1. `docker compose up --build`, then generate a summary in the app (http://localhost:8080 →
   Review).
2. Open http://localhost:3000 → **Explore** → **Tempo**, and search with TraceQL:
   `{resource.service.name="winlog-backend" && name="POST /summaries"}`.
3. Copy the trace ID, then switch to **Loki**:
   `{service_name="winlog-backend"} | trace_id="<trace ID>"`.

## Alerting on user impact

| Rule | Where | Notifies |
|---|---|---|
| `Server errors above 5%` | Local Grafana; provisioned from [`ops/grafana/alerting/user-impact.yaml`](ops/grafana/alerting/user-impact.yaml) on every start | Shown in Grafana (**Alerting → Alert rules**, folder `Winlog`) |
| `Server errors above 5% in production` and `… in dev` | Grafana Cloud; imported from [`ops/grafana-cloud/alert-rules.yaml`](ops/grafana-cloud/alert-rules.yaml) | Email to the product owner |

Each rule fires when more than 5% of the backend's requests over the last 5 minutes were
answered with a server error (5xx) for at least 1 minute. A 5xx is what a user feels as "it is
broken": the database is unreachable, the AI is unavailable, or an unexpected error. 4xx
answers, including the 429 of a reached AI limit, are expected answers and do not count.

CI checks that the local rule is loaded, and a unit test keeps the hosted rules' query the same
as the local one. How to make the local rule fire on purpose, and what the rules cannot see (a
sleeping backend sends no telemetry): [`docs/observability.md`](docs/observability.md),
"Alerts".

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
  is routed only to model endpoints with zero data retention, which the provider account's
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
  [`docs/decisions/default-model.md`](docs/decisions/default-model.md). Production uses that
  default model, and its OpenRouter key has a spending limit (see
  [`ops/deployment.md`](ops/deployment.md)).

## Configuration

All configuration comes from environment variables. [`.env.example`](.env.example) is the full
list, with each variable's default and what it does. Copy it to `.env` (git-ignored) and never
commit real secrets.

- A backend you run on your computer (`uv run uvicorn app.main:app --reload` in `backend/`)
  reads its settings from `.env` itself.
- Under Docker Compose, the backend container gets every variable in `.env`, except a few that
  Compose sets itself: `DATABASE_URL` (the `db` service), `OTEL_EXPORTER_OTLP_ENDPOINT` (the
  `lgtm` service), `OTEL_EXPORTER_OTLP_HEADERS` (empty, so a hosted telemetry token never goes
  to `lgtm`), `TELEMETRY_ENVIRONMENT` (`local`), `PORT` (8000) and `HSTS_MAX_AGE_SECONDS` (0
  when `.env` has no value). See the `backend` service in
  [`docker-compose.yml`](docker-compose.yml).
- Change backend settings in `.env`, not in the shell, then run `docker compose up` again. A
  shell variable wins over `.env` only for the values `docker-compose.yml` fills in with
  `${...}`: `AI_PROVIDER`, `CORS_ALLOWED_ORIGINS`, `HSTS_MAX_AGE_SECONDS` and the `POSTGRES_*`
  values.
- With `AI_PROVIDER=openai-compatible` and a real `AI_API_KEY`, every suggestion and summary is
  a real AI call that costs money. The end-to-end test needs the mock (`AI_PROVIDER=mock`).
- `docker compose config` prints the values from `.env`, including `AI_API_KEY`, so do not
  share its output.

## Development commands

For work outside the containers you need uv (it installs the Python version in
`backend/.python-version`), Node.js (the version in `frontend/.nvmrc`) and Docker for
PostgreSQL. Copy `.env.example` to `.env` in the repository root first.

Backend, in `backend/`:

| Task | Command |
|---|---|
| Install dependencies | `uv sync` |
| Apply migrations (start PostgreSQL first with `docker compose up -d --wait db` in the repository root) | `uv run alembic upgrade head` |
| Dev server | `uv run uvicorn app.main:app --reload` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Unit tests | `uv run pytest tests/unit` |
| Integration tests (real PostgreSQL: `docker compose up -d --wait db` in the repository root, and `TEST_DATABASE_URL` in `.env`) | `uv run pytest tests/integration` |

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

[`AGENTS.md`](AGENTS.md) is the full command reference, including new migrations, the demo seed
script and both ways to start the system for the end-to-end test. It also lists every check CI
runs, with CI's own command, among them the contract lint of `openapi.yaml` and the generation
of the frontend's API types from it.

# AGENTS.md

Instructions for AI coding agents working on Winlog.

## Project

Winlog is a personal success diary web app. Users capture work achievements, learnings and feedback, and turn them into AI-generated, editable summaries for performance reviews.

Sources of truth (read them before starting any task):

- `product-spec.md`: scope, requirements, acceptance criteria
- `openapi.yaml`: the API contract between frontend and backend

## Working rules

- Implement only what `product-spec.md` describes. If a task needs behaviour the spec does not cover, stop and ask. Do not invent requirements.
- Contract first: every API change starts in `openapi.yaml`, then the backend, then the frontend.
- Do not edit `product-spec.md` or `openapi.yaml` unless the task explicitly says so.
- For a task that touches more than one module, propose a plan before editing.
- Keep changes small and focused on the task. Do not refactor unrelated code.
- A task is done only when lint and all tests pass.
- If you are unsure how a library works, check its documentation instead of guessing.
- No real AI calls without the product owner's explicit approval in that session. Real AI calls cost money. This covers tests, scripts, live checks and running the app with a real provider (anything other than `AI_PROVIDER=mock`). If a task needs one, stop and ask first, with the reason and an estimated cost.
- After each task, add an entry to `docs/ai-workflow.md` with the date, the task, what you did, how you verified it, and anything left open.
- Follow the process in docs/process.md

## Repository layout

```
backend/              FastAPI app (Python)
  app/                application code
  app/ai/             AI adapter (real provider + mock provider)
  migrations/         Alembic migrations
  tests/unit/         unit tests
  tests/integration/  integration tests (real PostgreSQL)
frontend/             React + TypeScript app (Vite)
  src/api/            the only place that calls the backend
mcp-server/           developer MCP server for coding agents
docs/                 architecture and process docs
security/             scan reports and security notes
ops/                  operational notes
.github/workflows/    CI/CD pipelines
openapi.yaml          API contract
docker-compose.yml    full system for local dev and integration tests
test-all.sh           runs all unit and integration tests with one command
```

## Commands

Keep these commands working. If you change one, update this file.

Backend (run in `backend/`):

- Install dependencies: `uv sync`
- Dev server: `uv run uvicorn app.main:app --reload`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Unit tests: `uv run pytest tests/unit`
- Integration tests (needs PostgreSQL and `TEST_DATABASE_URL` in `.env`; start it first with `docker compose up -d db` in the repo root): `uv run pytest tests/integration`
- Apply migrations: `uv run alembic upgrade head`
- New migration: `uv run alembic revision --autogenerate -m "<message>"`
- Seed or reset the demo account (needs `DEMO_EMAIL` and a migrated database; changes nothing when `DEMO_EMAIL` is empty): `uv run python -m scripts.seed_demo`

Frontend (run in `frontend/`):

- Install dependencies: `npm ci`
- Dev server: `npm run dev`
- Lint: `npm run lint`
- Tests: `npm test`
- Build: `npm run build`
- End-to-end smoke test (one Playwright test of the main user flow at 1280×800, `e2e/`, config `playwright.e2e.config.ts`): `npm run test:e2e`. It starts nothing itself: it runs against a running system at `E2E_BASE_URL` (default `http://localhost:8080`) with `AI_PROVIDER=mock`. First copy `.env.example` to `.env` in the repo root, then start the system in one of two ways:
  - Full system: `docker compose up --build -d` in the repo root.
  - Without the app containers (for example in a cloud session): `docker compose up -d db` in the repo root; `uv run alembic upgrade head` and `uv run uvicorn app.main:app --port 8000` in `backend/`; `npm run build` and then `npx vite preview --port 8080 --strictPort` in `frontend/`.

  Each run drafts one summary, which counts against the global daily AI limit (`AI_DAILY_REQUESTS_GLOBAL`); `docker compose down -v` resets a local database. Traces and screenshots of a failed run go to `frontend/e2e-results/`.
- Viewport tests (Playwright, 360×640 and 1280×800, every API call mocked; builds the app and serves it with `vite preview`; screenshots go to `viewport-screenshots/`; needs Chromium once: `npx playwright install chromium`): `npm run test:viewport`

Full system (repo root): `docker compose up --build`

All unit and integration tests (repo root): `./test-all.sh`. It runs the three suites in order: backend unit tests, backend integration tests and frontend tests (`npm test`), runs every suite even after one fails, prints a summary and exits with 0 only when all pass. It starts the test database with `docker compose up -d --wait db` if needed and stops it again with `docker compose stop db` only if it started it. It needs `.env` in the repo root, Docker, uv and `npm ci` done in `frontend/` first. The separate commands above stay.

## Backend conventions

- FastAPI with Pydantic models that match the schemas in `openapi.yaml`.
- PostgreSQL via SQLAlchemy 2.x. Change the schema only through new Alembic migrations, and never edit a migration that is already merged.
- All configuration comes from environment variables (documented in `.env.example`). No hard-coded URLs, keys or limits.
- Scope every query on user data to the authenticated user, and add a test that another user cannot access it.
- Hash passwords with an established library (argon2 or bcrypt). Never store or log them in plain text.
- All AI calls go through the adapter in `app/ai/`. Provider and model come from environment variables.
- Check the AI usage limits (per user and global, per day) before every AI call.
- Send only the data a request needs to the AI provider.
- Never log entry text, summaries or passwords.

## Frontend conventions

- React + TypeScript, built with Vite.
- All backend calls go through `src/api/`. Components never call `fetch` directly.
- API data types are derived from `openapi.yaml`.
- Mobile-first responsive layout: every screen must work at a 360px viewport width.
- Visual design follows `DESIGN.md` (colours, type, layout, components, icons, illustrations). Read it before building or changing any screen. `PRODUCT.md` holds the product facts it relies on.
- All UI text is in English.
- Tests use Vitest and React Testing Library.

## Testing

- Unit tests and integration tests live in separate folders and run separately. `./test-all.sh` runs them all in one go.
- Integration tests run against real PostgreSQL (via Docker Compose), never SQLite.
- Tests never call a real AI API. They use the mock provider.
- Frontend tests never reach a real backend: unmocked requests fail in the shared test set-up.
- Every new endpoint gets tests for the success case, validation errors, and access by another user.
- Cover each acceptance criterion in `product-spec.md` with at least one test, and name the test after its requirement ID (for example `test_fr_e1_one_text_creates_one_entry`).
- Never weaken or delete a failing test to make it pass. Fix the code or ask.

## Security

- Never commit secrets. Real values go in `.env` (git-ignored). Keep `.env.example` up to date with placeholder values.
- Validate all input at the API boundary.
- Do not add a new dependency without saying why in your task summary.

## Git

- Work on a branch per task. Never push to `main` directly.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- Keep commits small and focused.

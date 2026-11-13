# Deployment: Render and Neon

How Winlog runs in production, how to set it up from scratch, and how to redeploy (issue #38,
`docs/product-spec.md` §10.2 and §10.4).

| Part | Where | Defined in |
|---|---|---|
| Backend (FastAPI) | Render web service `winlog-api`, Docker, free instance, region Frankfurt | `render.yaml`, `backend/Dockerfile`, `backend/start.sh` |
| Frontend (React build) | Render static site `winlog-app`, Render's global CDN | `render.yaml` |
| Database | Neon, PostgreSQL 18, region Frankfurt (AWS eu-central-1) | Neon console |
| AI | OpenRouter, zero data retention, model `anthropic/claude-haiku-5.5` | `render.yaml`, OpenRouter account |

Both Render services are defined in one Render Blueprint, `render.yaml` in the repository
root. Every setting is an environment variable. Only two of them are secrets.

**Secrets never go into git, an issue, a comment, a chat or a task summary.** They are typed
only into the Neon, OpenRouter and Render web pages named below.

> Render, Neon and OpenRouter pages could not be opened from the session that wrote this file.
> Field names in `render.yaml` were checked against Render's published Blueprint JSON schema;
> the names of buttons and settings in the three web consoles below are from memory. If a
> console looks different, follow its current wording; what each step must achieve stays the
> same.

## What the backend does on every start

`backend/start.sh` is the image's start command. It runs on every container start: every
deploy, every manual restart, and every wake of the sleeping free instance.

1. `start: applying database migrations` – `alembic upgrade head`.
2. `start: resetting the demo account` – the demo reset (`python -m scripts.seed_demo`), only
   when `DEMO_EMAIL` is set. It replaces the demo account's entries, tags and summaries with
   the sample data and keeps its login tokens and AI usage (#21): visitors stay logged in, and
   a reset does not give the shared demo more AI requests. Without `DEMO_EMAIL` it prints
   `start: DEMO_EMAIL is not set, skipping the demo reset`.
3. `start: starting the server on port <PORT>` – uvicorn on `0.0.0.0`, on the port Render sets
   in `PORT` (8000 when `PORT` is not set, as in Docker Compose).

If step 1 or 2 fails, the script exits with a non-zero code and the server never starts.

**What a failed start looks like in Render:**

- On a deploy: the deploy shows as **Failed** in the service's **Events**, and the **Logs**
  show the last `start:` line followed by the error (for example a database connection error)
  and an exit with status 1. Render keeps serving the previous successful deploy.
- On a wake or restart: there is no older instance to fall back to, so the backend does not
  answer until a start succeeds. Look at the service's **Logs** for the failing step.

The access log stays off (`backend/app/telemetry.py`, #74), and the start command does not turn
it back on, so request lines with query strings (such as `?tag=<name>`) never reach Render's
logs. The backend prints only its JSON log lines and sends no telemetry in production
(`OTEL_EXPORTER_OTLP_ENDPOINT` is not set, `docs/observability.md`; hosted telemetry is #92).

## Set up production from scratch

Do the steps in this order. You need the Render, Neon and OpenRouter accounts.

### 1. Neon: the database connection string

1. Open the Neon project (PostgreSQL 18, region AWS eu-central-1, Frankfurt).
2. Open **Connect** (connection details) for the project's database.
3. Choose the **direct** connection, not the pooled one: turn **Connection pooling** off. The
   direct host name has no `-pooler` in it. Alembic and SQLAlchemy keep their own normal
   session connections, which the pooled endpoint is not meant for.
4. Copy the connection string. It looks like
   `postgresql://<user>:<password>@<endpoint>.eu-central-1.aws.neon.tech/<database>?sslmode=require`
   (Neon may add `&channel_binding=require`). Keep the whole query part, especially
   `sslmode=require`: the connection must use TLS. The backend accepts `postgresql://` URLs
   as they are.
5. This string is a secret (it contains the password). It goes only into Render's
   `DATABASE_URL` in step 3. Do not save it anywhere else.

### 2. OpenRouter: account settings and the production key

1. In the account's **Settings → Privacy** (data policy):
   - turn on the setting that routes requests **only to zero-data-retention (ZDR) endpoints**.
     The backend also asks for ZDR on every request (`provider: {"zdr": true}`, #13); the
     account setting enforces it a second time (§8);
   - leave OpenRouter's own **logging of prompts and answers** (input/output logging) **off**.
2. In **Keys**, create a new key **for production only**, separate from the development key
   used for the model comparison (#14). Give it a **credit (spending) limit of $5**. That is
   the real cap on AI cost: the daily limits in `render.yaml` bound the number of requests,
   and the key's limit bounds the money.
3. Make sure the account has credit.
4. The key is a secret. It goes only into Render's `AI_API_KEY` in step 3.

### 3. Render: create the Blueprint

1. Make sure the branch with `render.yaml` is merged into `main`.
2. In the Render Dashboard: **New → Blueprint**, connect the GitHub repository, and choose
   the branch `main`. Render reads `render.yaml` and lists two services: `winlog-api` (web
   service, Docker) and `winlog-app` (static site).
3. Render asks for the two `sync: false` values. Paste:
   - `DATABASE_URL`: the Neon direct connection string from step 1;
   - `AI_API_KEY`: the production OpenRouter key from step 2.
4. Apply the Blueprint. Render builds the backend image from `backend/Dockerfile` and the
   static site with `npm ci && npm run build` in `frontend/`.
5. Check the two public URLs (next section), then wait until both first deploys show
   **Live**. The backend's first start runs all migrations and creates the demo account.
6. Open `https://<backend host>/health`. It must answer `{"status": "ok", "database": "ok"}`.

The two `sync: false` values are entered only once. Later Blueprint syncs do not ask again and
keep them. To change one (a new key, a new database password), edit it in the service's
**Environment** page in the Render Dashboard and save; the backend then restarts with it.

### 4. The public URLs

Two values are the services' public URLs, written as `https://<host>` without a trailing slash.
They are written in `render.yaml`, so they are reviewed in git:

| Variable | Service | Value in `render.yaml` |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | backend | `https://winlog-app.onrender.com` (the static site's URL) |
| `VITE_API_BASE_URL` | static site, at build time | `https://winlog-api.onrender.com` (the backend's URL) |

Render gives each service the host `<service name>.onrender.com`. If a name is already taken
by someone else, Render adds a suffix (for example `winlog-api-abcd.onrender.com`). Each
service shows its real URL at the top of its page in the Render Dashboard. **On the first
deploy, compare both URLs with the table.** If one differs:

1. To get running at once, set the real value on the other service's **Environment** page in
   the Dashboard: the static site's URL in the backend's `CORS_ALLOWED_ORIGINS`, or the
   backend's URL in the static site's `VITE_API_BASE_URL`.
2. Then trigger a new deploy of the service you changed. `VITE_API_BASE_URL` is built into
   the JavaScript files, so it takes effect only with a new static-site build (**Manual
   Deploy → Deploy latest commit**, or clear the build cache first if the old value persists).
3. Put the same value into `render.yaml` with a normal task and merge it into `main`, so the
   next Blueprint sync keeps it instead of overwriting the dashboard value.

The static-site build refuses to run with an empty `VITE_API_BASE_URL` and prints
`VITE_API_BASE_URL is required`, as `frontend/Dockerfile` does, so a forgotten value cannot
produce a site that calls no backend. A change to `VITE_API_BASE_URL` always needs a new
static-site build. A change to `CORS_ALLOWED_ORIGINS` needs only a backend restart, which Render
does when the value changes.

## Redeploy

- **Normal changes:** merge into `main`. Each service deploys the new commit automatically, but
  only after all of that commit's GitHub checks have passed (`autoDeployTrigger: checksPass`,
  §10.2). A commit with a failing check is not deployed. (#39 later replaces this with its own
  pipeline.)
- **By hand:** a service's **Manual Deploy → Deploy latest commit** in the Render Dashboard.
- **A changed `render.yaml`:** after the merge, Render syncs the Blueprint and applies the
  changed settings (see the Blueprint's page in the Dashboard; a sync can also be started there).

## Run the demo reset by hand

Restart the backend: on the `winlog-api` page, **Manual Deploy → Restart service** (or deploy
the latest commit). The start script runs the migrations and then the demo reset before the
server accepts requests. The demo is also reset on every deploy and whenever the sleeping free
instance wakes up (§7.7).

## Environment variables

Change non-secret values in **`render.yaml`**, not in the Render Dashboard: a Blueprint sync
overwrites dashboard edits of every value the file sets. Only the two secrets are kept in the
Dashboard. Real values never go into `.env.example`, which documents every backend variable.

### Backend (`winlog-api`)

| Variable | Value | Comes from | Secret |
|---|---|---|---|
| `DATABASE_URL` | Neon direct connection string with `sslmode=require` | Render Dashboard (`sync: false`), step 1 | **yes** |
| `AI_API_KEY` | production-only OpenRouter key, $5 credit limit | Render Dashboard (`sync: false`), step 2 | **yes** |
| `CORS_ALLOWED_ORIGINS` | the static site's URL | `render.yaml` | no |
| `AI_PROVIDER` | `openai-compatible` | `render.yaml` | no |
| `AI_BASE_URL` | `https://openrouter.ai/api/v1` | `render.yaml` | no |
| `AI_MODEL` | `anthropic/claude-haiku-5.5` (`docs/decisions/default-model.md`) | `render.yaml` | no |
| `AI_SUGGESTION_TIMEOUT_SECONDS` | `15` | `render.yaml` | no |
| `AI_SUMMARY_TIMEOUT_SECONDS` | `60` | `render.yaml` | no |
| `AI_SUMMARY_MAX_TOKENS` | `16000` | `render.yaml` | no |
| `AI_SUMMARY_MAX_INPUT_CHARACTERS` | `50000` | `render.yaml` | no |
| `AI_DAILY_SUGGESTIONS_PER_USER` | `10` | `render.yaml` | no |
| `AI_DAILY_SUMMARIES_PER_USER` | `2` | `render.yaml` | no |
| `AI_DAILY_REQUESTS_GLOBAL` | `100` | `render.yaml` | no |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `10` | `render.yaml` | no |
| `LOGIN_ATTEMPT_WINDOW_MINUTES` | `15` | `render.yaml` | no |
| `DEMO_LOGIN_MAX_ATTEMPTS` | `20` | `render.yaml` | no |
| `DEMO_LOGIN_WINDOW_MINUTES` | `60` | `render.yaml` | no |
| `TOKEN_LIFETIME_DAYS` | `7` | `render.yaml` | no |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `3` | `render.yaml` | no |
| `DEMO_EMAIL` | `demo@example.com` (the reset creates it before the server accepts requests, so nobody can register it first) | `render.yaml` | no |
| `PORT` | the port the server listens on | set by Render itself; not in `render.yaml` | no |

Not set in production, on purpose: `OTEL_EXPORTER_OTLP_ENDPOINT` (no telemetry export, #92),
and the variables only Docker Compose or the tests use (`POSTGRES_*`, `*_HOST_PORT`,
`VITE_API_BASE_URL` on the backend, `TEST_DATABASE_URL`).

### Static site (`winlog-app`)

| Variable | Value | Comes from | Secret |
|---|---|---|---|
| `VITE_API_BASE_URL` | the backend's URL, built into the JavaScript (public) | `render.yaml` | no |
| `NODE_VERSION` | `26.13.0`, the version in `frontend/.nvmrc`; the build log prints `Node v26.13.0` | `render.yaml` | no |

The static site publishes `frontend/dist`. A rewrite sends every path that is not a built file
to `/index.html`, so reloading `/review`, `/summaries/<id>` or `/entries/new` shows the app;
files under `/assets/` are still served as files.

## Switching the AI model

`AI_MODEL` can be switched to the backup model `deepseek/deepseek-v4.1-flash`
(`docs/decisions/default-model.md`). Before switching, check its current prices and its
zero-data-retention endpoints with the free `check` command. It runs in a developer checkout
(the comparison is not in the backend image), reads only OpenRouter's public model lists, and
makes no AI call and needs no key:

```
cd backend
uv run python -m scripts.model_comparison check deepseek/deepseek-v4.1-flash
```

Then change `AI_MODEL` in `render.yaml` with a normal task and merge it.

## Free-plan limits

Production uses free plans only. **No paid plan is chosen without the product owner's
approval.** The figures below are the providers' free allowances as remembered when this file
was written; check the current numbers on Render's and Neon's pricing pages.

- **Cold start (§12):** the free backend instance sleeps after 15 minutes without requests.
  The first request after that wakes it: the container starts, runs the migrations and the
  demo reset, and then answers. That can take about a minute. The Neon compute also scales to
  zero when idle and needs a moment to resume.
- **Render free web services:** a monthly allowance of free instance hours per workspace
  (about 750), 512 MB memory, and a monthly outbound bandwidth allowance. When an allowance
  runs out, Render suspends free services until the next month.
- **Render static sites:** free, with monthly bandwidth and build-minute allowances.
- **Neon free plan:** one small compute with a monthly compute-hour allowance, about 0.5 GB of
  storage per project, and scale to zero after a few minutes idle.

## Do not run the end-to-end test against production

`npm run test:e2e` (`frontend/e2e/`) expects the mock AI (`AI_PROVIDER=mock`). Against
production it would register test data and draft a summary with the **real** AI, which costs
money and needs the product owner's approval first (`AGENTS.md`). Never point `E2E_BASE_URL`
at the production URLs. Run it only against a local system.

## Live checks after a deploy

Section C of issue #38 lists the checks on the live app (health, HTTPS, CORS, the main flows,
the demo reset on start, demo-login counts per visitor). Real AI calls in those checks need
the product owner's explicit approval in that session, with a cost estimate.

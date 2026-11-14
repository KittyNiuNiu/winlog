# Deployment: GitHub Actions, Render and Neon

How Winlog is built, deployed to the hosted **dev** environment and promoted to **production**,
how to roll back, and how to set it all up (issues #38 and #39, `docs/product-spec.md` §10.2
and §10.4).

| Part | Dev | Production | Defined in |
|---|---|---|---|
| Backend (FastAPI) | Render web service `winlog-api-dev` | Render web service `winlog-api` | `render.yaml`, `backend/Dockerfile`, `backend/start.sh` |
| Backend image | `ghcr.io/kittyniuniu/winlog-backend`, tag `:dev` | the same image, tag `:production` | `.github/workflows/ci.yml`, `.github/workflows/deploy.yml` |
| Frontend (React build) | Render static site `winlog-app-dev` | Render static site `winlog-app` | `render.yaml` |
| Database | Neon project for dev, PostgreSQL 18, AWS eu-central-1, test data only | Neon project for production, PostgreSQL 18, AWS eu-central-1 | Neon console |
| AI | the mock (`AI_PROVIDER=mock`), no key, no cost | OpenRouter, zero data retention, `anthropic/claude-haiku-5.5` | `render.yaml`, OpenRouter account |

Both backends are free web services in Render's Frankfurt region that run the prebuilt image;
both frontends are free static sites on Render's CDN. All four services are defined in one
Render Blueprint, `render.yaml` in the repository root.

**Secrets never go into git, an issue, a comment, a chat, a log or a task summary.** They are
typed only into the Neon, OpenRouter, Render and GitHub settings pages named below. There are
seven: three in Render (`DATABASE_URL` of each backend, `AI_API_KEY` of production) and four
deploy hook URLs in GitHub ([Secrets](#secrets)).

> **Where the wording comes from.** The Render steps were checked against Render's
> documentation (render.com/docs, 14 November 2026) by a session that could read it but not
> open the Render Dashboard. The GitHub steps follow GitHub's documentation. The Neon and
> OpenRouter wording is from memory. Field names in `render.yaml` were checked against Render's
> Blueprint JSON schema. If a page looks different, follow its current wording; what each step
> must achieve stays the same. Report every difference, so this guide is corrected.

## The pipeline

Every push runs **CI**. Only a commit on `main` whose CI run passed goes further:

```
push to any branch ──► CI (all jobs) ──► branch other than main: stop, nothing is pushed or deployed
                                     └─► main, every CI job passed:
                                          Deploy workflow
                                          1. Publish image ──► ghcr.io/kittyniuniu/winlog-backend:sha-<commit>
                                          2. Deploy to dev  ──► winlog-api-dev (image by digest), winlog-app-dev (same commit)
                                          3. Deploy to production: waits for the product owner's approval
                                                            ──► winlog-api (same digest), winlog-app (same commit)
```

1. **CI** (`.github/workflows/ci.yml`, every push to every branch): Contract, Backend, Frontend,
   Tests, **Backend image** and Full system with the end-to-end test. The Backend image job
   builds the backend image for `linux/amd64` from `backend/Dockerfile` with `backend/` as the
   context, fails if the image holds any file named `.env` or `.env.<anything>`, and checks the
   `org.opencontainers.image.source` label that links the package to this repository. CI pushes
   nothing. On `main` it keeps the checked image as the run's `backend-image` artifact. No CI
   job has a condition that skips it on `main`.
2. **Deploy** (`.github/workflows/deploy.yml`) starts when a CI run for a push to `main` has
   finished, and does something only when that CI run **passed**: every job succeeded. A failed
   or cancelled CI run (for example one cancelled by a newer push to `main`) deploys nothing for
   its commit. On pushes to other branches the workflow also runs, so GitHub checks the file,
   but all its jobs are skipped.
   1. **Publish image** pushes the image CI built and checked for that commit to
      `ghcr.io/kittyniuniu/winlog-backend:sha-<40-character commit SHA>`. It builds nothing.
      Its summary shows the commit SHA and the image digest (`sha256:…`).
   2. **Deploy to dev** (GitHub environment `dev`) calls `winlog-api-dev`'s deploy hook with
      `imgURL=ghcr.io/kittyniuniu/winlog-backend@sha256:…`, so Render deploys exactly that
      image; moves the `:dev` tag to that digest; calls `winlog-app-dev`'s deploy hook with
      `ref=<commit SHA>`, so Render builds the same commit; and then waits up to 10 minutes until
      `GET https://winlog-api-dev.onrender.com/health` and `https://winlog-app-dev.onrender.com/`
      both answer 200. Its summary says which commit and digest the production step will deploy.
   3. **Deploy to production** (GitHub environment `production`) waits until the product owner
      approves it, then does the same for `winlog-api` (the **same digest**, tag
      `:production`) and `winlog-app` (the same commit), and waits for
      `https://winlog-api.onrender.com/health` and `https://winlog-app.onrender.com/`. It builds
      nothing. If the dev deploy failed, the production step is never offered.

A deploy hook that does not answer 2xx, or a missing hook secret, fails the job with a message
that names the service or the secret, never the URL. If the backend's hook succeeded and the
static site's hook then fails, that environment runs the new backend with the previous app until
the failed job is re-run (**Re-run this job**; in production it waits for approval again). The
two static sites are separate builds
of the same commit, because `VITE_API_BASE_URL` is built into the JavaScript (#25).

**What the pipeline cannot see.** Render keeps the previous deploy live until a new one is
healthy, so a 200 from `/health` right after a hook does not prove that the new image is live.
Without a Render API key (which GitHub does not hold) the job cannot read Render's deploy status.
That is why the person approving production checks the dev service's **Events** in Render first.

**One deploy per environment at a time.** Each deploy job has its own concurrency group
(`deploy-dev`, `deploy-production`) that never cancels a running deploy. A newer run's deploy
waits until the running one has finished. If yet another run arrives, GitHub cancels the
*waiting* one (not the running one) and keeps the newest. A production step that is waiting for
approval can hold the production group, so approve or reject old waiting production steps.

**Deploys that name no image.** Render deploys an image service without a named image after a
Blueprint sync, a changed environment variable, or **Manual Deploy → Deploy latest reference**.
Then it pulls the tag in `render.yaml`: `:dev` for `winlog-api-dev`, `:production` for
`winlog-api`. The pipeline moves each tag to the digest it deploys, right after Render accepted
that deploy, so such a deploy gets the image the pipeline last deployed to that environment,
never a newer one. Static sites have no tag: a sync or **Deploy latest commit** builds the
newest commit on `main`, which may be newer than the one approved. Redeploy a static site with
**Manual Deploy → Deploy a specific commit** and the commit from the last Deploy run (or re-run
that run's production step, [Roll back](#rollback-and-emergencies)).

### Where to see each step

| Step | GitHub | Render Dashboard |
|---|---|---|
| CI | **Actions** tab → workflow **CI** → the run for the commit | – |
| The image | the **Deploy** run → job **Publish image** → its summary (commit and digest); the package page `winlog-backend` (repository page → **Packages**) lists each version with its tags | – |
| Dev | the **Deploy** run → job **Deploy to dev** and its summary; **Environments** → `dev` on the repository page lists the deployments | `winlog-api-dev` and `winlog-app-dev` → **Events** (each deploy, its image or commit, and whether it is live) and **Logs** |
| Production | the **Deploy** run → job **Deploy to production**: "Waiting for review" until approved | `winlog-api` and `winlog-app` → **Events** and **Logs** |

## Promote to production

The product owner approves every production deploy. **No agent approves a deployment, re-runs
the production job or calls a deploy hook**, even though agents work through the same GitHub
account.

1. Open the repository's **Actions** tab → workflow **Deploy** → the run for the commit. The
   job **Deploy to production** shows "Waiting for review".
2. Read the **Deploy to dev** summary: it names the commit and the digest
   (`ghcr.io/kittyniuniu/winlog-backend@sha256:…`) the production step will deploy.
3. Check dev **before** approving:
   - In the Render Dashboard, `winlog-api-dev` → **Events**: the deploy of exactly this digest
     is the live one (not failed, not still in progress).
   - `winlog-app-dev` → **Events**: the deploy of this commit is live.
   - Open https://winlog-app-dev.onrender.com: the app loads, **Try the demo** shows the sample
     entries, and the change in this commit works.
4. In the run, click **Review deployments**, select `production`, optionally write a comment,
   and click **Approve and deploy**. To skip this commit, click **Reject** instead; a newer run
   will offer its own production step.
5. Watch the job **Deploy to production** finish, then `winlog-api` → **Events** (the same
   digest is live) and `winlog-app` → **Events** (the same commit is live).

The approval itself happens only on GitHub, and the production hook URLs are readable only
after it. Approving costs nothing; production's AI costs come only from users' requests.

## Rollback and emergencies

**None of these undo database migrations.** The backend applies migrations when it starts
(`backend/start.sh`), and an older image does not downgrade the schema. Before going back, check
the migrations added since that image (`backend/migrations/versions/`): an older image must
still work with the newer schema. If it cannot, fix forward with a new commit instead.

### Promote an earlier image again (preferred)

1. **Actions** → workflow **Deploy** → open the earlier run whose image you want back (its
   **Publish image** summary shows the commit and digest). GitHub re-runs jobs only up to 30 days
   after a run started.
2. Open its job **Deploy to production** → **Re-run this job** (or **Re-run jobs** → the
   production job). GitHub re-runs only that job, with the digest and commit that run published.
3. Approve it as in [Promote to production](#promote-to-production). The job deploys that
   digest and commit and moves `:production` back to that digest.

The same works for dev with the earlier run's **Deploy to dev** job; a re-run of it also re-runs
the production step after it, which then waits for approval again (reject it if not wanted).

### Render's own rollback

On a service's **Deploys** page in the Render Dashboard, click **Rollback** next to a recent
successful deploy, then **Rollback to this deploy**. On free instances Render offers only the two
most recent previous deploys. An image service rolls back to the exact digest of that deploy,
because the pipeline deploys by digest; every `sha-<commit>` image stays in GHCR, which a
rollback needs. A static site rolls back to that deploy's build.

Afterwards the `:production` (or `:dev`) tag still points to the newer image, so a later deploy
that names no image would bring it back. As soon as GitHub Actions works, re-run the production
step of the run that matches the rolled-back image (above), so tag and service agree again.

### When GitHub Actions is down

New images cannot be built then: images are built only in GitHub Actions, never on a developer's
machine or on Render. Only images already in GHCR can be deployed:

- **Redeploy what each environment last got from the pipeline:** the backend's **Manual Deploy
  → Deploy latest reference** (it pulls `:production` or `:dev`). For a static site, **Manual
  Deploy → Deploy a specific commit** with the commit from the last Deploy run.
- **Go back:** Render's rollback (above).
- **Deploy one specific image by hand:** find its digest on the GHCR package page (each version
  lists its tags `sha-<commit>` and its digest). Copy the service's deploy hook URL from the
  service's **Settings** page in Render. In your own terminal (bash), without the URL on any
  command line, in the shell history or in the process list:

  ```
  read -rs HOOK          # paste the deploy hook URL, then press Enter
  printf 'url = "%s&imgURL=ghcr.io%%2Fkittyniuniu%%2Fwinlog-backend%%40sha256%%3A%s"\n' \
    "$HOOK" '<digest without sha256:>' |
    curl --silent --output /dev/null --write-out '%{http_code}\n' --request POST --config -
  unset HOOK
  ```

  `printf` is built into bash, so the URL reaches curl only on its standard input, as in the
  pipeline.

  `200` or `202` means Render accepted the deploy. Production still gets only an image that has
  run in dev. Afterwards, re-run the matching production step once GitHub Actions works, so the
  `:production` tag follows.

## The dev environment

- **URLs:** backend https://winlog-api-dev.onrender.com, app https://winlog-app-dev.onrender.com.
  They are public but are not announced: the README names only the production URLs (#40).
- **AI:** the mock provider (`AI_PROVIDER=mock`). Dev has no AI key and never makes a real AI
  call, so it costs nothing per request. Suggestions and summaries show the mock's text.
- **Data:** test data only, in dev's own Neon project. **Never copy real or production data
  into dev**, and never point dev's `DATABASE_URL` at the production database.
- **Demo account:** reset on every start, as in production (`DEMO_EMAIL=demo@example.com`).
- **End-to-end test:** may run against dev ([below](#end-to-end-test-dev-yes-production-never)).
- **Deploys:** automatic after every passing CI run on `main`, and only then. Anything
  merged into `main` reaches dev within minutes, and production only after approval.

## Secrets

| Secret | Where it is kept | Value from | Used by |
|---|---|---|---|
| `DATABASE_URL` of `winlog-api` | Render, `winlog-api` → **Environment** (`sync: false`) | production Neon project, direct connection string | the production backend |
| `AI_API_KEY` of `winlog-api` | Render, `winlog-api` → **Environment** (`sync: false`) | OpenRouter production key, $5 credit limit | the production backend |
| `DATABASE_URL` of `winlog-api-dev` | Render, `winlog-api-dev` → **Environment** (`sync: false`) | dev Neon project, direct connection string | the dev backend |
| `RENDER_API_DEPLOY_HOOK` in environment `dev` | GitHub, **Settings → Environments → `dev`** → environment secrets | `winlog-api-dev` → **Settings** → Deploy Hook | job **Deploy to dev** |
| `RENDER_APP_DEPLOY_HOOK` in environment `dev` | GitHub, environment `dev` | `winlog-app-dev` → **Settings** → Deploy Hook | job **Deploy to dev** |
| `RENDER_API_DEPLOY_HOOK` in environment `production` | GitHub, environment `production` | `winlog-api` → **Settings** → Deploy Hook | job **Deploy to production**, only after approval |
| `RENDER_APP_DEPLOY_HOOK` in environment `production` | GitHub, environment `production` | `winlog-app` → **Settings** → Deploy Hook | job **Deploy to production**, only after approval |

GitHub holds only these four deploy hook URLs, all as **environment** secrets: no repository
secret, no Render API key, no registry password and no personal access token. The image push and
the tag moves use the workflow's own `GITHUB_TOKEN`. The GHCR package is public, so Render pulls
it without a credential.

A deploy hook URL is a secret: anyone with it can start a deploy. If one may have leaked, click
**Regenerate Hook** on the service's **Settings** page in Render and replace the GitHub secret
with the new URL.

## The one-off migration of the live production (#39)

Production moved from "Render builds `main` after CI passes" (#38) to the pipeline above. Do the
steps **in this order**. Production keeps its two URLs, its Neon database and its two secrets,
and keeps serving throughout: every step that could fail leaves the previous deploy live.
Production never runs an image that has not run in dev first.

**Before the pull request is merged** (production runs exactly as before):

1. **Render: turn off automatic deploys of the two production services.** `winlog-api` →
   **Settings** → **Auto-Deploy** → **Off** → save. Then the same for `winlog-app`. Check that
   both services' **Settings** now show **Off**. Until the Blueprint sync (step 8), both still
   have their #38 setting **After CI Checks Pass** (`autoDeployTrigger: checksPass`): Render
   would build every new commit on `main` and deploy it to production as soon as that commit's
   checks have passed, with no approval and without dev. The **Deploy** workflow's checks appear only after CI has finished,
   so they cannot stop that. With **Off**, Render deploys these two services only when someone
   starts a deploy (by hand, or later through their deploy hooks); their live deploys keep
   serving. The setting stays **Off** after the migration: `render.yaml` sets
   `autoDeployTrigger: "off"` for `winlog-app`, and for `winlog-api` it leaves the field out,
   which keeps the current value and has no effect on an image service (Render's Blueprint
   reference). (A `[skip render]` in the merge commit's message would skip only that one
   commit, so this guide does not rely on it.)
2. **Render: stop automatic Blueprint syncs.** Open the Blueprint (Dashboard → **Blueprints** →
   the Winlog Blueprint) → **Settings** → set **Auto Sync** to **No**. Otherwise the merge would
   sync `render.yaml` at once, before the image, the dev database and the hooks exist.
3. **GitHub: create the environment `dev`.** Repository → **Settings** → **Environments** →
   **New environment** → name `dev` → **Deployment branches** → **Selected branches and tags** →
   **Add deployment branch or tag rule** → Branch, `main` → **Add rule**. No reviewers.
4. **GitHub: create the environment `production`.** The same, with the name `production` and
   the branch rule `main`, and also:
   - **Required reviewers**: the product owner → **Save protection rules**;
   - leave **Prevent self-review** off: the product owner starts the runs (by merging) and
     approves them;
   - turn **Allow administrators to bypass configured protection rules** off, so the only way
     into production is the approval → **Save protection rules**.

   Add no secrets yet.

**Merge the pull request into `main`.** From now on, **merge nothing else into `main` until
step 13 is done.** Step 1 already keeps any merge out of production; the freeze also leaves one
Deploy run to follow and to re-run. What happens then:

- CI runs for the merge commit. When every job has passed, the **Deploy** workflow runs:
  **Publish image** pushes the first image, `ghcr.io/kittyniuniu/winlog-backend:sha-<commit>`
  (this creates the GHCR package, private at first). **Deploy to dev** then fails at "Check the
  deploy hook secrets", because the secrets do not exist yet. That is expected. **Deploy to
  production** is skipped.
- **Production is not changed.** The pipeline cannot reach it yet, and Render does not build the
  merge commit, because step 1 turned automatic deploys off. Check it once CI has finished:
  `winlog-api` → **Events** and `winlog-app` → **Events** show no new deploy.
- If one of them does show a deploy of the merge commit, step 1 was missed for that service: set
  its **Auto-Deploy** to **Off** now. If that deploy is still in progress, click **Cancel deploy**
  on its **Deploys** page (the previous deploy stays live). If it is already live, roll back to
  the previous deploy as in [Render's own rollback](#renders-own-rollback). Then continue.
- If step 2 was missed, Render syncs `render.yaml` right after the merge and makes step 8's
  changes early: the backends' first image deploys fail because the tags do not exist yet, and
  Render keeps the current production deploy live. Continue with step 5.

**After the merge:**

5. **GHCR: make the package public.** On the repository page → **Packages** → `winlog-backend`
   → **Package settings** → under "Danger Zone", **Change visibility** → **Public** → type the
   package name → confirm. GitHub warns that this cannot be undone (the repository is public and
   the image holds only its code; the product owner confirmed this on 2026-11-14). On the same
   page, check that the package is linked to `KittyNiuNiu/winlog` (the label does that).
6. **Neon: create the dev project.** **New project**, a name such as `winlog-dev`, PostgreSQL
   18, region AWS eu-central-1 (Frankfurt), free plan. Leave it empty: the backend's first start
   creates the tables and the demo account. Copy its **direct** connection string as in
   [Set up from scratch](#set-up-from-scratch), step 1. It goes only into step 9.
7. **Render: review the Blueprint sync.** Open the Blueprint → **Manual Sync**. Render lists
   what it will change. It should be exactly:
   - new web service `winlog-api-dev` (image) and new static site `winlog-app-dev`;
   - `winlog-api`: runtime from Docker to image `ghcr.io/kittyniuniu/winlog-backend:production`,
     no other change to its values.

   `winlog-app` should not be listed: its only change in `render.yaml` is auto-deploy off,
   which step 1 already made. If it is listed with auto-deploy, do not apply: set its
   **Auto-Deploy** to **Off** (step 1) and open **Manual Sync** again, because a sync redeploys
   every service it changes, and `winlog-app` would then build the newest commit on `main`
   before that commit has run in dev. If the list shows anything else, or a new name for an
   existing service, stop and report it.
8. **Apply the sync.** Expect:
   - `winlog-app-dev` builds the latest commit on `main` and goes live;
   - `winlog-api-dev`'s first deploy **fails** (no `:dev` image yet, and no `DATABASE_URL`);
   - `winlog-api` keeps its URL and its secrets. Its deploy of `:production` **fails** with an
     image pull error, because that tag does not exist until step 13. A failed deploy leaves the
     previous one live (Render's docs on zero-downtime deploys), so production keeps serving its
     Render-built deploy. Check
     https://winlog-api.onrender.com/health still answers `{"status": "ok", "database": "ok"}`.
   - `winlog-app` keeps its URL and its live deploy, with no new deploy.

   Render's docs say a service's runtime can change in a Blueprint (except for static sites), and
   the Dashboard can also change a service's source (**Settings → Build → Source → Edit**, the
   **Update Source** dialog). If the sync refuses to change `winlog-api`, or offers it only as a
   new service with a new URL, **stop**: production is unchanged, and the product owner decides
   how to continue.
9. **Render: the dev database.** `winlog-api-dev` → **Environment** → add `DATABASE_URL` with
   the dev connection string from step 6 → save. Render asks for `sync: false` values only when a
   Blueprint is first created, so it does not ask for this one. A deploy started by saving fails
   again (still no `:dev` image), which is expected.
10. **Render: copy the four deploy hooks.** On each service's **Settings** page, copy its
    **Deploy Hook** URL: `winlog-api-dev`, `winlog-app-dev`, `winlog-api`, `winlog-app`.
11. **GitHub: add the four environment secrets** ([Secrets](#secrets)): Repository →
    **Settings** → **Environments** → `dev` → **Add environment secret**:
    `RENDER_API_DEPLOY_HOOK` (the `winlog-api-dev` hook) and `RENDER_APP_DEPLOY_HOOK` (the
    `winlog-app-dev` hook). Then `production`: `RENDER_API_DEPLOY_HOOK` (the `winlog-api` hook)
    and `RENDER_APP_DEPLOY_HOOK` (the `winlog-app` hook). Paste each URL only there.
12. **First dev deploy.** **Actions** → workflow **Deploy** → the run of the merge commit →
    **Re-run jobs** → **Re-run failed jobs**. **Deploy to dev** now deploys the image by digest,
    moves `:dev`, builds `winlog-app-dev` from the same commit and waits for both. Then check dev
    as in [Promote to production](#promote-to-production), step 3:
    https://winlog-api-dev.onrender.com/health answers `{"status": "ok", "database": "ok"}`.
13. **First production deploy.** Approve **Deploy to production** as in
    [Promote to production](#promote-to-production). `winlog-api` now deploys the image by
    digest, its first image deploy; if it fails, the previous deploy stays live. Then
    `winlog-app` builds the same commit. Check https://winlog-api.onrender.com/health and
    https://winlog-app.onrender.com. Other merges into `main` may resume.
14. **Leave Auto Sync off, and the static sites' Auto-Deploy off.** With Auto Sync on, a
    merged change to `render.yaml` would also rebuild the static sites from the newest commit on
    `main` before that commit was approved. Instead, when a change to `render.yaml` has been
    promoted to production, open the Blueprint and click **Manual Sync**. A sync redeploys the
    backends from their tags, which point to the images the pipeline last deployed. (A deploy
    hook called with `ref`, as the pipeline does for the static sites, also turns a service's
    auto-deploy off, Render's docs on deploying a specific commit.)

**The proof (#39, section B)** comes from the next ordinary merge into `main` after these steps
(step 8 itself starts a production deploy, so the migration run does not show the normal order).
For that run, report: when the CI run finished; when `winlog-api-dev` and `winlog-app-dev`
started deploying in Render's **Events** (the backend deploy names the digest, the static site
deploy the commit); that production showed no new deploy until the approval; and that
`winlog-api` then deployed the same digest and `winlog-app` the same commit. Also report the two
dev URLs. None of these are secrets.

## Set up from scratch

For a new Render workspace or after losing everything. You need the GitHub, Render, Neon and
OpenRouter accounts.

### 1. Neon: two projects and their connection strings

1. Create two projects (PostgreSQL 18, region AWS eu-central-1, Frankfurt, free plan): one for
   production, one for dev.
2. For each, open **Connect** (connection details) for the project's database.
3. Choose the **direct** connection, not the pooled one: turn **Connection pooling** off. The
   direct host name has no `-pooler` in it. Alembic and SQLAlchemy keep their own normal
   session connections, which the pooled endpoint is not meant for.
4. Copy the connection string. It looks like
   `postgresql://<user>:<password>@<endpoint>.eu-central-1.aws.neon.tech/<database>?sslmode=require`
   (Neon may add `&channel_binding=require`). Keep the whole query part, especially
   `sslmode=require`: the connection must use TLS. The backend accepts `postgresql://` URLs
   as they are.
5. Each string is a secret (it contains the password). The production one goes only into
   `winlog-api`'s `DATABASE_URL`, the dev one only into `winlog-api-dev`'s.

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
4. The key is a secret. It goes only into `winlog-api`'s `AI_API_KEY` (step 4). Dev needs no key.


### 3. GitHub: the two environments

Create `dev` and `production` as in [the migration](#the-one-off-migration-of-the-live-production-39),
steps 3 and 4. Then merge (or push) the branch with the workflows into `main`, let CI pass, and
make the GHCR package public (migration step 5). The first **Deploy** run fails at the missing
hook secrets; that is expected.

### 4. Render: create the Blueprint

1. In the Render Dashboard: **New → Blueprint**, connect the GitHub repository, choose the
   branch `main`. Render reads `render.yaml` and lists four services: `winlog-api` and
   `winlog-api-dev` (web services, image) and `winlog-app` and `winlog-app-dev` (static sites).
2. Render asks for the three `sync: false` values. Paste:
   - `DATABASE_URL` of `winlog-api`: the production Neon string (step 1);
   - `AI_API_KEY` of `winlog-api`: the production OpenRouter key (step 2);
   - `DATABASE_URL` of `winlog-api-dev`: the dev Neon string (step 1).
3. Apply the Blueprint. The static sites build; the backends' first deploys fail, because the
   `:dev` and `:production` tags do not exist yet. (If Render refuses to create an image
   service whose tag does not exist yet, stop and report it, so this guide is corrected.)
4. Check the public URLs ([below](#the-public-urls)).
5. Set the Blueprint's **Auto Sync** to **No** (migration step 14).

### 5. Hooks and the first deploys

Do steps 10 to 13 of the migration: copy the four deploy hooks into the GitHub environment
secrets, re-run the failed jobs of the Deploy run, check dev, then approve production. The
backend's first start runs all migrations and creates the demo account.

The `sync: false` values are entered only once. Later Blueprint syncs do not ask again and keep
them. To change one (a new key, a new database password), edit it on the service's
**Environment** page in the Render Dashboard and save; the backend then restarts with it, using
the image its tag points to.

## The public URLs

Six values depend on the services' public URLs, written as `https://<host>` without a trailing
slash. They are in `render.yaml` and `.github/workflows/deploy.yml`, so they are reviewed in git:

| Value | Where | Must be |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` of `winlog-api` | `render.yaml` | `https://winlog-app.onrender.com` (production static site) |
| `VITE_API_BASE_URL` of `winlog-app` (build time) | `render.yaml` | `https://winlog-api.onrender.com` (production backend) |
| `CORS_ALLOWED_ORIGINS` of `winlog-api-dev` | `render.yaml` | `https://winlog-app-dev.onrender.com` (dev static site) |
| `VITE_API_BASE_URL` of `winlog-app-dev` (build time) | `render.yaml` | `https://winlog-api-dev.onrender.com` (dev backend) |
| `API_URL`, `APP_URL` of the job Deploy to dev | `deploy.yml` | the dev backend's and static site's URLs (health wait) |
| `API_URL`, `APP_URL` of the job Deploy to production | `deploy.yml` | the production URLs (health wait) |

Render gives each service the host `<service name>.onrender.com`. If a name is already taken
by someone else, Render adds a suffix (for example `winlog-api-dev-abcd.onrender.com`). Each
service shows its real URL at the top of its page in the Render Dashboard. **When a service is
created, compare its URL with the table.** If one differs:

1. To get running at once, set the real value on the other service's **Environment** page in
   the Dashboard: the static site's URL in its backend's `CORS_ALLOWED_ORIGINS`, or the
   backend's URL in its static site's `VITE_API_BASE_URL`.
2. `VITE_API_BASE_URL` is built into the JavaScript files, so it takes effect only with a new
   static-site build: **Manual Deploy → Deploy a specific commit** with the commit last deployed
   to that environment (or clear the build cache first if the old value persists). A change to
   `CORS_ALLOWED_ORIGINS` needs only a backend restart, which Render does when the value changes.
3. Put the same value into `render.yaml` and `deploy.yml` with a normal task and merge it, so
   the next Blueprint sync keeps it and the health wait checks the right host.

The static-site build refuses to run with an empty `VITE_API_BASE_URL` and prints
`VITE_API_BASE_URL is required`, as `frontend/Dockerfile` does, so a forgotten value cannot
produce a site that calls no backend.

## What the backend does on every start

`backend/start.sh` is the image's start command. It runs on every container start: every
deploy, every manual restart, and every wake of the sleeping free instance, in dev and in
production.

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

## Environment variables

Change non-secret values in **`render.yaml`**, not in the Render Dashboard: a Blueprint sync
overwrites dashboard edits of every value the file sets. Only the three secrets are kept in the
Dashboard. Real values never go into `.env.example`, which documents every backend variable.
After a merged change to `render.yaml` has been promoted, start a **Manual Sync** of the
Blueprint (Auto Sync stays off).

### Backend (`winlog-api`)

| Variable | Value | Comes from | Secret |
|---|---|---|---|
| `DATABASE_URL` | Neon direct connection string with `sslmode=require` | Render Dashboard (`sync: false`), [Neon](#1-neon-two-projects-and-their-connection-strings) | **yes** |
| `AI_API_KEY` | production-only OpenRouter key, $5 credit limit | Render Dashboard (`sync: false`), [OpenRouter](#2-openrouter-account-settings-and-the-production-key) | **yes** |
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


### Dev backend (`winlog-api-dev`)

The same as `winlog-api`, except these rows:

| Variable | Value | Comes from | Secret |
|---|---|---|---|
| `DATABASE_URL` | the **dev** Neon project's direct connection string with `sslmode=require` | Render Dashboard (`sync: false`), [Neon](#1-neon-two-projects-and-their-connection-strings) | **yes** |
| `CORS_ALLOWED_ORIGINS` | `https://winlog-app-dev.onrender.com` | `render.yaml` | no |
| `AI_PROVIDER` | `mock` | `render.yaml` | no |
| `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | not set: the mock needs none, and dev never calls a real AI | – | – |

All other values (timeouts, AI usage limits, login limits, token lifetime, database timeout,
`DEMO_EMAIL`) are the same as production's. Keep them the same when one changes.

### Static sites (`winlog-app`, `winlog-app-dev`)

| Variable | `winlog-app` | `winlog-app-dev` | Comes from | Secret |
|---|---|---|---|---|
| `VITE_API_BASE_URL` | `https://winlog-api.onrender.com` | `https://winlog-api-dev.onrender.com` | `render.yaml`, built into the JavaScript (public) | no |
| `NODE_VERSION` | `26.13.0` | `26.13.0` | `render.yaml`, the version in `frontend/.nvmrc`; the build log prints `Node v26.13.0` | no |

Both build with the same command and publish `frontend/dist`. A rewrite sends every path that is
not a built file to `/index.html`, so reloading `/review`, `/summaries/<id>` or `/entries/new`
shows the app; files under `/assets/` are still served as files. Both have
`autoDeployTrigger: off` and are built only through their deploy hooks with `ref=<commit SHA>`.

## Run the demo reset by hand

Restart the backend: on the `winlog-api` (or `winlog-api-dev`) page, **Manual Deploy → Restart
service**. The start script runs the migrations and then the demo reset before the server
accepts requests. The demo is also reset on every deploy and whenever the sleeping free
instance wakes up (§7.7), in dev and in production.

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

Then change `AI_MODEL` in `render.yaml` with a normal task, merge it, promote it, and sync the
Blueprint ([migration step 14](#the-one-off-migration-of-the-live-production-39)). Dev keeps the
mock.


## Free-plan limits

Dev and production use free plans only. **No paid plan is chosen without the product owner's
approval.** Render's figures below are from Render's documentation (14 November 2026); Neon's
are from search results and memory, so check Neon's pricing page.

- **Render free instance hours: one allowance for the whole workspace, shared by both
  backends.** Each workspace gets 750 free instance hours per calendar month. A free web service
  uses them while it runs; a spun-down service uses none. **If they run out, Render suspends
  every free web service in the workspace, production included, until the next month.** Two
  backends that never sleep would need about 1,488 hours in a 31-day month, so:
  - do not add an uptime pinger or anything else that keeps a backend awake;
  - dev wakes only for deploys and tests, so normal use stays far below the allowance;
  - check the hours used: Render Dashboard → **Billing** → **Monthly Included Usage**. Render
    also emails when the workspace approaches a limit.
- **Cold start (§12):** a free backend spins down after 15 minutes without requests. The first
  request after that wakes it: the container starts, runs the migrations and the demo reset,
  and then answers. That takes about a minute. The Neon compute also scales to zero when idle
  and needs a moment to resume. The deploy jobs wait up to 10 minutes for this.
- **Render bandwidth and pipeline minutes:** web services and static sites count against the
  workspace's monthly outbound bandwidth and build pipeline minutes. Each promoted commit builds
  the frontend twice (dev and production). If bandwidth runs out without a payment method,
  Render suspends the free services; if build minutes run out, new builds stop and services
  keep running.
- **Render rollbacks:** free web services can roll back only to the two most recent previous
  deploys. Re-running an earlier production step works for any run up to 30 days old.
- **Neon free plan:** dev has its own project and so its own allowance; it never uses
  production's. Each project gets a small compute with a monthly compute-hour allowance and a
  storage limit (search results said 100 projects, 100 CU-hours and 0.5 to 1 GB per project),
  and scales to zero after a few minutes idle.
- **GitHub:** Actions minutes are free on public repositories, and GHCR storage and transfer
  are free for public packages. Every `sha-<commit>` image stays in GHCR: rollbacks need it.

## End-to-end test: dev yes, production never

`npm run test:e2e` (`frontend/e2e/`) expects the mock AI. It registers a test account and drafts
a summary.

- **Dev** runs the mock, so the test may run against it, with no approval:
  `E2E_BASE_URL=https://winlog-app-dev.onrender.com npm run test:e2e` in `frontend/`. Each run
  leaves a test account in the dev database (test data only) and counts against dev's global
  daily AI limit.
- **Never against production.** There it would register test data and draft a summary with the
  **real** AI, which costs money and needs the product owner's approval first (`AGENTS.md`).
  Never point `E2E_BASE_URL` at `https://winlog-app.onrender.com`.

## Live checks after a deploy

Section C of issue #38 lists the checks on the live production app (health, HTTPS, CORS, the
main flows, the demo reset on start, demo-login counts per visitor), and section C of issue #39
the checks of dev, of the promotion and of the pipeline. Real AI calls in those checks need the
product owner's explicit approval in that session, with a cost estimate.

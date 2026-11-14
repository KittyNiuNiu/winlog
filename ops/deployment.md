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
> documentation (render.com/docs, 14 November 2026) by sessions that could read it but not open
> the Render Dashboard. The migration record and the Render steps of
> [Set up from scratch](#set-up-from-scratch) were then corrected from what the product owner
> saw in the Render Dashboard while migrating production on 14 November 2026 (issue #39). Three
> things there differ from what Render's documentation says or leaves out: a Blueprint sync is
> refused while an image tag it names does not exist; a sync did not keep an omitted
> `autoDeployTrigger`; and a service created from an image gets a **Name** pre-filled from the
> image. The GitHub steps follow GitHub's documentation. The Neon and OpenRouter wording is
> from memory. Field names in `render.yaml` were checked against Render's Blueprint JSON
> schema. If a page looks different, follow its current wording; what each step must achieve
> stays the same. Report every difference, so this guide is corrected.

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
      both answer 200. **This wait does not show that the new deploy is live:** the previous
      deploy keeps answering while the new one starts, so the wait can pass on the previous
      deploy. During the migration on 14 November 2026 it passed after 40 seconds in dev and
      after 1 second in production. Only the service's **Events** in Render show which deploy is live
      ([Promote to production](#promote-to-production), step 3). The job's summary says which
      commit and digest the production step will deploy.
   3. **Deploy to production** (GitHub environment `production`) waits until the product owner
      approves it, then does the same for `winlog-api` (the **same digest**, tag
      `:production`) and `winlog-app` (the same commit), and waits for
      `https://winlog-api.onrender.com/health` and `https://winlog-app.onrender.com/`. That wait,
      too, can pass on the previous deploy. It builds nothing. If the dev deploy failed, the
      production step is never offered.

A deploy hook that does not answer 2xx, or a missing hook secret, fails the job with a message
that names the service or the secret, never the URL. If the backend's hook succeeded and the
static site's hook then fails, that environment runs the new backend with the previous app until
the failed job is re-run (**Re-run this job**; in production it waits for approval again). The
two static sites are separate builds
of the same commit, because `VITE_API_BASE_URL` is built into the JavaScript (#25).

**What the pipeline cannot see.** Render keeps the previous deploy live until a new one is
healthy, so a 200 from `/health` right after a hook does not prove that the new image is live.
Without a Render API key (which GitHub does not hold) the job cannot read Render's deploy
status. A green deploy job shows only that Render accepted both deploys and that both URLs
answer. That is why the person approving production checks the dev service's **Events** in
Render first, and production's **Events** after the job.

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
3. Check dev **before** approving. A green **Deploy to dev** job is not enough: its wait can
   pass on the previous deploy ([The pipeline](#the-pipeline)). **Events** show whether the new
   deploy is live:
   - In the Render Dashboard, `winlog-api-dev` → **Events**: the deploy of exactly this digest
     is the live one (not failed, not still in progress).
   - `winlog-app-dev` → **Events**: the deploy of this commit is live.
   - Open https://winlog-app-dev.onrender.com: the app loads, **Try the demo** shows the sample
     entries, and the change in this commit works.
4. In the run, click **Review deployments**, select `production`, optionally write a comment,
   and click **Approve and deploy**. To skip this commit, click **Reject** instead; a newer run
   will offer its own production step.
5. Watch the job **Deploy to production** finish, then `winlog-api` → **Events** (the same
   digest is live) and `winlog-app` → **Events** (the same commit is live). The job can finish
   before the new deploys are live, for the same reason as in step 3.

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

## Blueprint syncs

Render applies `render.yaml` to the four services only when the Blueprint syncs.

- **Auto Sync stays No, and both static sites' Auto-Deploy stays Off.** With Auto Sync on, a
  merged change to `render.yaml` would sync at once, and a sync redeploys every service it
  changes: a static site would then build the newest commit on `main` before that commit was
  approved.
- **Sync by hand** once a change to `render.yaml` has been promoted to production: open the
  Blueprint → **Manual Sync**, read the list of changes, then apply it. Do it while the newest
  commit on `main` is the one production runs, because a static site the sync changes builds
  the newest commit on `main`. The backends redeploy from their tags, which point to the images
  the pipeline last deployed.
- **A sync is refused as a whole while an image tag it names does not exist.** On
  14 November 2026 Render refused one with "backend images not found" for `:dev` and
  `:production`. The pipeline creates each tag on its first deploy to that environment.
- **A sync takes over existing services by name** and keeps the environment values entered by
  hand, such as the `sync: false` secrets. On 14 November 2026 it listed the two dev services,
  created by hand, as **associated**, not new. If the list shows a new service for a name that
  already exists, or a name with a suffix, do not apply it: stop and report it.
- **The backends' auto-deploy setting shows "commit".** `render.yaml` leaves `autoDeployTrigger`
  out for the two image services. Render's Blueprint reference says an omitted value is kept for
  an existing service, but the sync of 14 November 2026 set both backends to "commit". This is
  harmless. An image service watches no repository: Render's documentation says the field has
  no effect on services that deploy a prebuilt image, and that they never redeploy when a new
  image gets their tag. A deploy that names no image pulls the environment's tag, which the
  pipeline moves only to a digest it has just deployed there. The static sites are Git-backed,
  so `render.yaml` sets `autoDeployTrigger: "off"` for them, and a deploy hook called with
  `ref`, as the pipeline does, also turns their auto-deploy off (Render's docs on deploying a
  specific commit).

## The one-off migration of the live production (#39)

**Done on 14 November 2026.** Production moved from "Render builds `main` after CI passes"
(#38) to the pipeline above. This is the record of the steps that worked, in the order they
were done. [Set up from scratch](#set-up-from-scratch) reuses steps 3 to 5. Production kept its
two URLs, its Neon database and its two secrets, and kept serving throughout. It never ran an
image that had not run in dev first.

**The one accepted deviation.** Production's first image deploy was started by hand (step 12,
**Update Source**), not by the approved production step. It was the image that had already run
in dev, after dev had been checked. This was the product owner's decision (Option A, issue #39,
14 November 2026): Render refused the Blueprint sync while the tags did not exist, and accepts a
deploy hook's `imgURL` only when it matches the service's own image URL, which `winlog-api` did
not have while Render still built it from Git. The approved step redeployed the same digest
minutes later. Every later image reaches production only through the approval.

**Before the pull request was merged** (production ran exactly as before):

1. **Render: turn off automatic deploys of the two production services.** `winlog-api` →
   **Settings** → **Auto-Deploy** → **Off** → save. Then the same for `winlog-app`. Check that
   both services' **Settings** now show **Off**. Until then both had their #38 setting **After
   CI Checks Pass** (`autoDeployTrigger: checksPass`): Render would have built every new commit
   on `main` and deployed it to production as soon as that commit's checks had passed, with no
   approval and without dev. The **Deploy** workflow's checks appear only after CI has
   finished, so they cannot stop that. (A `[skip render]` in the merge commit's message would
   skip only that one commit.) `winlog-app` stays **Off**; for `winlog-api` the setting no
   longer matters once it runs an image ([Blueprint syncs](#blueprint-syncs)).
2. **Render: stop automatic Blueprint syncs.** Open the Blueprint (Dashboard → **Blueprints** →
   the Winlog Blueprint) → **Settings** → set **Auto Sync** to **No**. Otherwise the merge would
   have synced `render.yaml` at once.
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

**The merge into `main`.** Pull request #100 was merged at 15:20 UTC as commit `7743b4f`. From
then on nothing else was merged into `main` until step 15 was done (the merge freeze), so the
newest commit on `main` stayed the one dev and production got. CI run 43609671948 passed. In
Deploy run 43610266675, **Publish image** pushed the first image,
`ghcr.io/kittyniuniu/winlog-backend:sha-7743b4f8ffe9ddeb3d2d30724ca585df11c5c6ea`, with the
digest `sha256:255ab53a4835096285cc43972e9de0cfceaac76fa68d082a9b3d02e7c3a53390`; this created
the GHCR package, private at first. **Deploy to dev** failed at "Check the deploy hook
secrets", as expected, and **Deploy to production** was skipped. `winlog-api` and `winlog-app`
showed no new deploy in **Events**.

**After the merge:**

5. **GHCR: make the package public.** On the repository page → **Packages** → `winlog-backend`
   → **Package settings** → under "Danger Zone", **Change visibility** → **Public** → type the
   package name → confirm. GitHub warns that this cannot be undone (the repository is public and
   the image holds only its code; the product owner confirmed this on 2026-11-14). On the same
   page, check that the package is linked to `KittyNiuNiu/winlog` (the label does that).
6. **Neon: create the dev project.** **New project**, the name `winlog-dev`, PostgreSQL 18,
   region AWS eu-central-1 (Frankfurt), free plan. Leave it empty: the backend's first start
   creates the tables and the demo account. Copy its **direct** connection string as in
   [Set up from scratch](#set-up-from-scratch), step 1. It goes only into step 7.

**The Blueprint sync was refused.** Blueprint → **Manual Sync** was refused as a whole: Render
reported "backend images not found" for `:dev` and `:production`, which only the pipeline
creates. Nothing changed in Render. So the dev services were created by hand first, and the
sync came last (step 15).

7. **Render: create `winlog-api-dev` from the image.** **+ New** → **Web Service** → **Existing
   Image**, image URL
   `ghcr.io/kittyniuniu/winlog-backend:sha-7743b4f8ffe9ddeb3d2d30724ca585df11c5c6ea` (public, no
   credential) → **Connect**. Name `winlog-api-dev`, region Frankfurt, instance type **Free**.
   Under **Advanced**: the health check path `/health` and four environment values,
   `DATABASE_URL` (the dev string from step 6), `AI_PROVIDER` = `mock`,
   `CORS_ALLOWED_ORIGINS` = `https://winlog-app-dev.onrender.com` and `DEMO_EMAIL` =
   `demo@example.com`. Render pre-fills the **Name** from the image (`winlog-backend-sha`), and
   the URL is fixed from the name when the service is created. The first try kept that name and
   got `winlog-backend-sha.onrender.com`, so that service was deleted and created again as
   `winlog-api-dev`. Its first deploy ran the image on the empty dev database, and
   https://winlog-api-dev.onrender.com/health answered `{"status": "ok", "database": "ok"}`.
8. **Render: create `winlog-app-dev`.** **New > Static Site**, this repository, branch `main`,
   name `winlog-app-dev`, publish directory `frontend/dist`, build command
   `cd frontend && npm ci --no-audit --no-fund && npm run build`, and the environment values
   `VITE_API_BASE_URL` = `https://winlog-api-dev.onrender.com` and `NODE_VERSION` = `26.13.0`.
   Once it was created: **Auto-Deploy** **Off**, and the rewrite rule with source `/*`,
   destination `/index.html` and action **Rewrite**. Its URL is
   https://winlog-app-dev.onrender.com.
9. **GitHub: the dev hooks.** Copy the **Deploy Hook** of `winlog-api-dev` and of
   `winlog-app-dev` (each service's **Settings**) into the environment `dev` as
   `RENDER_API_DEPLOY_HOOK` and `RENDER_APP_DEPLOY_HOOK` ([Secrets](#secrets)).
10. **First pipeline deploy to dev.** **Actions** → Deploy run 43610266675 → **Re-run jobs** →
    **Re-run failed jobs** (20:24 UTC). Render accepted both hooks (HTTP 200), the job moved
    `:dev` to the digest, and its wait passed at 20:25:40, on the deploys that were already live
    ([The pipeline](#the-pipeline)). **Deploy to production** then waited for approval.
11. **Check dev in Render's Events**, as in [Promote to production](#promote-to-production),
    step 3: both new deploys were live, the backend deploy named the digest, and **Try the
    demo** showed the sample entries.
12. **Render: switch `winlog-api` to the image dev runs.** `winlog-api` → **Settings** →
    **Build > Source** → **Edit** → in the **Update Source** dialog, the image
    `ghcr.io/kittyniuniu/winlog-backend@sha256:<the digest above>` (the field accepted the
    digest form) → submit. Render deployed it at once: production's first image deploy, the
    accepted deviation above. It is the same service, with the same URL, database and secrets.
    Afterwards https://winlog-api.onrender.com/health answered
    `{"status": "ok", "database": "ok"}`, and CORS still allowed only
    `https://winlog-app.onrender.com`.
13. **GitHub: the production hooks.** Copy the **Deploy Hook** of `winlog-api` and of
    `winlog-app` into the environment `production`, with the same two names.
14. **Approve.** The product owner approved **Deploy to production** in the same run
    ([Promote to production](#promote-to-production)); the job ran at 20:38 UTC. Render
    accepted the `winlog-api` hook with the same digest (a redeploy of what was live), the job
    moved `:production` to the digest, and Render accepted the `winlog-app` hook, which built
    commit `7743b4f`. Both deploys were live in **Events**, and the demo worked.
15. **Render: Manual Sync of the Blueprint.** With both tags in place, Render listed:
    - `winlog-api`: image `…@sha256:…` → `…:production`, auto-deploy trigger → "commit", base
      directory → `.`; no environment variable changes;
    - `winlog-api-dev`: **associated** (not new), image `…:sha-…` → `…:dev`, auto-deploy
      trigger → "commit", 13 environment variables created (the `render.yaml` values not
      entered in step 7);
    - `winlog-app-dev`: **associated** (not new), the build command, and the publish path
      `./frontend/dist`;
    - `winlog-app`: not listed.

    The sync was applied without errors, and every redeploy went live. The values entered by
    hand were kept. Production's `/health` stayed ok and its CORS unchanged.
16. **The merge freeze ended.** Merges into `main` resumed. Blueprint **Auto Sync** stays
    **No**, and both static sites' **Auto-Deploy** stays **Off**
    ([Blueprint syncs](#blueprint-syncs)).

**The proof (#39, section B)** comes from the first ordinary merge into `main` after the
migration, planned as the merge that brought this record into the guide. The migration run
cannot show the normal order, because production's first image deploy was started by hand. For
the proof run, report: when the CI run finished; when `winlog-api-dev` and `winlog-app-dev`
started deploying in Render's **Events** (the backend deploy names the digest, the static site
deploy the commit); that production showed no new deploy until the approval; and that
`winlog-api` then deployed the same digest and `winlog-app` the same commit. Take these from
**Events**, not from the deploy jobs' wait, which can pass on the previous deploy. Also report
the two dev URLs. None of these are secrets.

## Set up from scratch

For a new Render workspace or after losing everything. You need the GitHub, Render, Neon and
OpenRouter accounts.

The order follows what Render did during the migration ([Blueprint syncs](#blueprint-syncs)).
A Blueprint sync is refused while an image tag it names does not exist; creating a Blueprint
was not tried in that state, but Render checks that it can pull an image before it creates an
image service, so expect the same. Only the pipeline creates `:dev` and `:production`. So:

- the services are created by hand from the image `sha-<commit>`: dev first, production only
  after dev has been checked;
- the approval of the production step creates the tags;
- then the Blueprint is created, or synced, and takes over the services by name.

Creating a service deploys it at once, so production's first deploys are started by hand, with
the image and the commit dev runs. **Merge nothing else into `main` until step 6 is done:** a
static site builds the newest commit on `main` when it is created and when a sync changes it.

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
4. The key is a secret. It goes only into `winlog-api`'s `AI_API_KEY` (step 5). Dev needs no key.

### 3. GitHub: the two environments and the first image

Create `dev` and `production` as in [the migration](#the-one-off-migration-of-the-live-production-39),
steps 3 and 4. Then merge (or push) the branch with the workflows into `main` and let CI pass.
The **Deploy** run's **Publish image** pushes `ghcr.io/kittyniuniu/winlog-backend:sha-<commit>`,
and its summary shows the commit and the digest. **Deploy to dev** fails at the missing hook
secrets, which is expected. Make the GHCR package public (migration step 5).

### 4. Render: the dev services and the first dev deploy

1. **The dev backend.** **+ New** → **Web Service** → **Existing Image**, image URL
   `ghcr.io/kittyniuniu/winlog-backend:sha-<commit>` (the commit from step 3; the package is
   public, so no credential) → **Connect**. **Overwrite the pre-filled Name with
   `winlog-api-dev` before creating the service.** Render fills it in from the image (for
   example `winlog-backend-sha`), and the service's URL is fixed from the name when it is
   created: renaming it later does not change the URL. Region Frankfurt, instance type
   **Free**. Under **Advanced**: the health check path `/health`, and the environment values
   `DATABASE_URL` (the dev string, step 1), `AI_PROVIDER` = `mock`, `CORS_ALLOWED_ORIGINS` =
   `https://winlog-app-dev.onrender.com` and `DEMO_EMAIL` = `demo@example.com`. The backend's
   defaults for every other value are the values in `render.yaml`, and the Blueprint writes them
   all in step 6. Create the service: its first deploy runs the migrations on the empty
   database and creates the demo account.
2. **The dev static site.** **New > Static Site**, this repository, branch `main`, the name
   `winlog-app-dev` (check the **Name** here too), publish directory `frontend/dist`, build
   command `cd frontend && npm ci --no-audit --no-fund && npm run build`, and the environment
   values `VITE_API_BASE_URL` = `https://winlog-api-dev.onrender.com` and `NODE_VERSION` =
   `26.13.0`. Create it, then set its **Auto-Deploy** to **Off** and add the rewrite rule:
   source `/*`, destination `/index.html`, action **Rewrite**.
3. Compare both URLs with [the public URLs](#the-public-urls).
4. Copy both services' **Deploy Hook** into the GitHub environment `dev`:
   `RENDER_API_DEPLOY_HOOK` and `RENDER_APP_DEPLOY_HOOK` ([Secrets](#secrets)).
5. **Actions** → the **Deploy** run from step 3 → **Re-run jobs** → **Re-run failed jobs**.
   **Deploy to dev** deploys the image by digest, creates `:dev` and builds `winlog-app-dev`
   from the same commit. **Deploy to production** then waits for approval: do not approve it
   yet.
6. Check dev in **Events**, as in [Promote to production](#promote-to-production), step 3.

### 5. Render: the production services and the approval

Only after dev has been checked:

1. **The production backend**, as in step 4.1, with the same image `sha-<commit>` and the name
   `winlog-api`. Its environment values: `DATABASE_URL` (the production string, step 1),
   `AI_API_KEY` (the production key, step 2), `AI_PROVIDER` = `openai-compatible`,
   `AI_BASE_URL` = `https://openrouter.ai/api/v1`, `AI_MODEL` (its value in `render.yaml`),
   `CORS_ALLOWED_ORIGINS` = `https://winlog-app.onrender.com` and `DEMO_EMAIL` =
   `demo@example.com`.
2. **The production static site**, as in step 4.2, with the name `winlog-app` and
   `VITE_API_BASE_URL` = `https://winlog-api.onrender.com`; then **Auto-Deploy** **Off** and the
   rewrite rule.
3. Compare both URLs with [the public URLs](#the-public-urls), and check that
   https://winlog-api.onrender.com/health answers `{"status": "ok", "database": "ok"}`.
4. Copy both services' **Deploy Hook** into the GitHub environment `production`, with the same
   two names.
5. Approve **Deploy to production** in the same run
   ([Promote to production](#promote-to-production)). It deploys the same digest and commit
   again, through the hooks, and creates `:production`. Check both services' **Events**.

### 6. Render: the Blueprint

Now that both tags exist:

1. **New > Blueprint** → **Connect** this repository → a name for the Blueprint and the branch
   `main`; Render reads `render.yaml` at the root. If the Blueprint still exists, open it and
   click **Manual Sync** instead.
2. **Read the list before applying it.** Each of the four services must be taken over as the
   existing service of the same name, never created new. A sync of the existing Blueprint did
   that on 14 November 2026 (migration step 15). Whether **New > Blueprint** does the same was
   not observed, and Render's documentation reads both ways: its Blueprint reference says that
   for the name of an existing service "Render attempts to apply the Blueprint's configuration
   to that existing service", while its Blueprints page says the creation flow shows a notice
   when a new Blueprint matches existing resources and adds a suffix to the name of each new
   resource. If Render shows that notice, lists a new service for a name that exists, or adds a
   suffix to a name, **do not deploy the Blueprint**: stop and report it, so this guide is
   corrected. The services and the pipeline also work without a Blueprint, with the values
   entered by hand.
3. If Render asks for the `sync: false` values, enter the ones the services already have.
   Render asks for them only when a Blueprint is created; the sync of 14 November 2026 did not
   ask and kept them.
4. Click **Deploy Blueprint** (or apply the sync). The backends redeploy from their tags, the
   digest just approved. A static site the Blueprint changes rebuilds the newest commit on
   `main`, which is the approved one as long as nothing else has been merged.
5. Set the Blueprint's **Auto Sync** to **No** ([Blueprint syncs](#blueprint-syncs)). Merges
   into `main` may resume.

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

Render gives each service the host `<service name>.onrender.com`. The host is fixed when the
service is created: renaming the service later does not change it. When a service is created
from an image, Render pre-fills the **Name** from the image (for example `winlog-backend-sha`),
so overwrite it before creating the service. A service created by hand under a wrong name,
which nothing uses yet, can be deleted and created again with the right name, as
`winlog-api-dev` was on 14 November 2026. If a name is already taken by someone else, Render
adds a suffix (for example `winlog-api-dev-abcd.onrender.com`). Each service shows its real URL
at the top of its page in the Render Dashboard. **When a service is created, compare its URL
with the table.** If one differs:

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
Blueprint (Auto Sync stays off, [Blueprint syncs](#blueprint-syncs)).

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
Blueprint ([Blueprint syncs](#blueprint-syncs)). Dev keeps the mock.


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

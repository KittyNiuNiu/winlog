# AI workflow log

One entry per task done with an AI coding agent: date, task, what was done, how it was verified, and anything left open.

## 2026-11-01: Move the backlog from tasks.md into GitHub issues

- **Task:** Move each task from `tasks.md` into a GitHub issue.
- **What I did:** Created 39 issues (#2 to #40) in backlog order, one per task. Each issue keeps the task's title, Goal and Description text unchanged, plus a note with its position in the suggested build order. Replaced the task text in `tasks.md` with a numbered index that links to each issue, so the build order stays visible and the issues are the single source of truth.
- **How I verified it:** Listed the repository's issues and compared their numbers and titles against the 39 task headings from the old `tasks.md`; all 39 match, in order. Checked that every link in the new `tasks.md` points to the matching issue number.
- **Left open:** Issue numbers start at #2 because #1 is a pull request, so issue number = task number + 1. No labels, milestones or assignees were set, because the backlog did not define any.

## 2026-11-01: Add the process note

- **Task:** Create `docs/process.md` with three process rules (tasks are GitHub issues, one at a time; read the acceptance criteria before starting and before closing; commit regularly).
- **What I did:** Created `docs/process.md` with the three rules exactly as given.
- **How I verified it:** Compared the file's content with the requested text.
- **Left open:** The issues have a Goal and a Description but no "Acceptance criteria" section. The acceptance criteria live in `product-spec.md`, linked from each issue through its requirement IDs (for example FR-E1).

## 2026-11-01: Groom issue #2 (Write the OpenAPI contract)

- **Task:** Groom task 1 of the backlog (requested as "issue #1"; #1 is a pull request, so task 1 is issue #2), following `docs/pm.md`.
- **What I did:** Rewrote issue #2 using `docs/task-template.md`: Goal, checkable acceptance criteria, Out of scope with links, and Constraints. The product owner made five decisions when asked during grooming: bearer-token authentication with server-side, revocable tokens; a tag filter that matches entries with any of the selected tags; entry date required in the API, with the form pre-filling today's date; no pagination on the entry list in v1; size limits moved to a follow-up issue. Filed #43 (Decide maximum input sizes) for those limits. Other items moved out of scope link to existing issues.
- **Correction:** The first version of the groomed issue also contained eight decisions I made without asking, which broke the "stop and ask" rule in `AGENTS.md`. They were: a summary needs both a start and an end date; the limit-reached error names the limit; filtering by an unknown tag matches nothing; whitespace-only text counts as missing; exporting an empty account works; login gives one error for a wrong email or a wrong password; tokens expire after a configured time; date filters include both end dates, either date may be left out when listing, and a start after the end is an error. I listed them for the product owner, who then approved all eight. I updated issue #2 again: it now says all decisions are confirmed, every criterion about behaviour starts with "The file states that…" so it can be checked by reading `openapi.yaml`, and the out-of-scope link to "#3–#20" is narrowed to the issues that implement endpoints.
- **How I verified it:** Checked that onrender.com is on the Public Suffix List (the reason a cross-site cookie session would fail in Safari on the planned Render setup). Checked that FastAPI 0.162.0 generates OpenAPI 3.1.0, and that `npx @redocly/cli lint` (2.72.1) runs and validates an OpenAPI 3.1 file. Read the updated issue back from GitHub and checked it against the definition of done in `docs/pm.md`: all four sections are filled, every criterion can be checked by reading the file or running the lint command, and every out-of-scope item links to an issue.
- **Left open:** Issue #9 still says the backend defaults the entry date to today, which conflicts with the decision in #2; #9 should be updated when it is groomed. Out of scope in #2 gives token lifetime and server-side token storage to #7, and browser token storage to #25, but neither issue mentions those yet. #43 is not listed in `tasks.md`.

## 2026-11-01: Groom issue #3 (Set up the backend project skeleton)

- **Task:** Groom issue #3 following `docs/pm.md`.
- **What I did:** Rewrote #3 with the task template. Decisions confirmed by the product owner: each later issue adds its own environment variables, so #3 only reads `DATABASE_URL` and the CORS origins; CORS belongs in #3; and eight smaller proposals (missing required variable stops startup and names it; secrets masked; `.env.example` at the repo root; new `.gitignore`; pinned Python version; pydantic-settings; 404 and 405 use the shared error format; no `tests/integration/` until #4). Out-of-scope items link to #4, #5, #7, #12–#15, #21 and #24. Left to the engineer, as stated in the issue: the CORS variable's name, the Python version, and which variables are required.
- **How I verified it:** Checked with pydantic-settings 2.16.2 that a missing variable raises an error naming it and that `SecretStr` masks its value; checked that pytest exits with code 5 on a folder with no tests; confirmed that FastAPI's documentation recommends pydantic-settings. Checked the issue against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #3.

## 2026-11-01: Groom issue #4 (Run the backend and PostgreSQL with Docker Compose)

- **Task:** Groom issue #4 following `docs/pm.md`.
- **What I did:** Rewrote #4 with the task template. Decisions confirmed by the product owner: a separate test database in the same PostgreSQL container; a `.dockerignore` so `.env` never goes into the image; and eight smaller proposals (PostgreSQL healthcheck before the backend starts; image pinned to a major version Neon offers; named volume; credentials from `.env`; published, configurable port; timeout on the health database check; non-root container; #4 adds the SQLAlchemy engine and driver). Two criteria follow from those decisions and `AGENTS.md`: integration tests use their own database URL variable and never fall back to `DATABASE_URL`, and the health timeout comes from an environment variable. Out-of-scope items link to #5, #23, #24 and #38.
- **How I verified it:** Checked the issue against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #4.

## 2026-11-01: Groom issue #5 (Create the database schema and migrations)

- **Task:** Groom issue #5 following `docs/pm.md`.
- **What I did:** Rewrote #5 with the task template. Decisions confirmed by the product owner: #7 adds the token table in its own migration; and eight smaller proposals (time-zone-aware timestamps; migrations run when the backend container starts; a downgrade-and-upgrade test; `alembic check`; summary filters stored as values; the database restricts categories; email and tag case handling go to #6 and #8; usage counting goes to #15). Noted that `AGENTS.md` already settles the original "choose a database access layer and migration tool" as SQLAlchemy 2.x and Alembic. Out-of-scope items link to #6, #7, #8, #15, #21 and #38.
- **How I verified it:** Checked that Alembic 1.20.1 has the `check`, `upgrade` and `downgrade` commands. Checked the issue against the definition of done in `docs/pm.md`.
- **Left open:** When grooming #15: deleting an account deletes its AI usage rows, which lowers the day's global count; raise this with the product owner.

## 2026-11-01: Standing rule for grooming decisions

- **Rule from the product owner:** while grooming, accept the PM's recommended option without asking, as long as it fits the product scope and keeps development simple, maintainable and scalable. Anything outside the product scope is still asked. Each decision taken this way is listed in the issue and in this log.

## 2026-11-01: Groom issue #6 (Implement user registration)

- **Task:** Groom issue #6 following `docs/pm.md`.
- **What I did:** Rewrote #6 with the task template. Product owner's direct decision: passwords must be at least 15 characters (up to 128, any characters, no composition rules). Decisions taken by the standing rule: the frontend logs in right after registering (#26), so registration returns no token; emails are trimmed and stored in lower case; `EmailStr` validation; argon2 hashing; passwords used exactly as typed; responses never contain the password or hash; a test checks the password is not logged; simultaneous registrations for one email give "email already registered", not a server error. `openapi.yaml` gets the register rules first, as #2 requires.
- **How I verified it:** Checked with pydantic 2.13.5 and email-validator 2.3.0 that `EmailStr` lowercases only the domain, strips surrounding spaces and makes no DNS lookups (so the full lowercasing must be done by the app). The NIST page was blocked from this session; the 15-character figure for password-only login comes from several agreeing secondary sources.
- **Left open (outside product scope, for the product owner):** NIST also recommends checking new passwords against a list of common or breached passwords. The spec doesn't ask for it, so I did not add it or file an issue.

## 2026-11-01: Groom issue #7 (Implement login, logout and request authentication)

- **Task:** Groom issue #7 following `docs/pm.md`.
- **What I did:** Rewrote #7 with the task template. Decisions taken by the standing rule: token table in its own migration, cascading from users; random 32-byte tokens stored only as SHA-256 hashes; 7-day lifetime from an environment variable; one token per login (several devices at once); expired tokens deleted at login; same error and similar timing for unknown email and wrong password (dummy hash check); emails compared in lower case; login applies only the 128-character maximum; logout deletes only the current token; `WWW-Authenticate: Bearer` on 401; a test that tokens and passwords are not logged. Removed the original "signing keys or session secrets" line, because hashed random tokens need none. Out-of-scope items link to #20, #21, #25, #26 and #35.
- **How I verified it:** Checked the issue against the definition of done in `docs/pm.md`.
- **Left open (outside product scope, for the product owner):** The spec has no limit on failed login attempts (brute-force protection). I did not add it or file an issue.

## 2026-11-01: Groom issue #8 (Implement tag listing and tag name resolution)

- **Task:** Groom issue #8 following `docs/pm.md`.
- **What I did:** Rewrote #8 with the task template. Decisions taken by the standing rule: tag names are trimmed and inner spaces collapsed; matching ignores case and keeps the first spelling; a new migration makes names unique per user using `lower(name)`; empty names are a validation error; duplicates in one request become one tag; a resolve function that runs inside the caller's transaction (so tags only exist once the entry is saved); a lookup-only function for #16; simultaneous creation gives one tag; the list includes unused tags, sorted alphabetically ignoring case. Out-of-scope items link to #9, #10, #11, #16, #27 and #43.
- **How I verified it:** Checked the issue against the definition of done in `docs/pm.md`.
- **Left open (outside product scope, for the product owner):** The spec has no way to rename or delete a tag, so a mistyped tag stays in autocomplete forever. I did not add it or file an issue.

## 2026-11-01: Groom issue #9 (Implement entry creation)

- **Task:** Groom issue #9 following `docs/pm.md`.
- **What I did:** Rewrote #9 with the task template. Fixed the conflict with #2: the API now requires a date, and the form (#27) pre-fills today. Decisions taken by the standing rule: text stored exactly as typed; empty or whitespace-only Result/Impact stored as null; any real calendar date accepted, including future dates; a user id in the body is ignored; tags resolved inside the entry's transaction; the response shows stored tag spelling. Out-of-scope items link to #10, #11, #16, #27, #28 and #43.
- **How I verified it:** Checked the issue against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #9.

## 2026-11-01: Groom issues #10 and #11 (entries: read, edit, delete; filtering)

- **Task:** Groom issues #10 and #11 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #10: update is a full replacement (tags become exactly the list sent); removed tags stay in the tag list; last write wins; deleting twice gives "not found"; ids in the wrong format give a validation error; editing or deleting entries never changes saved summaries. For #11: sorted by date, then creation time, newest first; an entry appears once even if several tags match; flat list, grouping in the frontend; repeated query parameters for categories and tags; tag matching uses #8's rules; one shared filter function for the list and #17; a new index on entries (user_id, date). Added one line to #2 saying entry update is a full replacement. Out-of-scope items link to #9, #17, #27, #29, #31 and #43.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** #2 must also state #11's sort order and repeated query parameters, and its "Conflict with #9" line is now out of date. I'll fix those in a final consistency pass.

## 2026-11-01: Groom issues #12 and #13 (AI adapter and mock; OpenAI-compatible provider)

- **Task:** Groom issues #12 and #13 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #12: the provider variable is required with no default; summarise receives only date, category, text, Result/Impact and tag names; sync or async follows #4; invalid provider output is a provider failure; the mock is deterministic, obviously fake and configurable in tests; a no-logging test; the model variable moves to #13. For #13: base URL, key, model and two timeouts (15 s for suggestions, 60 s for summaries) from environment variables; the official `openai` SDK with Chat Completions; retries off; OpenRouter's `provider.zdr = true` on every request; prompts carry the §8 language rules; JSON answers validated; error mapping for timeouts, network failures, 4xx/5xx and bad output; only the entry text in the suggestion prompt, as the spec says. Out-of-scope items link to #14, #15, #16, #17 and #38.
- **How I verified it:** Checked with openai 3.42.1 that `max_retries` defaults to 2 and that Chat Completions accepts `extra_body`, `timeout` and `response_format`. Confirmed in OpenRouter's docs that `provider.zdr = true` restricts routing to zero-data-retention endpoints and that the OpenAI SDK works with OpenRouter's base URL.
- **Left open:** Nothing for #12 or #13.

## 2026-11-01: Groom issues #14 and #15 (default model; daily AI usage limits)

- **Task:** Groom issues #14 and #15 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Product owner's direct decision for #15: a separate global counter table with no personal data, instead of summing per-user rows, because deleted accounts would otherwise lower the global count. Decisions taken by the standing rule. For #14: at least three candidates, all with zero-data-retention endpoints; a committed test set of made-up entries in English and one other language; a repeatable comparison script that never runs in CI; results and reasoning in `docs/decisions/default-model.md`, including the maximum daily cost at the global cap. For #15: days in UTC; every attempted AI call counts, including failures; rejected requests do not count; one limited entry point wraps the adapter; atomic check-and-increment; the user's limit is checked before the global cap; limits must be whole numbers ≥ 0; the demo account is not special. Out-of-scope items link to #16, #17, #20, #28, #32, #38 and #40.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** #15 departs from the "summed for the global cap" note in `product-spec.md` §10.5. The product owner may want to update the spec.

## 2026-11-01: Groom issues #16, #17 and #18 (suggestions endpoint; summary generation; saved summaries)

- **Task:** Groom issues #16, #17 and #18 following `docs/pm.md`.
- **What I did:** Rewrote all three with the task template. Decisions taken by the standing rule. For #16: calls go through #15's limited entry point; suggested tags are cleaned and matched to the user's own tags; duplicates removed; at most 5 tags; nothing saved; empty text is a validation error that doesn't count. For #17: entries selected with #11's shared filter; no match means no AI call, no count and nothing saved; the stored filter uses cleaned tag names; nothing saved when the AI fails. For #18: list sorted newest first, no pagination; update changes only the text and ignores other fields; empty text rejected; last write wins; deleting twice gives "not found". Added "maximum number of entries in one summary" to #43, because a filter covering years of entries could exceed the model's context window. Out-of-scope items link to #9, #13, #28, #32, #33 and #43.
- **How I verified it:** Checked all three issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #16–#18.

## 2026-11-01: Groom issues #19, #20 and #21 (export; account deletion; demo account)

- **Task:** Groom issues #19, #20 and #21 following `docs/pm.md`.
- **What I did:** Rewrote all three with the task template. Decisions taken by the standing rule. For #19: one data function, two renderers; JSON with a format version, export time and the API's entry and summary fields, but no email, hash, tokens or usage; Markdown with headings per entry and summary, text unescaped; the same sort order as the list; dated file names; an empty account gets empty lists and "None" sections. For #20: one transaction; the global counter is not touched; the email can register again. For #21 (the original issue asked for these decisions): visitors can do everything except delete the demo account; a seed script resets the demo data on every run, and #38 runs it on every deploy; a demo-login endpoint replaces shared credentials (only the demo email is configured, and the demo user gets a random password); sample data rules (at least 20 entries, 5 tags, one non-English entry, dates over 6 months, a pre-written summary so no AI call). #21 adds demo-login and a demo error on delete-account to `openapi.yaml` first. Out-of-scope items link to #34, #35 and #38.
- **How I verified it:** Checked all three issues against the definition of done in `docs/pm.md`.
- **Left open (outside product scope, for the product owner):** Account deletion asks for no password again, and nothing limits how often demo-login or login can be called. The spec covers neither, so I did not add them or file issues.

## 2026-11-01: Groom issues #22 and #23 (data isolation suite; frontend skeleton)

- **Task:** Groom issues #22 and #23 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #22: the suite reads `openapi.yaml`; a test fails if app routes and contract operations differ; every protected operation is checked without a token; the only public operations are health, register, login and demo-login; cross-user checks cover entries, summaries, tags, filters, suggestions, exports, logout, account deletion and AI limits; any leak found is fixed in the same task. For #23: TypeScript strict mode; pinned Node LTS; React Router with placeholder routes and a "Page not found" page; app shell with four navigation links usable at 360px; plain CSS or CSS modules with no UI library; a Docker image serving the production build with route fallback; the frontend added to Docker Compose; its address in the CORS origins. Out-of-scope items link to #24–#34, #36 and #38.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #22 or #23.

## 2026-11-01: Groom issues #24 and #25 (CI; central API client)

- **Task:** Groom issues #24 and #25 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #24: runs on every push; no secrets, mock AI; CI copies `.env.example` to `.env` so a missing variable fails CI; cancels older runs on the same branch; job timeouts; cached uv and npm; jobs for the contract lint, backend, frontend and a full-system Compose start; a failing test branch proves the run fails. For #25: types generated with openapi-typescript and checked in CI; openapi-fetch; one function per operation; base URL from a Vite build variable in the root `.env`; an ESLint rule forbidding `fetch` outside `src/api/`; token and demo flag in `localStorage`; redirect to `/login` on "not authenticated"; a typed error per `code` plus network and unknown errors; no client timeout (60-second summaries, cold starts); export downloads return contents and file name. Out-of-scope items link to #26–#34, #37 and #39.
- **How I verified it:** Checked on npm that openapi-typescript (7.13.0) and openapi-fetch (0.17.0) exist and support OpenAPI 3.1.
- **Left open:** Nothing for #24 or #25.

## 2026-11-01: Groom issues #26 and #27 (auth screens; entry form)

- **Task:** Groom issues #26 and #27 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #26: show/hide password instead of a repeat field; inline validation (15–128 characters); "email already registered" links to login; automatic login after registering; return to the page the visitor wanted; a "server is waking up" hint after 10 seconds (§12); network and generic error messages that keep the input; `autocomplete` attributes and screen-reader announcements; logged-in users skip `/login`; logout in the app shell. For #27: `/entries/new` and `/entries/:id/edit`; a native date input with a local-time-zone default; categories as tappable options with none preselected; tag chips with case-insensitive autocomplete; the form works if tags fail to load; Save disabled while saving (no double entries); "Entry saved." on return; "Discard changes?" on cancel; a three-step capture flow. Out-of-scope items link to #28, #29, #35, #36 and #43.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #26 or #27.

## 2026-11-01: Groom issues #28 and #29 (AI suggestions in the form; entries page)

- **Task:** Groom issues #28 and #29 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #28: the button is disabled for empty text; suggestions only fill empty fields and never override a chosen category (offered as one-tap "Suggested: …" instead); suggested tags merge without duplicates and are visibly marked; each can be removed, plus "Discard suggestions"; no automatic re-suggesting; separate notices for AI unavailable, the user's limit and the global limit (reset after midnight UTC). For #29: all entries, newest first; full text with line breaks; dates never shifted by time zone; long words wrap at 360px; a thumb-reachable "New entry" button; delete with confirmation, "Entry deleted." and "already deleted" handling; empty, loading (with the waking-up hint) and error-with-retry states. Out-of-scope items link to #13, #16, #30, #31, #35 and #36.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #28 or #29.

## 2026-11-01: Groom issues #30 and #31 (writing nudge; review page)

- **Task:** Groom issues #30 and #31 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #30 (the original issue asked for these): the check runs in the frontend on the entries already loaded, so no new endpoint; "last 7 days" means today and the 6 days before, in the user's time zone; future-dated entries don't count; the banner shows for new users too; no close button. For #31: optional native date inputs; category toggles and a searchable tag multi-select (none means all); results update automatically; a start-after-end error; filters kept in the URL; "Clear filters"; grouping in a fixed category order with counts and empty groups hidden; read-only entry cards; a collapsible filter panel on mobile. Out-of-scope items link to #29, #32 and #36.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`. Corrected #30 after posting: its first version had an out-of-scope line without an issue link.
- **Left open:** In the final consistency pass, also check #22: one out-of-scope line has no issue link.

## 2026-11-01: Groom issues #32 and #33 (summary generation in the UI; saved summaries pages)

- **Task:** Groom issues #32 and #33 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #32: the button uses the shown filter; it is disabled, with a hint, when a date is missing or nothing matches; double-tap protection, because each request uses one of the day's summaries; it opens the new summary on success; notices for no match, AI unavailable, the user's limit and the global limit. For #33: list items show creation date, period, categories or tags (or "All …") and a two-line preview; an empty state links to Review; the detail page has edit mode with a note that entries are not affected; empty text is blocked; cancel asks before discarding; delete with confirmation; a "doesn't exist" state; period dates never shifted. Out-of-scope items link to #13, #17, #18, #33, #35 and #36.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** #32 lists #33 as a dependency, but it only needs the `/summaries/:id` route, which exists as a placeholder from #23. I'll fix that in the final pass. Outside product scope, for the product owner: a "Copy summary" button for pasting into a review tool. I did not add it.

## 2026-11-01: Groom issues #34 and #35 (settings page; "Try the demo")

- **Task:** Groom issues #34 and #35 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #34: downloads fetched through the API client and saved under the server's file name; progress and error states; the delete confirmation explains the consequences, offers downloads first and requires typing `DELETE`; after deletion, `/login` shows "Your account has been deleted." For #35: the demo button calls demo-login and stores the token and flag; a "demo isn't available" message; a shared-account notice on every app page, including a warning not to enter personal information; "Create your own account" logs out of the demo; "Delete account" is replaced with an explanation. Out-of-scope items link to #19, #20, #21, #35, #36 and #38.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #34 or #35.

## 2026-11-01: Groom issues #36 and #37 (viewport checks; end-to-end test)

- **Task:** Groom issues #36 and #37 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #36: Playwright tests at 360×640 and 1280×800 with mocked API calls cover every screen; no sideways scrolling; 44×44 px controls at 360px (inline links exempt); text columns at most 960 px wide on desktop; a quick-capture test (New entry, type, category, Save); screenshots saved as CI artifacts; problems fixed in the same task. For #37: one Playwright flow (register, banner, entry with a new tag, review filter, mock summary, JSON export, logout) against Docker Compose with the mock AI; unique emails; no fixed sleeps; a CI job after the other jobs, uploading traces on failure. Out-of-scope items link to #21, #35, #36 and #37.
- **How I verified it:** Checked both issues against the definition of done in `docs/pm.md`.
- **Left open:** Nothing for #36 or #37.

## 2026-11-01: Groom issues #38 and #39 (deploy to Render and Neon; deploy only when tests pass)

- **Task:** Groom issues #38 and #39 following `docs/pm.md`.
- **What I did:** Rewrote both with the task template. Decisions taken by the standing rule. For #38: a `render.yaml` Blueprint with secrets marked `sync: false`; the backend as a Docker web service binding to `PORT`; migrations and then the demo reset on every backend start (which covers "every deploy" from #21 and also refreshes demo data when a free instance wakes up); Neon over TLS with one direct `DATABASE_URL`; the frontend as a static site with a rewrite to `index.html`; OpenRouter account-level zero-data retention and a spending limit on the key; live checks; setup documented in `ops/deployment.md`, including the cold start. For #39: Render's `autoDeployTrigger: checksPass` on both services, so no deploy secret is needed (changed from the original issue); no test job may be skipped on `main`; proof from the Render event log. Out-of-scope items link to #24, #37, #38, #39 and #40.
- **How I verified it:** Confirmed in Render's docs that `PORT` defaults to 10000, that Blueprints support `runtime: docker`, `runtime: static` and `sync: false`, and that `autoDeployTrigger: checksPass` deploys only when all checks pass, counts skipped and neutral checks as passing, and skips the deploy when no checks exist. The 15-minute free-instance spin-down comes from a Render article, not a docs page.
- **Left open:** Nothing for #38 or #39.

## 2026-11-01: Groom issues #40 and #43, then a consistency pass over all groomed issues

- **Task:** Groom issues #40 and #43 following `docs/pm.md`, then check all groomed issues (#2–#40, #43) against each other.
- **What I did:** Rewrote #40 and #43 with the task template. Decisions taken by the standing rule. For #40: README sections in a fixed order that link to the source documents (`.env.example`, `AGENTS.md`, `ops/deployment.md`, the decision note) instead of copying them; a fresh-clone check of "Quick start". For #43: concrete limits (entry text 2,000 characters, Result/Impact 500, tag names 40, 10 tags per entry, summary text 10,000, and at most 50,000 characters of entries per summary, configurable); field limits fixed in the contract and the summary limit from an environment variable; long suggested tags dropped; frontend counters and messages; done after #33. Added #43 to `tasks.md` under task 32 (#33), without renumbering. Consistency pass: #2 now states #11's sort order and repeated query parameters, #19's empty-export format, and which later issues edit the contract, and its out-of-date "Conflict with #9" line is gone. #22 and #40 lost out-of-scope lines that had no issue link. #32 no longer waits for #33, because the `/summaries/:id` route exists from #23.
- **How I verified it:** Went through the Out of scope list of every groomed issue: each item links to an issue. Each issue has the four template sections.
- **Left open (outside product scope, for the product owner):** screening passwords against common or breached passwords (#6); limiting failed logins and demo-logins (#7, #21); renaming or deleting tags (#8); asking for the password again before account deletion (#20); a "Copy summary" button (#33). Spec updates that are the product owner's call: the global AI counter in #15 replaces "summed for the global cap" in §10.5, and §13's open question is answered by #14 once it is done.

## 2026-11-01: Outside-scope item 1: password rule changed (#6, #21, #26, #37)

- **Task:** Product owner decision on password strength, replacing the idea of screening against common or breached passwords.
- **What I did:** The product owner chose: at least 10 characters (up to 128), with at least one uppercase letter, one digit and one special character. This replaces the earlier 15-character rule with no composition rules. Two interpretations, taken by the standing rule: "10 letters" means 10 characters, and a special character is anything that is not a letter or a digit (for example `!`, `#`, `-` or a space). Updated #6 (rule, contract, per-requirement error messages, boundary tests, and a note that the rule deliberately differs from NIST SP 800-63B-4), #26 (hint and per-requirement messages on the registration form), #37 (test password) and #21 (the demo's random password must meet the rule). No follow-up issue for password screening.
- **How I verified it:** Re-read the four issues for any remaining mention of the 15-character rule.
- **Left open:** Items 2–5 of the outside-scope list still need the product owner's decision.

## 2026-11-01: Outside-scope item 2: filed #46 (Limit login and demo-login attempts)

- **Task:** Product owner decision on limiting login and demo-login attempts.
- **What I did:** The product owner asked for a follow-up issue. Filed #46, groomed with the task template. Decisions taken by the standing rule: 10 failed logins per email in 15 minutes block that email for the rest of the window, even with the correct password; 20 demo-logins per IP per hour; all values configurable; unknown emails counted the same way; a successful login clears the count; a new "too many attempts" error with `Retry-After`; IP read from Render's `X-Forwarded-For`; counts in a new table with hashed emails and IPs and expired rows deleted; messages on the login page and demo button. Added #46 to `tasks.md` under task 34 (#35), without renumbering.
- **How I verified it:** Checked #46 against the definition of done in `docs/pm.md`.
- **Left open:** Items 3–5 of the outside-scope list.

## 2026-11-01: Outside-scope item 3: unused tags disappear (#8, #10)

- **Task:** Product owner decision on tag cleanup.
- **What I did:** The product owner chose "unused tags vanish". Decisions taken by the standing rule: hide unused tags instead of deleting them (no clash with concurrent saves; retyping the name brings the tag back); and add the rule to #8 directly instead of filing a separate issue, because #8 is not built yet, so nothing has to be redone. Updated #8 (the tag list returns only tags used by at least one entry, plus tests) and #10 (removed or deleted tags stay in the database and leave the tag list once unused).
- **How I verified it:** Re-read #5, #11, #16, #27 and #31 for conflicts. #5's "deleting an entry keeps the tags" is still true at database level, and the others take their tags from #8's list or lookup.
- **Left open:** Items 4–5 of the outside-scope list.

## 2026-11-01: Outside-scope item 4: password required for account deletion (#2, #20, #34, #46)

- **Task:** Product owner decision on asking for the password before account deletion.
- **What I did:** The product owner chose to require the current password, added to the existing issues because they are not built yet. Updated #2 (password field on delete-account, a "wrong current password" error, the tag list showing only used tags from item 3, and #46 among later contract changes), #20 (password check before deleting; the demo error comes first; tests for missing and wrong passwords), #34 (a password field in the confirmation step; the button needs both `DELETE` and a password; "That password is incorrect." keeps the user logged in) and #46 (wrong deletion passwords count toward the per-email attempt limit, so deletion can't be used to guess passwords around the login limit). Decisions beyond the product owner's choice were taken by the standing rule.
- **How I verified it:** Re-read #21, #22 and #35 for conflicts: none (the demo error comes before the password check, and #22 checks authentication only).
- **Left open:** Item 5 of the outside-scope list.

## 2026-11-01: Outside-scope item 5: Copy button on the summary page (#33)

- **Task:** Product owner decision on a "Copy summary" button.
- **What I did:** The product owner chose to add it to #33, which is not built yet. Decisions taken by the standing rule: copies the saved text as plain text with line breaks; shows "Copied" for about 2 seconds; a fallback message if the browser refuses; hidden while editing so unsaved changes are never copied; uses the browser's Clipboard API with no new dependency; tests use a mocked clipboard.
- **How I verified it:** Re-read #33 against the definition of done in `docs/pm.md`.
- **Left open:** All five outside-scope items are decided. Still the product owner's call: whether to update `product-spec.md` §10.5 (the global AI counter from #15) and §13 (the default model, once #14 is done).

## 2026-11-01: Update product-spec.md to v0.2 with the groomed decisions

- **Task:** Update `product-spec.md` to match the groomed issues. The product owner explicitly asked for this edit, as `AGENTS.md` requires.
- **What I did:** Raised the version to 0.2 and kept every section number, so the "§" references in the issues stay valid. Added to the existing sections:
  - accounts: password rule, case-insensitive emails, login after registering, 7-day logins, and a new **FR-A4** for failed-login limits
  - entries: required date with a local-date default, size limits, tag rules, hidden unused tags
  - suggestions: fill only empty fields, at most 5 tags
  - review: inclusive dates, "any" within a filter type and AND across types, sort order, required period, summary input limit, and a new **FR-R6** for copying a summary
  - nudge: exact "last 7 days"
  - data control: export contents, deletion with password
  - demo rules
  - AI guardrails: UTC days, which calls count, separate global counter, data sent for summaries
  - NFR: 360px, token security
  - architecture: bearer tokens, test database, deploy after CI checks, Blueprint
  - data model: new `Token`, `AiUsageGlobal` and `LoginAttempt`; removed "summed for the global cap"
  - known limitations: shared demo data, possible 15-minute login lockout
  - open question §13: points to #14
  - a non-goal for manual tag management
  - a new §14 change log
- **How I verified it:** Compared each change with the issue it came from (#2, #6–#11, #13, #15, #16, #19–#21, #30, #33, #38, #39, #43, #46). Searched the spec for the outdated phrases ("15 characters", "summed for the global cap", "defaults to today"): none remain.
- **Left open:** The issues still say "product-spec.md v0.1". Their section references remain correct, because no section was renumbered.

## 2026-11-01: Number the issue titles in build order and point all issues to spec v0.2

- **Task:** Update every issue's spec reference from v0.1 to v0.2, and start each issue title with its position in the build order.
- **What I did:** Renamed all 41 open issues to "N. Title" in build order (1–41). #43 is task 33 and #46 is task 36, so tasks after them moved up by one or two. Renamed #43 to "Enforce maximum input sizes", because its values are decided. In every issue body, changed `product-spec.md` v0.1 to v0.2 and the last line to "Task N of 41 in the build order". Small alignment edits while doing so:
  - #5 lists the later tables from spec §10.5.
  - #7, #21, #25, #26, #28, #32, #33 and #35 link to #43 or #46 where those issues change them.
  - #15 notes that spec v0.2 reflects the global counter.
  - #25 adds the "wrong current password" error.
  - #33 and #46 name tests after the new FR-R6 and FR-A4.
  - #36, #38 and #40 list #43 and #46 as dependencies, and #38 adds their environment variables.
  - Renumbered `tasks.md` to the same 1–41 sequence and updated its intro.
- **How I verified it:** Listed all open issues and checked that the titles run 1–41 without gaps or duplicates and match `tasks.md`.
- **Left open:** Earlier log entries refer to the old task numbers (out of 39); the issue titles and `tasks.md` are now the reference.

## 2026-11-01: Task 1 (#2): write the OpenAPI contract

- **Task:** Implement issue #2 as the engineer, following `docs/software-engineer.md`: create `openapi.yaml`.
- **What I did:** Wrote `openapi.yaml` (OpenAPI 3.1.0) with the 19 operations from the issue's endpoint table and no others. It has bearer-token security (public: health, register, login), one shared `Error` schema with an enum of error codes, a `fields` list for validation errors and a `limit` field for reached AI limits, and every decision and edge case from the issue written in `info.description` and on the relevant schemas. Engineer's choices within the issue: plain resource paths, UUID ids, PUT for entry replacement, PATCH for summary text, separate `/export/json` and `/export/markdown`, and status codes: 422 validation, 401 not authenticated and wrong credentials, 403 wrong current password, 404, 409, 422 no matching entries, 429 and 503. Also merged `main` into the branch, because PR #47 had been merged and `main` had new commits (`docs/software-engineer.md`, `AGENTS.md`, `docs/process.md`). Force-pushing a rebase was blocked, so I merged instead.
- **How I verified it:** `npx @redocly/cli@2.72.1 lint openapi.yaml` reports 0 errors and 3 warnings: no license (the repository has none), a localhost server URL (the real development URL), and no 4xx on health (it takes no input). `openapi-spec-validator` confirms valid OpenAPI 3.1. A scripted check of the acceptance criteria (operations, operationIds, summaries, requirement IDs, security, error codes per operation, schemas, export headers, and the statements in `info.description`) passes. A deliberately broken copy made it fail, which shows the check works. The script is in my scratchpad, not the repository, because the issue allows changes only to `openapi.yaml` and this log.
- **Left open:** There is no project test suite yet (backend and frontend start in tasks 2 and 22), and CI linting of the contract comes with task 23 (#24). Issue #2 stays open for the product owner to review and close.

## 2026-11-01: Task 2 (#3): set up the backend project skeleton

- **Task:** Implement issue #3 as the engineer, following `docs/software-engineer.md`.
- **What I did:** Created `backend/` (uv project, Python 3.13 pinned in `requires-python` and `.python-version`):
  - `app/settings.py`: pydantic-settings with exactly two required variables, `DATABASE_URL` (a `SecretStr`) and `CORS_ALLOWED_ORIGINS` (comma-separated, each origin checked). A startup error names every missing or invalid variable and never shows values.
  - `app/errors.py`: the shared error format from `openapi.yaml` for validation errors (with `fields`), 404, 405 and unexpected 500s. Submitted values are never echoed.
  - `app/health.py`: `GET /health` with the documented body.
  - `app/main.py`: `create_app()` plus the module-level `app`, with CORS that allows the `Authorization` header and exposes `Content-Disposition` for export downloads (#25).
  - 23 unit tests. They validate response bodies against the schemas in `openapi.yaml`.
  - A root `.gitignore` and `.env.example`.
- **Dependencies and why:**
  - `fastapi`: the framework (`AGENTS.md`).
  - `uvicorn`: the dev server in the `AGENTS.md` command.
  - `pydantic-settings`: settings from environment variables (issue #3).
  - Dev group:
    - `pytest` and `ruff` (`AGENTS.md`).
    - `httpx2`: required by FastAPI's TestClient. Starlette 1.10 imports `httpx2` first and warns that plain `httpx` is deprecated. The PyPI project lists Tom Christie (the httpx author) and `github.com/pydantic/httpx2`.
    - `jsonschema` and `pyyaml`: load `openapi.yaml` and check that responses match its schemas. The tests also use `referencing`, which ships with `jsonschema`.
- **How I verified it:**
  - `uv sync`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest tests/unit` (23 passed, no warnings) all succeed in `backend/`.
  - Started `uv run uvicorn app.main:app --reload` with the two variables set: `/health` returned 200 with the documented body and `/nope` returned 404 in the shared format.
  - Started it with no variables and no `.env`: it exited with "DATABASE_URL is required but not set; CORS_ALLOWED_ORIGINS is required but not set".
  - `git status` after syncing and testing showed only the new source files; `.venv` and the caches are ignored.
- **Left open:**
  - Until #4 adds the real check, `/health` reports `"database": "ok"` without checking the database, because the documented body requires that field.
  - A CORS preflight from a disallowed origin gets Starlette's plain-text 400 instead of the shared error format. It carries no CORS headers, as required, and browsers don't show preflight bodies.
  - The integration-test command in `AGENTS.md` won't work until #4 adds the first integration test.

## 2026-11-01: Task 3 (#4): run the backend and PostgreSQL with Docker Compose

- **Task:** Implement issue #4 as the engineer, following `docs/software-engineer.md`.
- **What I did:**
  - `docker-compose.yml` with `db` and `backend` services:
    - PostgreSQL pinned to `postgres:18`, which Neon supports and uses by default for new projects.
    - A healthcheck, and the backend waits for it.
    - A named volume at `/var/lib/postgresql`, where the PostgreSQL 18 image keeps its data.
    - Credentials and ports from `.env`.
    - An inline init script that creates the test database on first start.
  - `backend/Dockerfile`: Python 3.13, uv 0.11.32 from PyPI, runtime dependencies only, non-root user `winlog`.
  - `backend/.dockerignore`: keeps `.env`, `.venv`, caches and tests out of the image. It lives in `backend/` because that is the build context.
  - `app/db.py`: a sync SQLAlchemy 2.x engine with psycopg 3. Plain `postgresql://` URLs are switched to the psycopg driver, and `pool_pre_ping` lets it recover after a database restart.
  - Health now checks the database and returns 503 `database_unreachable` when it can't connect. A new setting, `DATABASE_CONNECT_TIMEOUT_SECONDS` (default 3, range 2–60), bounds the wait.
  - `tests/integration/` reads only `TEST_DATABASE_URL` (environment or `.env`) and stops with a message naming it when missing.
  - New variables added to `.env.example`, and the integration-test command in `AGENTS.md` now says to start PostgreSQL first.
- **Why sync + psycopg:**
  - The app is small and low-traffic, and FastAPI runs sync endpoints in a thread pool, so async adds complexity without benefit.
  - psycopg 3 is the maintained PostgreSQL driver; its `binary` extra brings libpq, so the slim image needs no system packages.
- **Dependencies:**
  - `sqlalchemy`: required by `AGENTS.md`.
  - `psycopg[binary]`: the PostgreSQL driver.
- **How I verified it:**
  - `docker compose up --build -d` started `db` (healthy), then `backend`.
  - Through the published ports: `/health` returned 200 `{"status":"ok","database":"ok"}`.
  - With `db` stopped, health returned 503 `database_unreachable` immediately; after restarting `db` it returned 200 again.
  - Both `winlog` and `winlog_test` existed. The backend ran as uid 10001. The image contains no `.env` (checked with `find`).
  - A marker table survived `down`/`up` and was gone after `down -v`, and the fresh volume recreated both databases.
  - `uv run pytest tests/integration`: 1 passed. With `TEST_DATABASE_URL` empty it exited with code 4 and a message naming the variable.
  - `uv run pytest tests/unit`: 32 passed, with and without PostgreSQL running. The timeout test uses a local socket that never answers and gets 503 after about 2 seconds.
  - Ruff check and format are clean.
- **Sandbox note:** this session intercepts TLS, so containers here can't reach PyPI with their own certificates, and `ghcr.io` is blocked. To build here, I created a local copy of `python:3.13-slim` that trusts the session's proxy CA. It exists only in this container's Docker cache; the committed Dockerfile has no sandbox-specific settings.
- **Left open:** running migrations when the container starts comes in #5, the frontend service in #23, CI in #24 and production settings in #38.

## 2026-11-02: Task 4 (#5): create the database schema and migrations

- **Task:** Implement issue #5 as the engineer, following `docs/software-engineer.md`.
- **What I did:**
  - `app/models.py` has SQLAlchemy 2.x models for `users`, `entries`, `tags`, `entry_tags`, `summaries` and `ai_usage`, following `docs/product-spec.md` §10.5.
  - Ids are UUIDs generated by PostgreSQL (`gen_random_uuid()`), matching `openapi.yaml`, and every timestamp is `timestamptz`.
  - Categories are limited to the four values by a CHECK constraint (easier to change than an enum type, and "Side project" has a space).
  - Summary filters are stored as `text[]` values.
  - Every foreign key cascades on delete.
  - Constraint names follow a fixed naming convention, so later migrations can refer to them.
  - Alembic lives in `backend/migrations/` with `alembic.ini`. `env.py` reads `DATABASE_URL` through the app settings, and tests pass their own URL.
  - The initial migration was autogenerated with the `AGENTS.md` command and extended with a `set_updated_at()` trigger on `entries` and `summaries`, so `updated_at` changes on every update, not only ORM updates.
  - The backend container now runs `alembic upgrade head` and then `exec uvicorn`.
- **Beyond the issue, consistent with the spec:**
  - A CHECK that a summary's period doesn't end before it starts.
  - CHECKs that `ai_usage.request_type` is `suggestion` or `summary` and that `request_count` is not negative.
- **Fix to task 3:** `backend/.dockerignore` patterns only matched the top folder, so `app/__pycache__` reached the image. They now use `**/`; the image contains no caches or `.env` (checked with `find`).
- **Dependency:** `alembic`, a runtime dependency because the container runs the migrations (required by `AGENTS.md`).
- **How I verified it:**
  - `uv run alembic upgrade head`, `uv run alembic check` ("No new upgrade operations detected"), `uv run alembic downgrade base` and upgrade again all work against the dev database.
  - `docker compose down -v` then `docker compose up --build -d`: the backend log shows the migration running before uvicorn starts, all six tables exist, and `/health` returns 200.
  - `uv run pytest tests/integration`: 33 passed. They cover the migrations on an empty database, downgrade and upgrade, `alembic check`, uuid and timestamptz column types, every uniqueness, NOT NULL and CHECK rule, `updated_at`, and the cascades, including `test_fr_d2_deleting_a_user_removes_all_their_rows`.
  - `uv run pytest tests/unit`: 35 passed, also with PostgreSQL stopped. They include categories matching `openapi.yaml` and every foreign key cascading.
  - Ruff check and format are clean.
- **Left open:** the token table (#7), case-insensitive tag names (#8), the global AI counter (#15), and the entries index (#11) come in their own migrations.

## 2026-11-02: Task 5 (#6): implement user registration

- **Task:** Implement issue #6 as the engineer, following `docs/software-engineer.md`.
- **What I did:**
  - **Contract first** (separate commit): added a `Registration` schema to `openapi.yaml` for the register request, with `minLength: 10`, `maxLength: 128`, the character requirements and the email rule. Login keeps `Credentials`, because #7 checks no strength rule at login.
  - **Backend:** `POST /auth/register` in `app/accounts.py`.
    - The email goes through `EmailStr`, is trimmed, and is stored in lower case.
    - The password rule lives in `app/passwords.py` and names every missing requirement in one validation message. Length is counted in characters, and the password is used exactly as typed.
    - Passwords are hashed with argon2id (`argon2-cffi` defaults).
    - A duplicate email returns 409 `email_already_registered`, decided by the unique constraint, so simultaneous registrations are safe.
    - Responses contain only `id`, `email` and `created_at`.
  - Added a small `ApiError` for shared-format errors from endpoints, a per-request `get_session` dependency, and a helper that identifies which constraint rejected a change.
  - Moved the `contract` test fixture to `tests/conftest.py`, so integration tests can also validate responses against `openapi.yaml`.
- **Dependencies:**
  - `argon2-cffi`: an established argon2 library (`AGENTS.md`); bcrypt would ignore everything after 72 bytes.
  - `pydantic[email]`: email validation through email-validator, which makes no DNS lookups when used through pydantic.
- **How I verified it:**
  - `npx @redocly/cli@2.72.1 lint openapi.yaml`: valid, with the same 3 known warnings.
  - `uv run pytest tests/unit`: 52 passed. They cover each password requirement and its message, the 9- and 129-character boundaries, all missing requirements named together, non-ASCII uppercase letters, characters rather than bytes, invalid emails, missing fields, and rejected passwords never echoed.
  - `uv run pytest tests/integration`: 44 passed. They cover account creation validated against the `User` schema, no password or hash in responses, argon2id storage, spaces kept, the 10-character password accepted, trimming and lower-casing, duplicates in any case (409), five simultaneous registrations (one 201, four 409), and the password absent from logs at DEBUG level.
  - Live in the rebuilt container: 201 for a mixed-case email with spaces, 409 for the same email in upper case, 422 naming the missing requirements.
  - Ruff check and format are clean.
- **Left open:** login, logout and tokens come in #7, and the registration screen in #26.

## 2026-11-02: Draft the orchestration setup (subagents, /orchestrate skill, process rules)

- **Task:** Product owner request: one subagent per role, so the main session can orchestrate them as `docs/process.md` describes.
- **What I did:**
  - Merged `main`, which brings the new `docs/qa-engineer.md` and the updated `docs/process.md`.
  - Added `.claude/agents/pm.md`, `software-engineer.md` and `qa-engineer.md`. Each is a thin wrapper that points to its role file in `docs/` and defines a final report for the orchestrator.
    - None of them can launch agents.
    - The engineer and QA can't close issues, and none of them can merge pull requests.
    - QA may only read, run commands and comment.
  - Added the `/orchestrate` skill (`.claude/skills/orchestrate/SKILL.md`), with an optional issue number or `all`.
  - Appended to `docs/process.md`: how the orchestrator works, stop points (including after two QA FAILs), the product owner's standing rule for decisions, and branch and logging rules.
  - These are drafts for the product owner's review, committed because the stop hook requires a clean working tree.
- **How I verified it:**
  - Checked the [Claude Code subagents docs](https://code.claude.com/docs/en/sub-agents):
    - the file format and fields
    - subagents inherit MCP tools
    - background subagents keep Read, Grep, Glob, Bash, Edit, Write and MCP tools
    - subagents can't ask the user questions
    - a new `agents` folder loads only after a restart
  - Checked the [skills docs](https://code.claude.com/docs/en/skills): skills are the current format for slash commands.
  - Parsed every frontmatter block as YAML.
- **Left open:**
  - The setup works only in a new session.
  - QA's tool list includes `ToolSearch` because this environment loads GitHub tools on demand; that's an inference, not documented.
  - The product owner still has to decide about the commit identity, because the environment sets `GIT_AUTHOR_*` and `GIT_COMMITTER_*`.

## 2026-11-02: Add status labels for the issue lifecycle

- **Task:** Product owner request: make each issue's status explicit, so the orchestrator skips steps that are already done and QA checks the five implemented tasks before new work starts.
- **What I did:**
  - Added the status labels `groomed` and `implemented`, created on first use. `qa-failed` will be created the first time QA fails.
  - Labelled #2–#6 (tasks 1–5) `implemented`, and #7–#40, #43 and #46 `groomed`.
  - Added a "Status labels" section to `docs/process.md`: one status label per open issue; no label means it needs grooming; closed means QA passed; only the orchestrator changes labels and keeps any other labels.
  - The picking order now puts `implemented` and `qa-failed` issues first, then `docs/tasks.md` order, then unlisted issues, oldest first.
  - The `/orchestrate` skill now decides each step from the label and sets the next label from each role's report. The three agent files say not to change labels.
- **How I verified it:** listed all open issues with their labels: #2–#6 have `implemented`, the other 36 have `groomed`, and no issue has none or two.
- **Left open:** the labels are grey with no description, because the GitHub tools available here can't edit labels. The product owner can change their colours in the repository's label settings.

## 2026-11-03: Orchestrator: QA PASS and closed #2 (task 1, OpenAPI contract)

- QA PASS (https://github.com/KittyNiuNiu/winlog/issues/2#issuecomment-6615753550): all criteria met; Redocly 0 errors, spec validator OK, unit tests 52 passed. Closed #2 as completed.
- QA notes, none failing: a few cases share an HTTP status (each still has its own code); the Markdown export's header example names a `.json` file; schemas allow extra fields; the "no field size limits yet" sentence sits next to #6's password rule.

## 2026-11-03: Fix QA FAIL on #3 (no CORS headers for other origins)

- **Task:** QA failed #3 (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6615875013) on "A request from an origin that is not in the list gets no CORS headers". Starlette's `CORSMiddleware` left out only `Access-Control-Allow-Origin` for such origins. It still sent `Access-Control-Expose-Headers` on every response with an `Origin` header, and its fixed `Access-Control-Allow-Methods`, `-Allow-Headers` and `-Max-Age` on every preflight.
- **What I did:**
  - Added `backend/app/cors.py` with `AllowedOriginsCORSMiddleware`, a subclass of FastAPI's CORS middleware. For an origin that is not in `CORS_ALLOWED_ORIGINS`, it removes every `Access-Control-*` header from the response. Status, body and `Vary` stay as before, so a disallowed preflight is still 400 "Disallowed CORS origin".
  - `app/main.py` uses it with the same settings as before. Allowed origins are unchanged.
  - Strengthened `tests/unit/test_cors.py`: for other origins, the simple and preflight tests now check that no header starting with `access-control-` is present, on `/health` (200) and an unknown path (404), for an unrelated origin and six near misses (port, scheme, trailing slash, subdomain, `127.0.0.1`, `null`). The allowed-origin test also covers the 404 path.
  - No new dependencies.
- **How I verified it:**
  - The strengthened tests failed before the fix (28 failures) and pass after it.
  - `uv run pytest tests/unit`: 79 passed. `uv run pytest tests/integration`: 44 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - Live with `uv run uvicorn app.main:app`: QA's curl requests for all seven other origins, simple and preflight, on `/health` and `/nope`, return no `Access-Control-*` header. The allowed origin still gets `Access-Control-Allow-Origin` and `Access-Control-Expose-Headers: Content-Disposition`, and its preflight still allows `Authorization`.
- **Left open:** nothing for this criterion. Responses keep `Vary: Origin` (and, on preflights, `Vary` naming the `Access-Control-Request-*` request headers), because caches need it; it is a caching header, not a CORS header.

## 2026-11-03: Orchestrator: #3 failed QA twice, stopped for the product owner

- **First FAIL** (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6615875013): origins outside the allowed list still got some CORS headers. The engineer fixed it in 4b9fcd5 with stronger tests (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6615999045).
- **Second FAIL** (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6616147710): the earlier problem is fixed, but a 500 response to the allowed origin has no CORS headers, so a browser can't read the error. Starlette's server-error handler runs outside the CORS middleware. No test covers it. It has been there since 4f982da.
- Set #3 to `qa-failed` and stopped, as `docs/process.md` requires after a second FAIL. #4–#6 are still `implemented` and waiting for QA.

## 2026-11-04: Fix second QA FAIL on #3 (no CORS headers on the shared 500 response)

- **Task:** QA failed #3 a second time (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6616147710) on "A request from an allowed origin gets CORS headers". A request from the allowed origin that ended in the shared 500 `internal_error` response got no CORS headers. Starlette runs the handler registered for `Exception` in `ServerErrorMiddleware`, which wraps every middleware the app adds, so the CORS middleware never saw the 500. The product owner decided the engineer fixes it and QA runs again.
- **What I did:**
  - Added `UnexpectedErrorMiddleware` to `backend/app/errors.py`, a small ASGI middleware. `app/main.py` adds it before the CORS middleware, so it runs inside it. It answers an unexpected error with the same shared 500 body, so the response passes through the CORS middleware: the allowed origin gets the usual CORS headers, and other origins still get none (the fix from 4b9fcd5).
  - It then raises the error again, so uvicorn still logs it. `ServerErrorMiddleware` sees that a response has started and sends no second one. The `Exception` handler stays registered as a fallback for errors outside the new middleware.
  - The 500 body is unchanged (`{"code":"internal_error","message":"Something went wrong."}`) and shows no exception details.
  - Tests in `tests/unit/test_cors.py`, with a route defined only in the test that raises `RuntimeError`, for GET and POST: the allowed origin gets the same `Access-Control-*` and `Vary` headers as on `/health`, and the seven other origins get no header starting with `access-control-`. Both check the body against `Error` and that the exception text is absent.
  - Tests in `tests/unit/test_errors.py`: the error still reaches the server, and an error after a streamed response started sends no second response.
  - No new dependencies. No changes to settings, `.env.example` or `openapi.yaml`.
- **How I verified it:**
  - The two allowed-origin tests failed before the fix and pass after it. I also broke the middleware on purpose three ways: not adding it, not re-raising, and sending a second response. A test failed each time.
  - `uv run pytest tests/unit`: 97 passed. `uv run pytest tests/integration` (PostgreSQL via `docker compose up -d db`): 44 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - Live, QA's request: `uv run uvicorn app.main:app --port 8011` with `DATABASE_URL` at `127.0.0.1:1`, then `POST /auth/register` from `http://localhost:5173`. It returns 500 `internal_error` with `access-control-allow-origin: http://localhost:5173`, `access-control-expose-headers: Content-Disposition` and `vary: Origin`, the same as the 503 from `/health`. From `https://evil.example`, `http://localhost:5174` and `null` it returns the same 500 with no `access-control-*` header. uvicorn logs each error once, without the email or password.
  - Live with the database up and `--reload`: 200, 404, 405 and 422 responses and the preflight behave as before for the allowed origin and for `https://evil.example`.
- **Left open:** nothing for this criterion. An error raised inside the CORS middleware itself would still get the 500 body without CORS headers, from the fallback handler; the app code does not run there.

## 2026-11-04: Orchestrator: third round on #3, QA PASS, closed

- The product owner chose to let the engineer fix the second QA FAIL. The engineer added `UnexpectedErrorMiddleware` inside the CORS middleware, so the shared 500 response gets the same CORS headers as any other response: present for allowed origins, none for others. Tests now cover 500s with an `Origin` header (420125b; https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6640497704).
- QA PASS on all 19 criteria (https://github.com/KittyNiuNiu/winlog/issues/3#issuecomment-6640629693): 97 unit and 44 integration tests pass. Both earlier FAIL cases were re-checked live. QA also confirmed the new tests fail when the fix is reverted. Closed #3 as completed.

## 2026-11-04: Orchestrator: QA FAIL on #4, simpler `.env` check for QA

- **First FAIL** (https://github.com/KittyNiuNiu/winlog/issues/4#issuecomment-6641014416): 19 of 20 criteria pass. The health timeout criterion fails: with an idle connection in the pool and the database paused (TCP open, no answer), `GET /health` hung for 150 s. `DATABASE_CONNECT_TIMEOUT_SECONDS` is passed only as libpq `connect_timeout`, so the pre-ping and `SELECT 1` on a pooled connection have no time limit. The unit test covers only a new connection. Set #4 to `qa-failed`.
- **Process change (product owner):** QA's layer-by-layer `docker save` scan for `.env` kept failing to run, so the product owner asked for a simpler check. I tested `docker run --rm -u 0 --entrypoint find <image> / -xdev -name '.env*'`: no output on the real backend image, and it found both `.env` files planted in a test image. `-u 0` is needed because the image's non-root user cannot read `/root` and a few other folders. Added to `.claude/agents/qa-engineer.md`.

## 2026-11-04: Fix QA FAIL on #4 (health timeout on a pooled connection)

- **Task:** QA failed #4 (https://github.com/KittyNiuNiu/winlog/issues/4#issuecomment-6641014416) on "The database check gives up after a timeout set by an environment variable". After one successful `/health`, `docker compose pause db` made the next `/health` hang for 150 s. `DATABASE_CONNECT_TIMEOUT_SECONDS` was only libpq's `connect_timeout`, so the pool's pre-ping and `SELECT 1` on an idle pooled connection had no time limit. The product owner decided the engineer fixes it now.
- **What I did:**
  - Checked the libraries in the installed source and docstrings, because postgresql.org and docs.sqlalchemy.org are blocked here:
    - psycopg 3.3.6 enforces the timeout only while connecting, and has no public query timeout.
    - SQLAlchemy 2.1.6's pre-ping has no time limit.
    - The server enforces `statement_timeout` itself, so it can't fire while the server is frozen. `tcp_user_timeout` and keepalives rely on TCP acknowledgements, which a paused container still sends.
  - `database_is_reachable` in `backend/app/db.py` now runs the check in its own thread. The request waits for it at most `DATABASE_CONNECT_TIMEOUT_SECONDS` and then returns 503 `database_unreachable`.
  - A check that gave up finishes in the background. Its connection goes back to the pool when the database answers, or SQLAlchemy discards it if it broke. Either way the pool is not left broken.
  - Only `/health` has the limit; other database access is unchanged. I updated the comment in `settings.py`. `.env.example` already described the new behaviour, so it is unchanged. No new dependencies.
  - Tests:
    - **Integration:** a pausable TCP proxy in front of the real test database. Paused, it keeps connections open and forwards nothing. Pooled and new connections must give 503 within the timeout, and `/health` must return 200 again after the proxy resumes or drops its connections.
    - **Unit:** a connection that never answers, without PostgreSQL.
- **How I verified it:**
  - All three new tests fail with `backend/app` stashed: 200 after 15 s, or 15 s elapsed.
  - `uv run pytest tests/unit`: 98 passed, without PostgreSQL. `uv run pytest tests/integration`: 46 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - Live with `docker compose up --build` and QA's steps:
    - Timeout 3: 200, then pause, then 503 in 3.0 s (three times), then unpause, then 200.
    - Timeout 7: 503 in 7.0 s while paused. After unpause, `/health` returned 200 and registration returned 201.
    - Pause, then `docker compose restart db`: 503, then 200.
  - Afterwards I ran `docker compose down -v` and removed the built image.
  - This environment's workarounds are not committed: a local `python:3.13-slim` that trusts the proxy CA, and `postgres:18` from `mirror.gcr.io` because Docker Hub returned 429.
- **Left open:** while the database stays silent, a check that gave up keeps one background thread waiting on its connection until the database answers or the OS drops the connection. That is at most one thread per connection that went silent. Other endpoints still wait on a silent pooled connection as before; that is outside this criterion.

## 2026-11-04: Orchestrator: second round on #4, QA PASS, closed

- The product owner chose to let the engineer fix the first QA FAIL. The engineer now runs the health database check in its own thread with a deadline of `DATABASE_CONNECT_TIMEOUT_SECONDS`, so a pooled connection that stops answering gives 503 `database_unreachable` instead of hanging. New unit and integration tests cover a silent pooled connection (3795429; https://github.com/KittyNiuNiu/winlog/issues/4#issuecomment-6641408338).
- QA PASS on all 20 criteria (https://github.com/KittyNiuNiu/winlog/issues/4#issuecomment-6641742646): 98 unit and 46 integration tests pass. The round 1 reproduction now gives 503 in 3.0 s, and the backend recovers after unpause and after a restart. QA confirmed the new tests fail without the fix and used the new one-command `.env` image check. Closed #4 as completed.
- Noted, not failures: while the database stays paused, each `/health` call starts a thread; under heavy load QA saw a bounded peak of 316 threads, back to 2 after unpause. Other endpoints can still wait on a silent database, as before; that is outside #4. QA also asked about the `httpx2` dev dependency from #3: it is Pydantic's maintained fork of `httpx`, and Starlette 1.10's test client requires it. Neon's support for PostgreSQL 18 (generally available since May 2026) was checked in Neon's docs, because neon.com is blocked for QA here.

## 2026-11-08: Orchestrator: QA PASS on #5, closed

- QA PASS on all 21 criteria (https://github.com/KittyNiuNiu/winlog/issues/5#issuecomment-6723380485): 98 unit and 46 integration tests pass, and ruff check and format are clean. QA checked migrations, constraints, triggers and cascades by hand in `psql` and ran `docker compose up --build` on an empty volume. Closed #5 as completed.
- Noted, not failures: the database accepts an empty string as entry text, so the API must reject blank text (#9). `entry_tags` accepts a link from one user's entry to another user's tag, so the entry and tag endpoints must prevent that (#8, #9). If a row is inserted and updated in the same transaction, `updated_at` stays equal to `created_at`.

## 2026-11-08: Fix QA FAIL on #6 (password character classes, unpaired surrogates)

- **Task:** QA failed #6 (https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723433338) on the password rule. `Abcdefgh1²`, `Abcdefgh1１` and `Abcdefgh1٣` were rejected for a missing special character, because the special-character check used `str.isdigit()` while the digit check uses `0`–`9`. `Ⓐbcdefgh12` was accepted, because `str.isupper()` is true for the symbol `Ⓐ`. QA also found that a lone surrogate in the password (`"Abcdefgh1\ud800"`) gave a 500 from argon2. The product owner decided (https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723454343) that the engineer fixes it now and that "uppercase letter" means Unicode category `Lu`.
- **What I did:**
  - Contract first, in its own commit (fbae8e4): the `Registration` password description in `openapi.yaml` now says the uppercase letter is category `Lu`, a letter is category `L`, a special character is anything that is neither a letter nor `0`–`9` (with `²` and `Ⓐ` as examples), and that an unpaired surrogate is rejected. No other part of the contract changed.
  - `backend/app/passwords.py` (857c4f1) classifies characters by `unicodedata.category`: uppercase letter `Lu`, letter any `L*` category (the same set as `str.isalpha()`), digit only `0`–`9`, special character anything else. So `²`, `１`, `٣`, `Ⓐ`, Roman numerals and combining marks are special characters, and a titlecase letter such as `ǅ` (`Lt`) is a letter but not the uppercase letter.
  - A password that cannot be encoded as UTF-8 (only an unpaired surrogate can't) gets the problem "contains an invalid character (an unpaired surrogate)". It goes through the existing pydantic validator, so the response is the shared 422 `validation_failed` naming `password`. The message never contains the password. The email already rejects surrogates with a 422 naming `email` (email-validator's "unsafe characters"); I added tests for it and changed no email code.
  - Tests: unit tests for each new case in `tests/unit/test_registration_validation.py`, and integration tests in `tests/integration/test_registration.py`. The integration tests check that the three non-ASCII-digit passwords get 201, that `Ⓐbcdefgh12` gets 422 "needs at least one uppercase letter", that a password or email with a lone surrogate gets 422 with no row stored and the password in neither the response nor the logs, and that an escaped surrogate pair is one valid character (201).
  - No new dependencies.
- **How I verified it:**
  - Before the fix: 11 of the new unit tests and 5 of the new integration tests failed. The surrogate test failed with argon2's `UnicodeEncodeError`.
  - After the fix: `uv run pytest tests/unit`: 119 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 53 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. `npx @redocly/cli@2.72.1 lint openapi.yaml`: valid, with the same 3 known warnings.
  - Live with `uv run uvicorn` against the compose database: the three non-ASCII-digit passwords and `Abcdefgh1😀` got 201 with `$argon2id$` hashes. `Ⓐbcdefgh12` got 422 "Password needs at least one uppercase letter." The QA surrogate request got 422 naming `password`, and a surrogate in the email got 422 naming `email`. The server log had no password and no traceback. Docker Hub returned 429 for `python:3.13-slim`, so I could not rebuild the backend image here.
- **Left open:** nothing for the criteria. Character categories come from the Unicode database of the running Python (3.13), so a character added in a later Unicode version could move class when Python is upgraded.

## 2026-11-08: Orchestrator: QA FAIL on #6, product owner decisions, second round, QA PASS, closed

- **First FAIL** (https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723433338): the password rule rejected `Abcdefgh1²`, `Abcdefgh1１` and `Abcdefgh1٣`. The special-character check used `isdigit()`, but the digit check only accepted `0`–`9`, so non-ASCII digits counted as neither. `Ⓐbcdefgh12` was accepted because `isupper()` is true for the symbol `Ⓐ`. Outside the criteria, a lone surrogate in the password caused a 500 from argon2. Set #6 to `qa-failed`.
- **Product owner decisions** (recorded in https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723454343): the engineer fixes the FAIL now, and "uppercase letter" means a Unicode uppercase letter (category `Lu`). A symbol such as `Ⓐ` counts only as a special character.
- The engineer sorted characters by Unicode category (uppercase `Lu`, letter `L*`, digit `0`–`9`, everything else special), rejected unpaired surrogates with a 422 naming `password`, and reworded only the register password description in `openapi.yaml` (fbae8e4, 857c4f1; https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723513515).
- QA PASS on all criteria in round 2 (https://github.com/KittyNiuNiu/winlog/issues/6#issuecomment-6723558041): 119 unit and 53 integration tests pass. The round 1 cases were re-checked live, and QA confirmed the new tests fail without the fix. Closed #6 as completed.
- Not checked in round 2: the image build and `.env` check, because Docker Hub returned 429. The live checks ran on `uv run uvicorn`. The fix changes no Dockerfile or `.dockerignore`, and round 1 found no `.env` in the image.

## 2026-11-08: Implement #7 (login, logout and request authentication)

- **Task:** #7, login and logout (FR-A2) with server-stored bearer tokens, and one reusable dependency that identifies the current user and rejects every request without a valid token (FR-A3, §7.1).
- **What I did:**
  - New migration `ec3f02a4af39` (the first one is unchanged) adds `tokens`: `id`, `user_id` (indexed, `ON DELETE CASCADE`), `token_hash` (unique), `created_at` and `expires_at`. `Token` model in `backend/app/models.py`.
  - New setting `TOKEN_LIFETIME_DAYS` (default 7, whole number from 1 to 365) in `backend/app/settings.py` and `.env.example`.
  - `backend/app/auth.py`: tokens are `secrets.token_urlsafe(32)` (32 random bytes), and only their SHA-256 hex digest is stored. `create_token` deletes the user's expired tokens and adds a new one, so other devices stay logged in. `get_current_user` (with `get_current_login` under it) reads `Authorization: Bearer <token>` through FastAPI's `HTTPBearer(auto_error=False, scheme_name="bearerAuth")`. A missing or malformed header, or an unknown, expired or logged-out token, all get 401 `not_authenticated` with `WWW-Authenticate: Bearer`. `ApiError` in `backend/app/errors.py` now takes response headers.
  - `backend/app/accounts.py`: `POST /auth/login` returns 200 `{token, expires_at}`. The email is trimmed and lower-cased as in registration. A wrong password and an unknown email both get 401 `invalid_credentials`. For an unknown email the password is still checked against a dummy argon2 hash with the same parameters, made once at import (`backend/app/passwords.py`). The password must be 1 to 128 characters and no other rule applies. Because of the length limit, pydantic rejects an unpaired surrogate, so such a password gets 422 rather than a 500 from argon2. `POST /auth/logout` returns 204 and deletes only the request's token.
  - Tests: `tests/unit/test_auth.py` and `tests/integration/test_login.py`, named after FR-A2 or FR-A3. They cover each criterion, including a test-only route that returns the user a token identifies. I extended the existing table, timestamp and settings tests for the new table and variable.
  - No new dependencies (`secrets` and `hashlib` are standard library).
- **How I verified it:**
  - `uv run pytest tests/unit`: 147 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 79 passed. `uv run ruff check .`, `uv run ruff format --check .` and `uv run alembic check` are clean.
  - Mutation checks: I broke the code six ways, one at a time: no dummy hash, raw token stored, logout deleting all of the user's tokens, no expiry check, no expired-token cleanup, no `WWW-Authenticate` header. Each made the matching tests fail. Logging the password or the token made the log test fail.
  - Live with `docker compose up --build`. Docker Hub answered this time, and I built on the local CA-trusting `python:3.13-slim` shim, which is not committed. Results:
    - Register gave 201. Login with `"  LIVE@example.com "` gave 200 with a 43-character token and `expires_at` 7 days ahead.
    - A wrong password and an unknown email gave the same 401 body, in about the same time (about 45 ms each).
    - A password with an unpaired surrogate, or 129 characters, gave 422.
    - Logout with no header or with `Basic` gave 401 and `WWW-Authenticate: Bearer`. Logout gave 204, the same token again gave 401, and the second device's token still worked.
    - `psql` showed the table, index, unique constraint and cascade. The backend log had no token, no password and no traceback. `find` found no `.env` in the image.
  - Afterwards I ran `docker compose down -v` and removed the built and pulled images.
- **Left open:**
  - The `Credentials.password` schema in `openapi.yaml` has no `minLength: 1` or `maxLength: 128`, but the issue requires the 128 limit, and I treat an empty password as missing. A later contract change could document both; this issue does not allow editing `openapi.yaml`.
  - `docker-compose.yml` does not pass `TOKEN_LIFETIME_DAYS` to the backend container, so Compose always uses the default of 7. The issue does not list that file.
  - Expired tokens are deleted only when their user logs in again, as the issue specifies.

## 2026-11-08: Orchestrator: #7 implemented, QA PASS, closed

- The product owner asked me to start with #7 and continue through #10. #7 was `groomed`, so it went straight to the engineer: tokens table migration, `TOKEN_LIFETIME_DAYS` (default 7), login, logout and the `get_current_user` dependency (e731acc, 2bc3eff, 639f509; https://github.com/KittyNiuNiu/winlog/issues/7#issuecomment-6725850784).
- QA PASS on all criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/7#issuecomment-6725971106): 147 unit and 79 integration tests pass. QA checked the full system with `docker compose up --build`, compared the timing of a wrong password with an unknown email, and confirmed that the test-only `/test/whoami` route does not exist in the running app. Closed #7 as completed.
- Noted, not failures: `docker-compose.yml` does not pass `TOKEN_LIFETIME_DAYS` to the backend, so Compose always uses 7 days. `openapi.yaml` `Credentials.password` does not state the 128-character maximum or the minimum of 1 that the code enforces; a later contract change could add them.

## 2026-11-08: Implement #8 (tag listing and tag name resolution)

- **Task:** #8, the tag name rules (FR-E3, §10.5), the shared resolve and lookup functions for #9, #10, #11 and #16, and `GET /tags` (`listTags`), which lists only the tags the user's entries use (§7.2).
- **What I did:**
  - New migration `685f000b996b` (earlier migrations unchanged) adds the unique index `uq_tags_user_id_lower_name` on `tags (user_id, lower(name))` and drops the old `(user_id, name)` constraint, which the index covers. The `Tag` model matches it.
  - `backend/app/tags.py`:
    - `normalise_tag_name` trims the name and turns every run of whitespace inside it into one space.
    - `TagName` is a pydantic type for request models. A blank name gets the shared 422 naming the field, for example `tags.1`.
    - `resolve_tags` returns the user's tags in the order given and creates the missing ones with `INSERT … ON CONFLICT (user_id, lower(name)) DO NOTHING`. Inserts go in a fixed key order, so simultaneous requests cannot deadlock. It never commits.
    - `lookup_tags` returns only existing tags.
    - Matching uses the database's `lower()`, so it follows the index exactly. Python's `str.lower()` differs, for example for a final Greek sigma.
    - `GET /tags` uses `get_current_user`. It needs both the entry and the tag to belong to the user, because the database allows cross-user `entry_tags` rows (found by QA in #5).
  - Tests in `tests/unit/test_tags.py` and `tests/integration/test_tags.py` cover each criterion:
    - Name rules, resolve, lookup, rollback, and other users' tags.
    - Simultaneous creation: a blocking commit case, a rollback case, a barrier stress test, and a deterministic deadlock-order case.
    - The list: hiding a tag after its last entry is edited or deleted and showing it again, an empty list, other users, and no token.
  - Entries cannot be created through the API yet (#9), so the tests add entries and links directly. No new dependencies.
- **How I verified it:**
  - `uv run pytest tests/unit`: 161 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 114 passed. `uv run ruff check .`, `uv run ruff format --check .` and `uv run alembic check` are clean. Downgrading and upgrading the migration again works.
  - Mutation checks: each change made the matching tests fail. The changes were: Python `lower()` for matching, no `ON CONFLICT`, insert in the given order (deadlock), no user filter in resolve and lookup, no owner checks in the list, and listing unused tags.
  - Live with `uv run uvicorn` against the compose database: an empty list after register and login, then `["Alpha","beta"]` with an unused `zeta` hidden. `ALPHA` was rejected by the new index, and a request without a token got 401.
  - Issue comment: https://github.com/KittyNiuNiu/winlog/issues/8#issuecomment-6726084470
- **Left open:**
  - A tag name with a NUL character would fail in PostgreSQL. Input limits are #43, and #9 and #10 validate entry input.
  - The list sorts by `lower(name)` under the database collation, so on a `C` collation accented names sort after `z`.
  - The migration assumes no user already has two tags that differ only in case. The API could not create tags before this issue.

## 2026-11-08: Orchestrator: #8 implemented, QA PASS, closed

- #8 was `groomed`, so it went straight to the engineer, who added a migration making tag names unique per user with `lower(name)`, the shared `resolve_tags` and `lookup_tags` functions, and `GET /tags` (ed87767, 16b81cd, c6dc38b; https://github.com/KittyNiuNiu/winlog/issues/8#issuecomment-6726084470).
- QA PASS on all criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/8#issuecomment-6726154812): 161 unit and 114 integration tests pass. QA also checked that 150 simultaneous resolves produced no errors and no duplicates, that a rollback left no tags, and that `entry_tags` links between users show in neither user's list. Closed #8 as completed.
- Left open by the engineer, outside the criteria: a tag name with a NUL character would cause a database error, so input limits (#43) and entry validation (#9, #10) must reject it. Sorting accented names depends on the database collation. The sort test can't tell `name` from `lower(name)` on a collation that already ignores case.

## 2026-11-08: Implement #9 (entry creation)

- **Task:** #9, `POST /entries` (`createEntry`): one request creates one entry with text, date, category, optional tags and an optional Result/Impact (FR-E1 to FR-E3, §7.2, §7.3). Saving needs no AI.
- **What I did:**
  - `backend/app/entries.py`: the endpoint returns 201 with the `Entry` schema. It uses `get_current_user`, and fields the contract does not define, such as `user_id`, are ignored.
    - Text is stored exactly as typed. Empty or whitespace-only text gets 422 naming `text`. Whitespace follows the contract's `pattern: '\S'` (ECMAScript `\s`).
    - A missing, empty or whitespace-only Result/Impact is stored as null.
    - The date must be `YYYY-MM-DD` and a real calendar date. Pydantic alone would also accept date-times and timestamps. Any real date is accepted, including future dates.
    - The category must be one of the four exact values.
  - Tags go through #8's `TagName` and `resolve_tags` in the entry's transaction. A failed save stores neither the entry nor new tags.
  - `backend/app/text_rules.py`: NUL and unpaired surrogates in `text`, `result_impact` or a tag name get 422 naming the field instead of a 500. `TagName` uses the same check.
  - `backend/app/db.py`: `hide_parameters=True`, so database errors never repeat the statement's values, such as entry text, in a logged traceback.
  - No new dependencies. No changes to `openapi.yaml`, `product-spec.md` or migrations.
- **How I verified it:**
  - `uv run pytest tests/unit`: 225 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 238 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - New tests in `tests/unit/test_entries.py` and `tests/integration/test_entries.py`, plus additions to `test_tags.py` and `test_db.py`, cover every criterion. They include a forced foreign-key failure after the tags were resolved (no entry or tag remains), A's and B's `Python` tags (FR-A3), and entry text never appearing in logs.
  - Mutation checks: removing the character checks, `hide_parameters` or the date format check, trimming the text, or committing before linking the tags each made tests fail.
  - Live with `uv run uvicorn` against the compose database: 201 with the stored tag spelling, a `user_id` in the body ignored, a combined 422 naming four fields, and 401 without a token. No entry text in the log.
  - Issue comment: https://github.com/KittyNiuNiu/winlog/issues/9#issuecomment-6726276857
- **Left open:**
  - PostgreSQL puts the failing row into the message of a CHECK or NOT NULL violation, and `hide_parameters` cannot hide it. Entry creation cannot trigger one now, but a database-level limit on entry text (#43) would log the text in a 500 traceback.
  - A body that is not valid UTF-8 gets 400 `internal_error` on every endpoint, from FastAPI's body parsing and the shared handler.
  - #43 adds the size limits, including 10 tags per entry.

## 2026-11-08: Orchestrator: #9 implemented, QA PASS, closed

- #9 was `groomed`, so it went straight to the engineer. The engineer added `POST /entries` and rejects NUL characters and unpaired surrogates in text, result_impact and tag names with a 422. The engine now uses `hide_parameters=True`, so entry text never appears in a logged database error (1d1bfc5, ef069e0, f555e2d, afa0750; https://github.com/KittyNiuNiu/winlog/issues/9#issuecomment-6726276857).
- QA PASS on all criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/9#issuecomment-6726344948): 225 unit and 238 integration tests pass. QA ran the live checks with `uv run uvicorn`, because Docker Hub returned 429 for the image build. It tested a failure forced by a temporary trigger: the save rolled back with no entry or tag left. Closed #9 as completed.
- For #43: a 9000-character tag gives a 500 from the index size limit, so tag length must be limited at the API. If size limits were enforced only in the database, PostgreSQL would put the row, including entry text, into the error message. So check them at the API boundary.
- Noted, not failures: a body that is not valid UTF-8 gets 400 with `code: internal_error` on every endpoint, from the shared error handling. Tag case matching follows PostgreSQL `lower()` (#8), so `Straße` and `STRASSE` are separate tags.

## 2026-11-08: Implement #10 (reading, editing and deleting entries)

- **Task:** #10, `GET`, `PUT` and `DELETE /entries/{entryId}` (`getEntry`, `updateEntry`, `deleteEntry`): users can view, edit and delete their own entries (FR-E4), and another user's entry behaves as if it did not exist (FR-A3).
- **What I did:**
  - `backend/app/entries.py`: three endpoints, all using `get_current_user` and scoped to the user. A missing entry and another user's entry get the same 404 `not_found`.
  - Get returns the `Entry` schema. Tag names are sorted ignoring case, like `GET /tags`, because no tag order is stored. Only the owner's tags are shown.
  - Update is a full replacement through #9's `EntryInput`, so validation is the same as create. It locks the row (`FOR UPDATE`), deletes the old tag links and resolves the new tags with #8's `resolve_tags`, all in one transaction. The response lists tags in the order sent, as create does. `flag_modified` makes sure the row is always written, so the #5 trigger changes `updated_at` even when nothing else changed.
  - Delete returns 204. The links go through `ON DELETE CASCADE`, and the tags stay.
  - `entryId` must be the hyphenated `format: uuid` form. The other spellings pydantic accepts get 422 naming `entryId`. Without a valid token, all three return 401 before the id or the body is checked.
  - No new dependencies. No changes to `openapi.yaml`, `product-spec.md` or the migrations.
- **How I verified it:**
  - `uv run pytest tests/unit`: 282 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 362 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - New tests in `tests/integration/test_entry_changes.py` and `tests/unit/test_entries.py` cover each criterion. They include summaries stored directly in the database, which stay unchanged after an edit and a delete, a forced database failure during an update that rolls back everything, and all three operations on another user's entry.
  - Mutation checks: removing either user filter, `flag_modified`, the link deletion or the id format check, committing early, resolving tags before the 404 check, or returning 200 from delete each made tests fail.
  - Live with `uv run uvicorn` against the compose database: 200, 200, 404 for another user, 422, 401, then 204 and 404. No entry text in the server log.
  - Issue comment: https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726486265
- **Left open:**
  - The test database's collation already ignores case, so the tests cannot tell sorting tag names by `lower(name)` from sorting by `name` (as in #8).
  - `updated_at` is the transaction start time, so of two overlapping updates the last to commit wins but can carry the earlier timestamp.
  - `/entries/` with an empty id gets FastAPI's 307 trailing-slash redirect.
  - Size limits are #43.

## 2026-11-08: Fix the QA FAIL on #10 (token checked before a body that is not valid JSON)

- **Task:** #10, the QA FAIL on "Without a valid token, all three operations return 'not authenticated' and change nothing" (https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726557493). `PUT /entries/{entryId}` and `POST /entries` with no token or a wrong token and a body that is not valid JSON got 422 `validation_failed` instead of 401 `not_authenticated`, because FastAPI parses the JSON body before it runs any dependency.
- **What I did:**
  - `backend/app/auth.py`: new `AuthenticateFirstRoute`, a FastAPI `APIRoute` subclass (FastAPI's documented way to customise route handling). When FastAPI cannot read the body (a `json_invalid` validation error, or its 400 "There was an error parsing the body" for bytes that are not UTF-8), a route that needs authentication first solves its dependencies that lead to `get_current_login`. Without a valid token that raises `not_authenticated` with `WWW-Authenticate: Bearer`. With a valid token, the original body error is raised again, so the 422 stays. Only the error path runs the check, so a valid request still checks its token once. The body fails before anything runs, so nothing changes in the database.
  - All four routers (`accounts`, `entries`, `health`, `tags`) use it, so it covers every authenticated operation that takes a body, now and later. Public operations (`/auth/register`, `/auth/login`) have no login dependency and keep their 422.
  - No new dependencies. No changes to `openapi.yaml`, `product-spec.md` or migrations. The tag order in the PUT response is unchanged, as QA asked.
- **How I verified it:**
  - `uv run pytest tests/unit`: 301 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 404 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - New tests: in `tests/unit/test_auth.py`, every authenticated operation with a request body, with no token or a malformed header and the bodies `junk`, `{"text":`, `\xff\xfe` and `\x80`, gets 401; a logged-in request with malformed JSON still gets 422; register and login still get 422; and every router uses `AuthenticateFirstRoute` and together they hold every operation of the app. In `tests/integration/test_entries.py` and `test_entry_changes.py`, POST and PUT with no token, a wrong token or an expired token and those four bodies get 401 and change no entry, link or tag; with a valid token, malformed JSON gets 422.
  - Without the fix in `app/`, all 36 new integration no-token cases fail (24 PUT, 12 POST), and the 12 new unit no-token cases fail. The 422 cases pass both before and after.
  - Live with `uv run uvicorn` against the compose database: the QA requests (PUT and POST, no header or `Bearer garbage`, the bodies `junk`, `{"text":` and `\xff\xfe`) each gave 401 `not_authenticated` with `WWW-Authenticate: Bearer`. With a valid token: 422. Register and login with malformed JSON: 422. The entry and its tags were unchanged. No traceback or entry text in the server log.
- **Left open:**
  - With a valid token, a body that is not valid UTF-8 still gets FastAPI's 400 with `code: internal_error`, as noted for #9. Without a token it now gets 401.
  - `AuthenticateFirstRoute` looks at the route's own dependencies. If authentication were ever added as a router-level `dependencies=[...]`, it would not be seen. The docstring says so, and every operation now uses its own dependency.

## 2026-11-08: Orchestrator: #10 implemented, QA FAIL, fixed, QA PASS, closed

- #10 was `groomed`, so it went straight to the engineer: get, full-replacement update and delete for entries, scoped to the user, with another user's entry giving the same 404 as a missing one (362d239, 57ec2a3; https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726486265).
- **First FAIL** (https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726557493), on 1 of 17 criteria: with no valid token and a body that is not valid JSON, `PUT /entries/{id}` (and `POST /entries` from #9) gave 422 instead of 401, because FastAPI parses the body before it runs the token dependency. Nothing changed in the database. Set #10 to `qa-failed`. No product decision was needed, so per the process it went back to the engineer with the QA comment.
- The engineer added `AuthenticateFirstRoute` in `backend/app/auth.py`, used by every router. When the body can't be read, a protected route checks the token first. With a valid token the 422 stays, and register and login keep their 422 (2b4cb78, 69f854c; https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726652998).
- QA PASS on all 17 criteria in round 2 (https://github.com/KittyNiuNiu/winlog/issues/10#issuecomment-6726737518): 301 unit and 404 integration tests pass. All 48 reproduction requests gave 401. Each request runs one token lookup, and no database sessions leaked. The new tests fail without the fix. Closed #10 as completed.
- Noted, not failures: GET lists an entry's tags alphabetically ignoring case, while PUT and POST return them in the order sent. With a valid token, a body that is not UTF-8 still gets FastAPI's 400 `internal_error`. `AuthenticateFirstRoute` sees only route-level dependencies, not router-level ones.
- This ends the run the product owner asked for (#7 to #10).

## 2026-11-08: Orchestrator: open points from #7–#10 moved to the issues they belong to

- The product owner noticed that the open points from #7–#10 were only in this log and in the closed issues' comments, where later roles might miss them. The product owner decided to post each point where it fits.
  - **#43:** a 9000-character tag gives a 500, and size limits must be checked at the API because PostgreSQL puts the failing row (including entry text) into constraint errors (https://github.com/KittyNiuNiu/winlog/issues/43#issuecomment-6726774877). Also: `Credentials.password` in `openapi.yaml` lacks `maxLength: 128` and `minLength: 1` (https://github.com/KittyNiuNiu/winlog/issues/43#issuecomment-6726805286).
  - **#38:** `docker-compose.yml` does not pass `TOKEN_LIFETIME_DAYS` to the backend (https://github.com/KittyNiuNiu/winlog/issues/38#issuecomment-6726805981).
  - **New issue #58** (https://github.com/KittyNiuNiu/winlog/issues/58): a body that is not valid UTF-8 gets 400 `internal_error`, and an entry's tag order differs between GET and POST/PUT (needs a product decision). It needs grooming and is not yet in `docs/tasks.md`.
- From now on, the orchestrator posts each open point on the issue it belongs to when it closes an issue, not only in this log.

## 2026-11-08: Orchestrator: record open points on their issues (skill step 6)

- **Task:** the product owner asked to add the rule from the previous entry to step 6 of the orchestrate skill, so that later sessions follow it.
- **What I did:** `.claude/skills/orchestrate/SKILL.md`, step 6 (PASS): after closing an issue, the orchestrator collects the engineer's "left open" points and QA's notes. It posts each one as a comment on the open issue it fits, with a link to the source and a note that it is an input for grooming, not a new requirement. If no issue fits, it asks the product owner whether to create one or leave the point in the log. The log entry names where each point went. Step 7 now also reports where the open points were recorded.
- **How I verified it:** read the edited steps 6 and 7 against `docs/process.md`. They add no new role or label, and the rule that only the orchestrator closes issues is unchanged.
- **Left open:** `docs/process.md` does not mention this step, and the skill only spells out its steps. Add a line there if the rule should hold beyond the skill.

## 2026-11-08: Orchestrator: record open points on their issues (process.md)

- **Task:** the product owner asked to add the open-points rule to `docs/process.md` as well, and to check the closed issues for open points that no open issue mentions.
- **What I did:** added a rule to "Rules" in `docs/process.md`: when the orchestrator closes an issue, it posts each open point from the engineer and QA on the open issue it belongs to, and asks the product owner if no issue fits. The skill (step 6) already spells out the steps.
- **How I verified it:** the wording matches step 6 of `.claude/skills/orchestrate/SKILL.md`, and no role or label changes.

## 2026-11-08: Orchestrator: check the closed issues for open points no open issue mentions

- **Task:** the product owner asked whether any open points from closed issues (#2–#10) were missing from the open issues.
- **What I did:** read the engineer and QA comments on #2–#10 and searched the open issues' bodies and comments for each point.
  - #7–#10 were already covered by today's comments on #43 and #38 and by #58.
  - Points from #2–#6 already handled: contract lint in CI (#24), an extra field in a summary update is ignored (#18), the "no size limits yet" line in the contract is rewritten (#43), blank entry text is rejected (#9), tag links between users (#8, #11), Neon's support for PostgreSQL 18 (checked), and health-check threads (bounded).
- **Product owner decisions:** post the three remaining points where they fit:
  - #19: the shared `ContentDisposition` example in `openapi.yaml` names a `.json` file, so the Markdown export shows the wrong extension (https://github.com/KittyNiuNiu/winlog/issues/19#issuecomment-6726856969).
  - #58: malformed-JSON errors name the field by character position, for example `"1"` (https://github.com/KittyNiuNiu/winlog/issues/58#issuecomment-6726857490).
  - #38: only `/health` has a database time limit, so other endpoints can wait on a silent database (https://github.com/KittyNiuNiu/winlog/issues/38#issuecomment-6726861531).
- **Reviewed and not tracked** (product owner decision; none affects users or a criterion):
  - a disallowed CORS preflight gets Starlette's plain-text 400 (#3)
  - an error inside the CORS middleware itself would get no CORS headers (#3)
  - some `.env.example` comments run over several lines (#3)
  - `updated_at` stays equal to `created_at` when a row is inserted and updated in the same transaction (#5)
  - the password rule's character classes follow the Unicode version of the running Python (#6)

## 2026-11-08: Implement #11 (entry filtering)

- **Task:** #11, `GET /entries` (`listEntries`) with the optional period, category and tag filters of FR-R1, in one shared filter function that summary generation (#17) reuses, plus an index on entries (user_id, date).
- **What I did:**
  - `backend/app/entries.py`: `EntryFilter` (start date, end date, categories, tags; each optional) and `filter_entries(session, user, entry_filter)`, which returns the user's matching entries as API `Entry` objects. Dates include their own day; several categories or tags match any of them; filter types combine with AND. Tags go through #8's `lookup_tags` (trimmed, inner spaces collapsed, PostgreSQL `lower()`), which only finds the user's own tags, and the entry is scoped to the user too, so a link from one user's entry to another user's tag never matches. The tag condition is an `EXISTS`, so an entry with several selected tags appears once. Sort: date, then `created_at`, both newest first (the id only breaks a full tie). Each entry's tags come from one correlated `array_agg` sorted by `lower(name)`, as in `GET /entries/{entryId}`, so there is no query per entry.
  - The list endpoint takes `start_date`, `end_date`, `category` and `tag` as query parameters (repeated for lists), validates them and calls `filter_entries`. A start date after the end date is the shared validation error naming `end_date` (as `period_end` in `openapi.yaml` "must not be before `period_start`"). Dates use #9's `EntryDate`, categories #9's `Category`.
  - `backend/app/tags.py`: `FilterTagName`, which rejects NUL and unpaired surrogates (422 naming `tag.N`) and otherwise accepts any name. Unknown names, and names that are empty after trimming, match nothing and are not an error.
  - `backend/app/models.py` and a new migration `e6c4db2b6d3c`: index `ix_entries_user_id_date`. No existing migration changed.
  - No new dependencies. No changes to `openapi.yaml` or `product-spec.md`.
- **How I verified it:**
  - `uv run pytest tests/unit`: 341 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 476 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - New tests in `tests/integration/test_entry_filter.py` and `tests/unit/test_entries.py`, named after FR-R1 and FR-A3: each filter alone, combinations, any-tag, no duplicates, case and spaces, matching exactly as the tag index does (final sigma, ß), commas in tag names, unknown, unused, empty and other users' tag names, the cross-user link set up directly in the database, inclusive and open-ended dates, sort order, 250 entries without pagination, each validation error, no, wrong or expired token (also with invalid parameters), the shared function returning exactly the listed entries, the endpoint calling it, and the index.
  - Mutation checks: exclusive start or end dates, dropping the owner check on tag names, sorting `created_at` ascending, removing the date-order check, a join instead of `EXISTS`, and dropping the user scope each make tests fail.
  - Live with `uv run uvicorn` against the compose database: the filters, 422s and 401 behaved as in the tests, and `EXPLAIN` shows the planner can use `ix_entries_user_id_date`.
- **Left open:**
  - An empty or whitespace-only `tag` value matches nothing (like an unknown name), so `?tag=` alone gives an empty list. The frontend (#31) should not send empty tag values.
  - The generated FastAPI schema describes the optional parameters as `anyOf [..., null]`; `openapi.yaml` stays the contract.
  - uvicorn's access log records the request line, so filter tag names appear in it. Entry text is never logged.
  - Size limits on query parameters (very long or very many tag names) are left to #43.

## 2026-11-08: Orchestrator: #11 implemented, QA PASS, closed

- The product owner asked for #11–#13, then to stop after #11. #11 was `groomed`, so it went straight to the engineer. The engineer added the shared `filter_entries` function, `GET /entries` and a migration with an index on `entries (user_id, date)` (35cbfbd, b1db268, f024d29; https://github.com/KittyNiuNiu/winlog/issues/11#issuecomment-6727326487).
- QA PASS on all 20 criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/11#issuecomment-6727404112): 341 unit and 476 integration tests pass. QA ran live checks with `docker compose up --build`, including entry–tag links between users set up in the database, and `EXPLAIN` using the new index. Closed #11 as completed.
- **Open points**, recorded where they belong:
  - #31: an empty `tag` value returns an empty list, so the filter controls must not send one (https://github.com/KittyNiuNiu/winlog/issues/31#issuecomment-6727411093).
  - #17: `filter_entries` leaves the period order check and the NUL check in tag names to its caller (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6727411916).
  - #43: no size limits on the filter's query parameters (https://github.com/KittyNiuNiu/winlog/issues/43#issuecomment-6727412379).
  - #38: the access log records filter tag names. This was the product owner's choice (https://github.com/KittyNiuNiu/winlog/issues/38#issuecomment-6727416124).
  - #58: date errors use two wordings, and the generated schema shows optional parameters as nullable. This was the product owner's choice.
- **Product owner decision on commit identity:** commits keep the environment's identity (`GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL` set to the product owner's account), not `noreply@anthropic.com`. The stop hook's "Unverified" warnings about this are expected and ignored. Pushed commits are never rewritten.

## 2026-11-09: Implement #12 (AI adapter interface and mock provider)

- **Task:** #12, the provider-agnostic AI adapter in `backend/app/ai/` with `suggest` and `summarise`, a required `AI_PROVIDER` variable with a factory, and a deterministic mock provider (`product-spec.md` §8 and §9).
- **What I did:**
  - `app/ai/adapter.py`: the sync interface (`AIProvider`, matching #4), `Suggestion`, `SummaryEntry` and the errors `AITimeoutError` and `AIProviderError` (both under `AIError`). Providers implement `_suggest` and `_summarise`; the public methods check the output for every provider: a category outside the four, tags that are not a list of valid tag names, or a summary that is blank, not text or not storable raises `AIProviderError`. Any other exception from a provider also becomes `AIProviderError` (chained). Tag names are normalised as `app.tags` does.
  - Data minimisation: `summarise` accepts only `SummaryEntry` objects (date, category, text, Result/Impact, tag names; frozen, with slots). `SummaryEntry.from_entry` copies those fields from an API `Entry` and leaves the id behind. An empty list raises `ValueError`, so no AI call is made without entries.
  - Logging: the adapter logs only the operation, provider, entry count, time taken and error type. Error messages never contain user content.
  - `app/ai/mock.py`: `MockProvider`. The category comes from a SHA-256 of the text (not `hash()`, which changes per run); the tag is "Mock tag" and the summary is "Mock summary of N entries from <first date> to <last date>." Tests can call `return_suggestion`, `return_summary`, `raise_timeout`, `raise_provider_error` and `reset`, and read `suggest_calls` and `summarise_calls`.
  - `app/ai/factory.py`: `create_ai_provider(settings)` and the `get_ai_provider` dependency (`AI` annotation) for #16 and #17. `create_app` creates the provider at startup and keeps it on `app.state.ai_provider`.
  - `app/settings.py`: `ai_provider: Literal["mock"]`, required with no default. A missing value gives "AI_PROVIDER is required but not set", an unknown one "AI_PROVIDER is invalid: Input should be 'mock'". The factory gives the same kind of message if it ever gets an unknown name, and a test checks its list matches the setting's.
  - `.env.example`: `AI_PROVIDER=mock` with its comment. `docker-compose.yml`: the backend gets `AI_PROVIDER` from `.env` and Compose stops with a message when it is missing; without this line, `docker compose up` would no longer start the backend (`AGENTS.md`: keep the commands working).
  - Existing tests: the explicit test settings pass `ai_provider="mock"`, the import defaults set `AI_PROVIDER`, `no_env_file` removes it, and the settings tests set it where they expect a valid configuration. No test was weakened.
  - No new dependencies. No changes to `openapi.yaml` or `product-spec.md`.
- **How I verified it:**
  - `uv run pytest tests/unit`: 397 passed. `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 476 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - New tests in `tests/unit/test_ai.py`: the factory (mock, unknown values, missing variable, at app startup), the contract's `Category` and `Suggestion` schemas, data minimisation, determinism with fixed values, configured output, both errors, invalid output, and a logging test that runs every path with captured logs and checks no input or output text appears in the logs or error messages.
  - Mutation checks: logging the entry text, or skipping the category check, makes tests fail.
  - `uv run uvicorn app.main:app` with `AI_PROVIDER=mock` served `/health`; with `openai` and with the variable unset it stopped with the messages above. `docker compose config` without `AI_PROVIDER` stops naming it. Building the backend image did not work in this session (pip in the image build could not reach PyPI through the sandbox proxy), so the container itself was not started.
- **Left open:**
  - The adapter does not limit the number of suggested tags; `openapi.yaml` allows at most 5 in a `Suggestion`, so #16 has to apply that limit (and map names to the user's spelling).
  - The usage-limit check before each call is #15; the real provider, its timeouts and prompts are #13.
  - The adapter logs each call's metadata at INFO (success) and WARNING (failure); #38 may want to review log levels.

## 2026-11-09: Orchestrator: #12 implemented, QA PASS, closed

- The product owner asked for #12–#15. #12 was `groomed`, so it went straight to the engineer. The engineer added the sync AI adapter, the deterministic mock provider, the factory and the required `AI_PROVIDER` setting (8b70ead, 2352bd6, 1653954; https://github.com/KittyNiuNiu/winlog/issues/12#issuecomment-6730523979).
- QA PASS on all 15 criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/12#issuecomment-6730594890): 397 unit and 476 integration tests pass, lint is clean. QA started the backend container with the mock and no AI key, using a base image that only adds the sandbox proxy's CA, because pip in the plain build could not verify the proxy's certificate. Closed #12 as completed.
- **Open points**, recorded where they belong:
  - #16: the adapter does not limit the number of suggested tags (the contract allows 5), and `AIProviderError` keeps the provider exception as its cause, which a traceback-logging handler could leak (https://github.com/KittyNiuNiu/winlog/issues/16#issuecomment-6730606009).
  - #13: a plain or SDK timeout becomes `AIProviderError`, so the real provider must raise `AITimeoutError` itself (https://github.com/KittyNiuNiu/winlog/issues/13#issuecomment-6730606567).
  - #17: the same error-cause logging point as #16 (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6730606978).
  - Left in this log by the product owner's choice: the adapter's log levels (INFO on success, WARNING on failure), and `test_fr_e2_entry_is_saved_without_an_ai_provider` now setting `AI_PROVIDER=mock` because the variable is required. That test still covers "an entry can be saved without using AI suggestions".
- Side effect of QA: one test account (`qa12-…@example.com`) with one entry is left in the local dev database, because account deletion (#20) is not built yet.

## 2026-11-09: Implement #13 (OpenAI-compatible AI provider)

- **Task:** #13, a real AI provider behind the #12 adapter that calls an OpenAI-compatible Chat Completions API (OpenRouter planned), with zero-data-retention routing, the §8 language rules and the error mapping from #12 (`product-spec.md` §8 and §10.2).
- **What I did:**
  - `app/ai/openai_compatible.py`: `OpenAICompatibleProvider` uses the official `openai` SDK (`OpenAI(base_url, api_key, max_retries=0)`) and `chat.completions.with_raw_response.create`, so it can log the response status. Every request sends `extra_body={"provider": {"zdr": true}}` and the operation's timeout (suggestions 15 s, summaries 60 s by default). `from_settings` builds it from the settings; tests pass an `httpx2.Client` with a mock transport.
  - Prompts: suggest sends a fixed system prompt and the entry text as the only user message, asks for exactly one of the four categories written exactly as in `openapi.yaml` (in English whatever the entry's language), up to 5 tag names in the entry's language, and a JSON object (`response_format={"type": "json_object"}`). Summarise sends a fixed system prompt and a JSON list of the entries with only date, category, text, result_impact and tags, and asks for a review-ready summary in the language most entries use, using only facts from the entries and shorter than 10,000 characters.
  - Output: the suggestion must be a JSON object with a `category` from the four and `tags` as a list of non-blank strings, otherwise `AIProviderError` (extra keys are ignored; a Markdown-fenced answer counts as invalid JSON). The adapter then normalises and checks again, as for every provider.
  - Errors: the SDK's `APITimeoutError` becomes `AITimeoutError` (the open point from #12's QA); `APIStatusError` (any 4xx/5xx, including 401 and 429) becomes `AIProviderError` naming only the status; `APIConnectionError` and unreadable answers (non-JSON body, no choices, no message text) become `AIProviderError`. The SDK exception is not chained (`from None`), because it can hold the provider's answer.
  - Logging: one INFO line per request with the model, the status (or "none") and the duration. Never the key, entry text, tag names or summary text.
  - `app/settings.py`: `AI_PROVIDER` accepts `openai-compatible`. New `AI_BASE_URL` (must start with http:// or https://), `AI_API_KEY` (`SecretStr`), `AI_MODEL`, `AI_SUGGESTION_TIMEOUT_SECONDS` (default 15) and `AI_SUMMARY_TIMEOUT_SECONDS` (default 60), both whole numbers from 1 to 600. With `openai-compatible`, a missing or blank base URL, key or model stops the app with "<NAME> is required when AI_PROVIDER is 'openai-compatible' but not set"; with `mock` they are ignored. `app/ai/factory.py` registers the provider. `.env.example` documents all five.
  - Existing tests: `no_env_file` also removes the new variables; the settings field list and the "allowed providers" test now include the new names (the old test said #13 would add them). No test was weakened.
  - New dependency: `openai>=3.42` (3.46.0 locked; it brings `jiter` and `sniffio` and uses the `httpx2` already in the lock). The issue requires the official SDK.
- **How I verified it:**
  - `uv run pytest tests/unit`: 501 passed (104 new in `tests/unit/test_ai_openai_compatible.py`). `uv run pytest tests/integration` (PostgreSQL 18 via `docker compose up -d db`): 476 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - The new tests stub HTTP with `httpx2.MockTransport` and check the URL, bearer key, model, `zdr`, the exact messages and fields sent, the per-operation timeouts, one request per call after 429/500/503/network errors and timeouts, valid suggestion and summary, invalid JSON, invalid categories, invalid tags, timeouts, network errors, 400–503 statuses and unreadable bodies, and a DEBUG-level log capture over all paths (no key or content in logs or error messages).
  - Mutation checks: turning retries on, dropping `extra_body`, not mapping the timeout, logging the prompt or using the wrong timeout each make a test fail.
  - `uv run uvicorn app.main:app` with `AI_PROVIDER=openai-compatible`: stops naming the missing variables; with all three set it starts and `/health` answers ok. No real AI API was called.
- **Left open:**
  - `docker-compose.yml` passes only `AI_PROVIDER` to the backend container, not the new variables, because the issue limits the files. Running the container with `openai-compatible` needs them added there (local only; production is #38).
  - The SDK's timeout applies to each phase (connect, read, write, pool), not to the whole request, so a provider that keeps sending bytes slowly could take longer than the timeout. #14 can check this with the chosen model.
  - #14: the chosen model must answer plain JSON (a Markdown-fenced answer is rejected) and support `response_format`.
  - No `max_tokens` is sent and `finish_reason` is not checked, so a cut-off summary is returned as is; the 10,000-character limit is #17's.

## 2026-11-09: Orchestrator: #13 implemented, QA PASS, closed

- #13 was `groomed`, so it went straight to the engineer. The engineer added the OpenAI-compatible provider using the official `openai` SDK (3.46.0, no retries, `zdr` on every request), five new settings and the required-variable checks (3d3384b, a7fe667, 0df17ca; https://github.com/KittyNiuNiu/winlog/issues/13#issuecomment-6734671723).
- QA PASS on all 15 criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/13#issuecomment-6734777069): 501 unit and 476 integration tests pass, lint is clean. QA also ran the SDK's real HTTP client against a local fake server on 127.0.0.1 (no real AI API), and confirmed the locked `openai` and `httpx2` packages are the official ones and that the SDK's HTTP layer is `httpx2`, so the tests' `httpx2.MockTransport` really stubs it. Closed #13 as completed.
- **Open points**, recorded where they belong:
  - #14: the chosen model must answer suggestions with plain JSON (a Markdown-fenced answer is rejected), and the SDK timeouts apply per connection phase, not to the whole request (https://github.com/KittyNiuNiu/winlog/issues/14#issuecomment-6734788531).
  - #17: no `max_tokens` or `finish_reason` check, so a cut-off summary is returned as it is; the 10,000-character summary limit from `product-spec.md` is not enforced by the provider (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6734789135).
  - New issue #61, created on the product owner's instruction: `docker-compose.yml` does not pass the real provider's variables to the backend, and `httpx2` is imported at runtime but declared only as a dev dependency. It needs grooming.

## 2026-11-09: Implement #14 (decide the default LLM model): partial, blocked before the paid run

- **Task:** #14, a documented, repeatable comparison of at least three OpenRouter models with zero-data-retention endpoints, a decision note at `docs/decisions/default-model.md` and the chosen model as the `AI_MODEL` default in `.env.example`.
- **What I did:**
  - `backend/scripts/model_comparison/test_set.json`: 24 made-up entries (12 English, 12 German, three per category in each language) with expected categories, plus four summary cases (all English, all German, mostly English, mostly German). German is my choice for the second language; the issue allows any.
  - `backend/scripts/model_comparison/comparison.py` (`python -m scripts.model_comparison`):
    - `check` (free) reads OpenRouter's public `/models` and `/endpoints/zdr` lists and shows each candidate's ZDR endpoints, `response_format` support, prices and the estimated cost of one run. ZDR endpoints with `safety_retention` are not counted, because they may keep flagged prompts (§8).
    - `run` needs `--confirm-paid-calls` and `AI_API_KEY` from the environment. It sends every test entry and summary case once through `OpenAICompatibleProvider` (same prompts, `zdr`, JSON parsing and timeouts as production) with the SDK's default HTTP client plus a response hook. The hook records the raw answer (for "valid JSON on the first try"; a fenced answer counts as invalid), the usage and OpenRouter's cost. It writes one JSON file per candidate plus `run.json` (date, excluded models, hashes of the test set and prompts).
    - `report` refuses until every review field (tag language, summary language, quality 1–5) is filled in, then prints the results table and the maximum daily cost at the global cap.
    - The OpenRouter response fields (`model_id` as the permanent slug, `canonical_slug`, `pricing`, `safety_retention`, `usage.cost`) were taken from OpenRouter's official Python SDK 1.3.143 on PyPI, read as data, because openrouter.ai itself was not reachable.
  - `docs/decisions/default-model.md`: a draft with the method, the proposed candidates (to confirm with `check`), the test set, the review rules and quality rubric, the cost assumptions and how to re-run. The results, the excluded models, the chosen model and the maximum daily cost are marked *pending*.
  - No new dependencies. No change to `.env.example`, `product-spec.md` or `openapi.yaml`.
- **How I verified it:**
  - `uv run pytest tests/unit`: 519 passed (18 new in `tests/unit/test_model_comparison.py`, all offline with `httpx2.MockTransport`). `uv run pytest tests/integration` (PostgreSQL via `docker compose up -d db`): 476 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - Mutation checks: counting safety-retention endpoints, accepting fenced JSON, dropping the `--confirm-paid-calls` check and using the lowest instead of the highest ZDR price each make tests fail.
  - `check` against the real host fails cleanly with "Could not read OpenRouter's list /models: ProxyError"; `run` without the flag refuses before any request. No real AI API was called.
- **Left open (blocked):**
  - No OpenRouter key in `.env` or the environment, openrouter.ai is blocked by the session's network policy, and spending is not approved. The comparison run, the results, the chosen model, the maximum daily cost and the `.env.example` default wait for these.
  - The candidate ids come from openrouter.ai pages found by web search on 2026-11-09 and must be confirmed with `check`.

## 2026-11-09: Implement #15 (enforce daily AI usage limits)

- **Task:** #15, daily caps on AI requests checked before every AI call: per user for suggestions and for summaries, plus one global cap, through one limited entry point (`product-spec.md` §8, §10.5, FR-D2).
- **What I did:**
  - Settings: `AI_DAILY_SUGGESTIONS_PER_USER` (10), `AI_DAILY_SUMMARIES_PER_USER` (2) and `AI_DAILY_REQUESTS_GLOBAL` (100), documented in `.env.example`. Each must be a whole number of 0 or more written with digits only; anything else (including `1.0`, `+5`, `1_000`, which pydantic would accept) stops the app with "<NAME> is invalid: … must be a whole number of 0 or more". There is no upper bound, because the criterion names none.
  - Migration `113dfac7accf` adds `ai_usage_global` (`day` primary key, `request_count`, no user id) and the `AiUsageGlobal` model. The per-user counts use the existing `ai_usage` table from #5.
  - `app/ai/limits.py`: `LimitedAI.suggest(user_id, text)` and `LimitedAI.summarise(user_id, entries)` are the entry point; features get it through `LimitedAIDependency`, which wraps the app's provider (`get_ai_provider`, so test overrides still apply). Order: the adapter's input checks (moved into `check_suggest_input` / `check_summarise_input` in `adapter.py`, so nothing counts for an empty entry list or a non-string text), then one transaction that raises the user's count and then the global count, each with `INSERT … ON CONFLICT DO UPDATE … WHERE request_count < limit RETURNING`, then commit, then the AI call. A reached limit raises `AILimitReachedError` (a 429 `ApiError` with `code: limit_reached` and `limit` set to `user_suggestions`, `user_summaries` or `global`), and the rollback leaves the user's count unchanged when only the global cap is reached. A limit of 0 refuses without touching the database. The day is the UTC date of a clock the tests can set.
  - Messages follow the UI texts groomed in #28 and #32 (for example "You've used today's suggestions. They're available again after midnight UTC.").
  - Existing tests: the table lists in `tests/unit/test_models.py` and the integration `APP_TABLES` include the new table, the settings field list includes the three limits, `no_env_file` removes them, and `migrated_db` also truncates `ai_usage_global` (it has no user id, so `TRUNCATE users CASCADE` does not empty it). No test was weakened.
  - No new dependencies.
- **How I verified it:**
  - `uv run pytest tests/unit`: 588 passed (69 new in `tests/unit/test_ai_limits.py`). `uv run pytest tests/integration` (PostgreSQL via `docker compose up -d db`): 513 passed (37 new in `tests/integration/test_ai_limits.py`). `uv run ruff check .` and `uv run ruff format --check .` are clean. All AI calls use the mock provider.
  - The integration tests cover each limit reached, 23:59:59 and 00:00:00 UTC, failed, timed-out and invalid-output calls counting, rejected requests not counting (no entries, wrong input, reached limit, no or wrong token, validation error), limits of 0, the user's count staying the same when the global cap is reached, the error body against the contract, deleting a user (directly in the database, because #20 is not built) without lowering the global count, FR-A3 and the shared demo account. Two race tests start 10 and 20 requests together with one slot left (per user and global), five times each, and check exactly one goes through.
  - Mutation checks: a read-then-write check instead of the conditional upsert makes the race test fail; counting after the AI call makes the failure and race tests fail; a module outside `app/ai/` that imports the raw provider or reads `app.state.ai_provider` makes the guard test fail.
- **Left open:**
  - #16 and #17 must call `LimitedAI` (via `LimitedAIDependency`) and map `AITimeoutError`/`AIProviderError` to `ai_unavailable`; `AILimitReachedError` already becomes the 429 response by itself.
  - #20 must delete the user's `ai_usage` rows (the foreign key already cascades) and must leave `ai_usage_global` alone.
  - The #14 comparison script (`backend/scripts/model_comparison/`) calls the provider directly and is not counted. It is a developer tool outside `app/`, run by hand with its own confirmation flag, so I left it unchanged.
  - Old `ai_usage` and `ai_usage_global` rows are never cleaned up; one row per user, day and type is small, but a cleanup could be groomed later.

## 2026-11-09: Orchestrator: #14 blocked on a paid OpenRouter run

- #14 was `groomed`, so it went to the engineer, who was told not to make paid calls or invent results without the product owner's approval. The engineer built the fixed test set (24 made-up entries, 12 English and 12 German, plus 4 summary cases), the comparison script (`check`, `run --confirm-paid-calls`, `report`), offline tests and a draft decision note (6de1ce5, 10b2a6a, d033496; https://github.com/KittyNiuNiu/winlog/issues/14#issuecomment-6735075467). No results, chosen model or `AI_MODEL` default yet.
- Status BLOCKED: no OpenRouter key, and openrouter.ai was blocked by the network policy. The product owner approved the paid run (the engineer's estimate was roughly $0.30–0.45 for 5 candidates, from unverified web-search prices). The orchestrator created a personal cloud environment "winlog" that allows openrouter.ai and moved this session onto it. The secure key form was declined or could not be shown, so the product owner will add the key in the environment settings. #14 stays `groomed` until then.
- Open for the product owner when #14 resumes: the engineer counts only zero-data-retention endpoints without OpenRouter's `safety_retention` flag, a strict reading of §8 to confirm.
- Product owner decision: work on #15 while #14 waits for the key.

## 2026-11-09: Orchestrator: #15 implemented, QA PASS, closed

- #15 was `groomed`, so it went straight to the engineer. The engineer added the three limit settings, the `ai_usage_global` migration and the limited entry point `LimitedAI`, with atomic conditional upserts committed before the AI call (145110f, b5e030f, b3e68e2; https://github.com/KittyNiuNiu/winlog/issues/15#issuecomment-6736343369).
- QA PASS on all 15 criteria in the first round (https://github.com/KittyNiuNiu/winlog/issues/15#issuecomment-6736455308): 588 unit and 513 integration tests pass, lint is clean. The migration upgrades, downgrades and shows no drift. QA's own race probe used 20 OS processes against real PostgreSQL, and exactly the allowed number went through each time. Closed #15 as completed.
- **Open points**, recorded where they belong:
  - #16 and #17: call `LimitedAI` through `LimitedAIDependency` and map `AITimeoutError`/`AIProviderError` to `ai_unavailable` (https://github.com/KittyNiuNiu/winlog/issues/16#issuecomment-6736463839, https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6736464744).
  - #20: per-user `ai_usage` rows cascade with the account; `ai_usage_global` must not be touched (https://github.com/KittyNiuNiu/winlog/issues/20#issuecomment-6736465655).
  - #14: the comparison script's calls are not counted against the limits (https://github.com/KittyNiuNiu/winlog/issues/14#issuecomment-6736466515).
  - #61: Compose does not forward the `AI_DAILY_*` variables (https://github.com/KittyNiuNiu/winlog/issues/61#issuecomment-6736467546), and the limit variables have no upper bound, so a value above bigint gives a 500 that fails safe. The product owner chose to add this one to #61 (https://github.com/KittyNiuNiu/winlog/issues/61#issuecomment-6736561615).
  - Left in this log by the product owner's choice: old rows in the usage tables are never cleaned up.
- Side effects of QA: the local tag `python:3.13-slim` now points to a QA-built image that adds the sandbox proxy CA, and the dev database is migrated to 113dfac7accf.

## 2026-11-09: Orchestrator: rule against unapproved real AI calls

- **Task:** the product owner asked how the OpenRouter key will be used in development and wanted to prevent high costs.
- **What I did:** added a working rule to `AGENTS.md`: no real AI calls without the product owner's explicit approval in that session. It covers tests, scripts, live checks and running the app with a real provider (anything other than `AI_PROVIDER=mock`). A task that needs one stops and asks first, with the reason and an estimated cost.
- **Why:** the key is saved as a network secret on the "winlog" cloud environment, and the proxy adds it to every request to openrouter.ai from every session on that environment. Tests and the app with the mock never call it, but a live check or a script could.
- **Also recommended to the product owner (not in the repository):** a separate development key with a small credit limit and no automatic top-up, and removing the network secret from the environment after the #14 run.
- **How I verified it:** a documentation change only; no code or tests changed.

## 2026-11-09: #14: free candidate check (no AI call)

- **Task:** #14, the free `check` step only. The product owner has not approved the paid run yet (`AGENTS.md`: no real AI call without approval).
- **What I did:** after the session moved to the "winlog" environment (openrouter.ai allowed, key added by the network proxy), I ran only the free `check` step, as the product owner approved; no AI call was made. All five ids exist. Usable: `openai/gpt-5.4-mini`, `anthropic/claude-haiku-5.5`, `mistralai/mistral-small-2603`. Excluded: `google/gemini-3.8-flash` (its only ZDR endpoints have safety retention) and `qwen/qwen3.8-flash` (no ZDR endpoint).
- **Result:** the decision note records the check, with dated prices; the estimated run cost for the three is $0.18.
- **How I verified it:** `uv run ruff check .` is clean and `uv run pytest tests/unit` passes (588). Only `GET /models` and `GET /endpoints/zdr` were requested.
- **Left open:** the paid `run`, the review, the results, the choice, the maximum daily cost and the `.env.example` default still need the product owner's approval to spend.

## 2026-11-09: Implement #14 (decide the default LLM model): comparison run and decision

- **Task:** finish #14: the paid comparison run, the review, the decision note and the `.env.example` default.
- **Product owner decisions (2026-11-09):**
  1. Strict zero-data-retention reading: endpoints with OpenRouter's `safety_retention` flag do not count. So `google/gemini-3.8-flash` is excluded (all its ZDR endpoints have safety retention), and `qwen/qwen3.8-flash` is excluded (no ZDR endpoint).
  2. Exactly one paid run, with `openai/gpt-5.4-mini`, `anthropic/claude-haiku-5.5`, `mistralai/mistral-small-2603` and `deepseek/deepseek-v4.1-flash` (the spare). No reruns.
- **What I did:**
  - Ran `check` again: the estimate was $0.24, below the $1 stop threshold. Then I ran the comparison once: `run ... --confirm-paid-calls`, with `AI_API_KEY=placeholder` on the command line only, while the network proxy added the real key.
  - `openai/gpt-5.4-mini` got HTTP 429 on 7 of 28 calls, including all 4 summaries. I recorded these as failures and did not retry them.
  - Actual cost: $0.0303, the same in the sum of `usage.cost` and in the key's usage after the run.
  - Reviewed every suggestion's tag language and every summary's language and quality (1–5) against the rubric in the note. I am the engineer agent, not the product owner: each result file says so in `review_by`, and each rating has a one-line reason.
  - `report` gives Haiku and DeepSeek the same summary quality (4.8). Haiku is cheaper and faster. Mistral wrote one summary in the wrong language and invented facts in two others. GPT-5.4 mini was rate limited and is the most expensive. Chosen: `anthropic/claude-haiku-5.5`, with a maximum daily cost of about $0.41 at the global cap of 100 requests. No product trade-off: the best model is also the cheapest acceptable one.
  - Completed `docs/decisions/default-model.md`, committed the result files under `backend/scripts/model_comparison/results/2026-11-09/`, and set `AI_MODEL=anthropic/claude-haiku-5.5` in `.env.example`.
  - `test_ai_openai_variables_are_documented_in_env_example` asserted an empty `AI_MODEL=`. It now asserts the chosen value exactly, as the issue requires. New tests check that `.env.example` names the model from the decision note, and that the committed results are fully reviewed and contain no key, authorization header or placeholder.
- **How I verified it:**
  - `uv run pytest tests/unit`: 590 passed. `uv run pytest tests/integration` (PostgreSQL via `docker compose up -d db`): 513 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean.
  - Changing `AI_MODEL` in `.env.example` makes the new test fail.
  - The result files were scanned for `bearer`, `authorization`, `sk-or-`, `api_key` and `placeholder`; none are present.
- **Left open:**
  - GPT-5.4 mini's suggestion for en-06 took 16.7 s, past the 15 s timeout, because the SDK timeout applies per connection phase (the open point from #13). Haiku's slowest calls were 3.0 s and 8.2 s.
  - GPT-5.4 mini's summaries are unmeasured because of rate limiting.
  - The product owner closes the open question in `product-spec.md` §13. Setting the model and key in production is #38.

## 2026-11-09: Orchestrator: #14 unblocked, implemented, QA PASS, closed

- **Unblocking:** the product owner saved a separate development OpenRouter key (limit $5) as a network secret on the "winlog" cloud environment and added $10 of credits. The orchestrator confirmed the key and the balance only through the free endpoints `/api/v1/key` and `/api/v1/credits`. The engineer then ran the free `check` step.
- **Product owner decisions:**
  - Strict zero-data-retention reading: endpoints with OpenRouter's `safety_retention` flag do not count. Gemini 3.8 Flash was excluded (all of its ZDR endpoints have the flag), and Qwen3.8 Flash because it has no ZDR endpoint.
  - Exactly one paid run was approved, with four models: GPT-5.4 mini, Claude Haiku 5.5, Mistral Small and DeepSeek V4.1 Flash as a spare, at an estimated $0.23.
- The engineer ran it once. The actual cost was $0.0303; QA found it exactly equals the key's usage, so no other paid calls were made. GPT-5.4 mini got HTTP 429 on 7 of its 28 calls, recorded and not retried. Chosen default: `anthropic/claude-haiku-5.5` (24/24 categories, 4/4 summary languages, quality 4.8, about $0.41 a day at the global cap of 100). It is set as `AI_MODEL` in `.env.example`. The engineer agent rated the summaries, and the note says so (d2fe2f4, 058c90c, c8d4462, c58cb19; https://github.com/KittyNiuNiu/winlog/issues/14#issuecomment-6735075467).
- QA PASS on every criterion in the first round, with no real AI calls (https://github.com/KittyNiuNiu/winlog/issues/14#issuecomment-6749416769): 590 unit and 513 integration tests pass, lint is clean. Closed #14 as completed.
- **Open points**, recorded where they belong:
  - #61: the per-phase SDK timeout was confirmed in the run (a 16.7 s GPT-5.4 mini suggestion against a 15 s timeout) (https://github.com/KittyNiuNiu/winlog/issues/61#issuecomment-6749429249).
  - #38: the chosen production model, and that the maximum daily cost is an estimate (no output token limit), so the production key's spending limit is the real cap (https://github.com/KittyNiuNiu/winlog/issues/38#issuecomment-6749430929).
  - Left in this log by the product owner's choice:
    - The note says every rating has a reason, but the 91 passed tag ratings have none.
    - One Mistral review note wrongly says it invented "Python", which was an input tag. The rating and the decision are unchanged.
    - GPT-5.4 mini's summaries were not measured because of the 429s.
    - The note does not mention that the script's calls bypass the app's usage limits.
  - For the product owner: close the open question in `product-spec.md` §13.

## 2026-11-09: Implement #16 (AI suggestions endpoint)

- **Task:** #16, `POST /suggestions` (`suggestCategoryAndTags`): AI suggestions for an entry's category and tags that save nothing (FR-S1, FR-S2, §7.3, §8).
- **What I did:**
  - New `backend/app/suggestions.py`, registered in `app/main.py`. The request body uses the entry text rules (`EntryText`), so missing, empty, whitespace-only or unstorable text is the shared validation error before anything is counted.
  - The endpoint calls `LimitedAI.suggest(user.id, text)` through `LimitedAIDependency` (#15), so limits are checked before the AI call and a reached limit is the 429 `limit_reached` error. `AIError` (timeout, provider failure, unusable output) becomes the 503 `ai_unavailable` error, raised `from None`, so the provider exception (which may repeat entry text, open point from #12) is never its cause or context in a traceback. Nothing in the module logs.
  - The session is closed before the AI call, so no database connection or transaction is held while the AI answers.
  - Suggested tag names are cleaned with #8's rules, matched to the user's own tags with `lookup_tags`, and get the stored spelling. Names that match each other (case-insensitive, PostgreSQL `lower()`) are returned once, then the list is cut to 5. To map each name to its stored tag I made #8's private `_match_keys` public as `match_keys` (rename only).
  - `tests/unit/test_auth.py`: added the new router to the list of routers that must use `AuthenticateFirstRoute` (the test checks that this list holds every operation).
- **How I verified it:**
  - New `tests/unit/test_suggestions.py` (contract, validation, error mapping, limit errors, no chained provider error) and `tests/integration/test_suggestions.py` (34 tests against PostgreSQL with the mock provider: success, only the text reaches the AI, counting, case matching, cleaning, another user's tag, duplicates, the 5-tag cap, nothing saved, validation, both limits, timeout, provider failure, unusable output, no token, logs free of text and tags).
  - Mutating the endpoint (no stored spelling, no cap, chained error) makes 9 of these tests fail.
  - `uv run pytest tests/unit`: 609 passed. `uv run pytest tests/integration`: 547 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. No real AI call; `AI_PROVIDER=mock` only. No new dependency.
- **Left open:** a maximum text size is #43; the frontend button and pre-fill are #28.

## 2026-11-09: Orchestrator: #16 implemented, QA PASS, closed

- The product owner asked for #16–#17. Before starting, the orchestrator merged `main` (which includes PR #62) into the working branch. #16 was `groomed`, so it went straight to the engineer, who added `POST /suggestions`. It calls `LimitedAI.suggest` through `LimitedAIDependency`, matches suggested tags to the user's stored spelling, removes duplicates, keeps at most 5, saves nothing, and maps every `AIError` to 503 `ai_unavailable`, raised `from None` so no provider message reaches a traceback (2305565, b4d8843, 34238e7; https://github.com/KittyNiuNiu/winlog/issues/16#issuecomment-6749744770). This covers the open points posted from #12 and #15.
- QA PASS on all 12 criteria in the first round, with only `AI_PROVIDER=mock` (https://github.com/KittyNiuNiu/winlog/issues/16#issuecomment-6749841491): 609 unit and 547 integration tests pass, lint is clean. QA ran live checks with `docker compose up --build`, and judged both side changes legitimate (`_match_keys` renamed to `match_keys`, and the new router added to the token-before-body test). Closed #16 as completed.
- **Open points:** the engineer listed none. Left in this log by the product owner's choice: the tag-rule tests are named `fr_s3_…`, though the rules come from the §7.3 acceptance criteria (`openapi.yaml` lists FR-S3 for this operation).
- Side effect of QA: test users `qa16-*@example.com` with usage rows are in the local dev database.

## 2026-11-09: Implement #17 (summary generation), one decision pending

- **Task:** #17, `POST /summaries` (`generateSummary`): generate an AI summary of the entries matching a filter and save it with that filter (FR-R3, FR-R4, FR-A3, §7.4, §8).
- **What I did:**
  - New `backend/app/summaries.py`, registered in `app/main.py`. The body is `SummaryFilter`: `period_start` and `period_end` are required real dates in `YYYY-MM-DD` form (the entry date rule), categories must be among the four, and tag names may not hold NUL or an unpaired surrogate (#11's `FilterTagName`). The endpoint checks that the start is not after the end (validation error naming `period_end`), because #11's `filter_entries` does not (open point from #11).
  - Entries come from `filter_entries`, so they are exactly what `GET /entries` returns for the same filter. No match is the 422 `no_matching_entries` error, raised before the limited entry point: no AI call, nothing counted, nothing saved.
  - The AI is called through `LimitedAI.summarise(user.id, entries)` via `LimitedAIDependency` (open point from #15), with `SummaryEntry.from_entry`, so only date, category, text, Result/Impact and tag names are sent. The session is closed during the AI call. `AIError` becomes 503 `ai_unavailable`, raised `from None` so the provider's exception never reaches a traceback (open point from #12). Nothing in the module logs.
  - The summary is saved with its period, its categories (each once) and its tag names cleaned with #8's rules: stored spelling when the user has the tag, names matching each other kept once, names empty after cleaning left out (they match nothing). The response is the saved summary with 201. No entry or tag is written.
  - `tests/unit/test_auth.py`: added the new router to the list of routers that must use `AuthenticateFirstRoute`.
- **How I verified it:**
  - New `tests/unit/test_summaries.py` (23 tests: contract shape, request model, filter passed to the shared filter, no match, period order, error mapping, limit errors, no chained provider error) and `tests/integration/test_summaries.py` (63 tests against PostgreSQL with the mock provider: saved filter, matching entries equal the list endpoint's for 7 filters, only §8's fields reach the adapter, entries unchanged, no match, validation, both limits, timeout, provider failure, unusable output, no token, two users, another user's tag name, logs free of entry and summary text).
  - Mutations (no period-order check, chained AI error, no stored spelling, no category de-duplication, no commit) each make tests fail.
  - `uv run pytest tests/unit`: 632 passed. `uv run pytest tests/integration`: 610 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. Live check with `uvicorn` and `AI_PROVIDER=mock` against the dev database: no match 422, success 201, period order 422, no token 401, second summary 429 `user_summaries`. No real AI call. No new dependency.
- **Left open (decision needed):** a generated summary longer than 10,000 characters (`product-spec.md` §7.4), and a summary the model cut off (open point from #13: no `max_tokens`, no `finish_reason` check), are saved as they are. The criteria, `openapi.yaml` and the spec do not say whether to treat them as `ai_unavailable`, cut them to 10,000 characters, or something else, so I asked on the issue instead of deciding.

## 2026-11-09: Implement #17 (summary generation): summary length and cut-off answers

- **Task:** finish #17 with the product owner's decisions of 2026-11-09 (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6750566660): (1) a summary longer than 10,000 characters, or one the model cut off, is an unusable AI answer: 503 `ai_unavailable`, nothing saved, the attempted call still counts (§8); the length check goes in the adapter's shared summary check (#12). (2) In the OpenAI-compatible provider (#13), `finish_reason` "length" is a provider failure, and summary requests send a `max_tokens` that fits the 10,000-character limit. The earlier session's endpoint work (fbbb69d, 3cea2a9, 28c4140) was already pushed; I continued from it.
- **What I did:**
  - `backend/app/ai/adapter.py`: `MAX_SUMMARY_CHARACTERS = 10_000` (a fixed rule of `product-spec.md` §7.4, counted in characters, not bytes). `_checked_summary` raises `AIProviderError` above it, so every provider shares the check; the endpoint already maps it to 503 and saves nothing, and `LimitedAI` counts the call before it is made.
  - `backend/app/ai/openai_compatible.py`: an answer with `finish_reason == "length"` raises `AIProviderError` (for summaries and suggestions; the message holds no content). Summary requests send `max_tokens`; suggestion requests send none (not part of the decision, and their answer is a short JSON object). The summary prompt takes "10,000" from the adapter's constant (same text as before).
  - `max_tokens` comes from a new setting, `AI_SUMMARY_MAX_TOKENS` (`app/settings.py`, `.env.example`), default 16000, whole number from 1 to 100000. Why a setting: the right value depends on the model (tokenizer, reasoning tokens, its own output cap), and `AGENTS.md` asks for no hard-coded limits. Why 16000: 10,000 characters are about 2,500 tokens in English (about 4 characters per token), about 3,300 in German (about 3; #14's pessimistic estimate) and up to about 10,000 in Chinese, Japanese or Korean (about 1 per character). Reasoning tokens count against `max_tokens` too: up to 3,400 per summary in #14's run (DeepSeek), under 100 for the default model. 10,000 + 3,400 rounded up with margin gives 16,000, so the bound does not cut a valid summary in any of these languages. A larger value only raises the cost bound, because the adapter rejects anything over 10,000 characters; at the default model's output price ($0.55 per million tokens, #14) 16,000 tokens cost at most about $0.009.
  - `backend/scripts/model_comparison/comparison.py`: passes the setting's default to the provider, as it already does for the timeouts (the constructor now needs it).
- **How I verified it:**
  - `tests/unit/test_ai.py`: exactly 10,000 characters accepted and 10,001 rejected, for 1-, 2-, 3- and 4-byte characters; the check applies to any `AIProvider` subclass; an over-long summary is not logged or put in the error.
  - `tests/unit/test_ai_openai_compatible.py`: `finish_reason` "length" fails for summaries and suggestions, "stop" and null pass; summary requests send `max_tokens` from the constructor and from the settings; suggestion requests send no `max_tokens`; the setting's default, environment value, invalid values and `.env.example` line; the default leaves room for one token per character plus reasoning; a 10,001-character answer with "stop" fails through the adapter. Updated where the decision requires: the summary request body now also holds `max_tokens`, and the privacy test includes a cut-off answer. `tests/unit/test_settings.py` lists the new setting.
  - `tests/integration/test_summaries.py` (PostgreSQL, mock provider): a 10,001-character summary gives 503 `ai_unavailable`, saves nothing and counts the call for the user and globally; a 10,000-character summary is saved whole (ASCII and CJK).
  - Mutations (limit off by one, no `finish_reason` check, no `max_tokens`) each make unit tests fail.
  - `uv run pytest tests/unit`: 659 passed. `uv run pytest tests/integration`: 614 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. No real AI call: only `AI_PROVIDER=mock` and stubbed HTTP. No new dependency.
- **Left open:** `docker-compose.yml` passes only `AI_PROVIDER` of the AI settings to the backend container (as before for the timeouts and limits), so `AI_SUMMARY_MAX_TOKENS` uses its default there. Other `finish_reason` values (such as "content_filter" or "error") are still judged by their text only; the decision covered "length". A maximum size of the input entries is #43.

## 2026-11-09: Orchestrator: #17 implemented, blocked on a decision, finished, QA PASS, closed

- #17 was `groomed`, so it went to the engineer with the four open points from #11, #12, #13 and #15. The engineer added `POST /summaries` (fbbb69d, 3cea2a9, 28c4140) and returned BLOCKED on one product decision: what to do with an AI summary over 10,000 characters or cut off by the model (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6750121570).
- **Product owner decisions** (recorded at https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6750566660):
  - Such a summary is an unusable AI answer: 503 `ai_unavailable`, nothing saved, and the attempt still counts. The 10,000-character check goes in the adapter's shared summary check.
  - The provider change is done within #17: `finish_reason == "length"` is a failure, and summary requests send `max_tokens`.
- The container restarted, so a new engineer session finished the work (2fefc16, 7aa9b90, 45c1e99; https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6750719739). It added the setting `AI_SUMMARY_MAX_TOKENS` (default 16000: up to about 10,000 tokens for CJK text plus reasoning tokens).
- QA PASS on every criterion and both decisions in the first round, with only the mock provider and stubbed HTTP (https://github.com/KittyNiuNiu/winlog/issues/17#issuecomment-6750827933): 659 unit and 614 integration tests pass, lint is clean. Closed #17 as completed.
- **Open points**, recorded where they belong:
  - #61: Compose does not forward `AI_SUMMARY_MAX_TOKENS` (https://github.com/KittyNiuNiu/winlog/issues/61#issuecomment-6750845988). Finish reasons other than `length` (for example `content_filter`) are not treated as failures; the product owner chose to add this to #61.
  - #38: check that the production model's output cap accepts `AI_SUMMARY_MAX_TOKENS`, and add the setting to the production variables (https://github.com/KittyNiuNiu/winlog/issues/38#issuecomment-6750847264).
  - #43 already holds the maximum size of the entries sent in one summary.
- Side effect of QA and the engineer's live checks: test users `se17-*`, `qa17a-*` and `qa17b-*`, with entries, summaries and usage rows, are in the local dev database.

## 2026-11-09: Implement #18 (saved summary management)

- **Task:** #18, list, get, edit and delete saved summaries (FR-R5, FR-A3, §7.4): `listSummaries`, `getSummary`, `updateSummary` and `deleteSummary` in `openapi.yaml`.
- **What I did:**
  - `backend/app/summaries.py` (the router from #17): `GET /summaries` returns the user's summaries with text and filter, newest first by `created_at` (id as a tie-breaker), not paginated. `GET`, `PATCH` and `DELETE /summaries/{summaryId}` load the summary scoped to the user, so another user's summary is the same 404 `not_found` as a missing id and stays unchanged.
  - `SummaryUpdate` takes only `text`, with the entry text rules (#9's `EntryText`): required, stored exactly as typed, not empty or only whitespace (`pattern: '\S'`), no NUL or unpaired surrogate. Other fields, such as `filter`, are ignored. The row is locked (`FOR UPDATE`) and always written, so the trigger sets `updated_at` even for the same text and the last of two edits wins; `created_at`, the filter and all entries are untouched.
  - The id uses #10's UUID rule (`_require_uuid`), so a wrong format is the validation error naming `summaryId`. Delete answers 204; deleting again is 404. All routes use `AuthenticateFirstRoute`, so without a valid token every operation is 401 and changes nothing, even with a bad body. Nothing is logged.
  - No maximum length for edited text: `SummaryUpdate` in `openapi.yaml` sets none, and the issue moves it to #43.
- **How I verified it:**
  - New `tests/unit/test_summary_management.py` (60 tests: the four operations match the contract, current-user dependency, edit body rules, extra fields ignored, wrong id formats, 401 without a token, no text in validation errors).
  - New `tests/integration/test_summary_management.py` (125 tests against PostgreSQL, summaries generated with the mock provider or stored directly: order and content of the list, empty list, no pagination, get, edit changes only the text and keeps the stored filter, text exactly as typed, invalid text changes nothing, non-object bodies, `updated_at`/`created_at`, last edit wins, edits never change entries, tags or links, ids and owner in the body ignored, delete keeps entries, second delete 404, missing ids, another user's summary for all operations and the list, wrong id formats, no/invalid/expired token for all four operations, summary text never logged).
  - Mutations (list not scoped to the user, oldest first, no forced write, get/edit or delete not scoped, text trimmed) each make integration tests fail.
  - `uv run pytest tests/unit`: 719 passed. `uv run pytest tests/integration`: 739 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. No AI call (the mock provider only for generating test summaries). No new dependency.
- **Left open:** the 10,000-character limit for edited summary text is #43. `summaries.py` imports `_require_uuid` from `entries.py` to share the id rule; a shared public helper could replace it later.

## 2026-11-09: Orchestrator: #18 implemented, QA PASS, closed

- The product owner asked for #18–#19. Before starting, the orchestrator merged `main` (which includes PR #63) into the working branch. #18 was `groomed`, so it went straight to the engineer, who added list, get, edit (`PATCH`, text only) and delete for saved summaries in `backend/app/summaries.py`, all limited to the logged-in user (edf7da1, c0cbbd1, eaef272; https://github.com/KittyNiuNiu/winlog/issues/18#issuecomment-6751102292).
- QA PASS on every criterion in the first round, with only `AI_PROVIDER=mock` (https://github.com/KittyNiuNiu/winlog/issues/18#issuecomment-6751181128): 719 unit and 739 integration tests pass, lint is clean. QA also checked the system live with two users. Closed #18 as completed.
- **Open points**, recorded where they belong:
  - #43: edited summary text has no maximum length yet (a 200,000-character edit was accepted); the shared `MAX_SUMMARY_CHARACTERS` from #17 could be reused (https://github.com/KittyNiuNiu/winlog/issues/43#issuecomment-6751188925).
  - #58: a non-JSON body gives 422 with `field: "0"` and "JSON decode error", from the shared validation handler (https://github.com/KittyNiuNiu/winlog/issues/58#issuecomment-6751190144).
  - Left in this log by the product owner's choice: `summaries.py` imports the private `_require_uuid` from `entries.py`; a shared public helper would be cleaner.

## 2026-11-09: Implement #19 (data export in JSON and Markdown)

- **Task:** #19, `GET /export/json` and `GET /export/markdown` (`exportJson`, `exportMarkdown` in `openapi.yaml`; FR-D1, FR-A3, §7.6, §8).
- **What I did:**
  - New `backend/app/export.py`. `collect_export` is the one function that collects the data; `render_json` and `render_markdown` both render its result, so both files always hold the same entries and summaries. Entries come from #11's `filter_entries` with an empty filter (the entry list's order: date, then creation time, newest first); summaries from #18's list query, which I moved into a shared `user_summaries` in `backend/app/summaries.py` (the list endpoint now uses it too; behaviour unchanged). Both are scoped to the user.
  - JSON: `ExportFile` with `format_version` 1, `exported_at` (UTC), and the entries and summaries with exactly the fields of the `Entry` and `Summary` schemas (summaries with their filter). No email, password hash, token, user id or usage data.
  - Markdown: `# Winlog export`, `Exported on YYYY-MM-DD`, `## Entries` and `## Summaries`. Each entry is `### <date> · <category>`, then its text, `Result/Impact: …` (only if it has one) and `Tags: …` (`None` without tags). Each summary is `### <created UTC date> · <start> to <end> · Categories: … · Tags: …` (`all` for an empty list, which means no restriction), then its text. Text is written as stored, without escaping. An empty section says `None`, which matches the example in `openapi.yaml`.
  - Downloads: `Content-Disposition: attachment; filename="winlog-export-YYYY-MM-DD.json"` or `.md`, from the UTC date of the export time. Content types `application/json; charset=utf-8` and `text/markdown; charset=utf-8`; non-ASCII text is written unchanged (no `\u` escapes). The routes use `AuthenticateFirstRoute`, so no valid token is 401 `not_authenticated`. They have no AI dependency, write nothing, and log nothing.
- **How I verified it:**
  - New `tests/unit/test_export.py` (27 tests: both operations and `ExportFile` match the contract, no AI dependency on the routes, both formats from the same data and order, JSON fields, empty account (equal to the contract's Markdown example), every entry and summary in Markdown, text without escaping, non-English text, UTC file names, no token). `tests/unit/test_auth.py` lists the new router.
  - New `tests/integration/test_export.py` (33 tests against PostgreSQL, mock provider only): JSON entries and summaries equal the list endpoints' responses (order and fields), Markdown holds every entry and summary in that order, both formats hold the same data, export time, text exactly as written, empty account, headers, content types and file names, CORS exposes `Content-Disposition`, non-English text, no email/password hash/token/user id/usage, works with the mock AI failing (timeout and provider error) and with the global AI limit reached, writes nothing, no/invalid/expired token, two users, nothing logged.
  - Mutations (reversed entry order, ASCII-escaped JSON, stripped summary text, Result/Impact always shown, local instead of UTC date) each make tests fail.
  - `uv run pytest tests/unit`: 746 passed. `uv run pytest tests/integration`: 772 passed. `uv run ruff check .` and `uv run ruff format --check .` are clean. Live check with `uvicorn` and `AI_PROVIDER=mock` against the dev database (user `se19-*`): empty and filled exports, headers and 401. No real AI call. No new dependency.
- **Left open:** the shared `ContentDisposition` header example in `openapi.yaml` still shows a `.json` file name for the Markdown export too (open point from #2, comment on #19). The issue does not allow editing `openapi.yaml`, so I left it; the code sends `.md` as the criteria require. Entry or summary text that itself contains Markdown headings (for example a line `## Summaries`) is copied unescaped, as the criteria require, so it can look like part of the file's structure. The download buttons are #34.

## 2026-11-09: Orchestrator: #19 implemented, QA PASS, closed

- #19 was `groomed`, so it went straight to the engineer, who added `GET /export/json` and `GET /export/markdown` in `backend/app/export.py`. Both are built from one shared `collect_export`, and the summaries list query moved into a shared `user_summaries` (2981c4f, 1cbe097, ffd414f, b1e08b0; https://github.com/KittyNiuNiu/winlog/issues/19#issuecomment-6751365512).
- QA PASS on all 17 criteria in the first round, with only `AI_PROVIDER=mock` (https://github.com/KittyNiuNiu/winlog/issues/19#issuecomment-6751448293): 746 unit and 772 integration tests pass, lint is clean. QA's live check with three accounts showed the empty Markdown export is byte-for-byte the `openapi.yaml` example, and that #18's list endpoint is unchanged after the refactor. Closed #19 as completed.
- **Open points**, recorded where they belong:
  - New issue #64, created on the product owner's instruction: the shared `ContentDisposition` example in `openapi.yaml` shows a `.json` file name for the Markdown export too. The code sends `.md`; fixing the example needs a contract edit.
  - Left in this log by the product owner's choice: because text is not escaped (as required), a heading line inside an entry or summary renders as a heading when the Markdown file is viewed formatted. The data stays complete.
- Housekeeping: the orchestrator removed QA's leftover test-account token files from the scratchpad. Test users from the live checks (`se19-*` and QA's accounts) remain in the local dev database.

## 2026-11-09: Orchestrator: close the open question about the default model (spec §13)

- **Task:** the product owner closed the open question in `product-spec.md` §13. They confirmed `anthropic/claude-haiku-5.5` as the default model and chose `deepseek/deepseek-v4.1-flash` as the backup.
- **Product owner decision:** "backup" means a documented alternative that is switched to by changing `AI_MODEL`, not an automatic retry. The app keeps making at most one AI call per user action (#13).
- **What I did:**
  - `docs/product-spec.md`: §13 now lists no open questions and records the closed one with the default and backup model. "Last updated" is 9 November 2026, and the change log has an entry. The version stays 0.2, so references in the issues still match.
  - `docs/decisions/default-model.md`: added the backup model at the top, as product owner decision 3, and in the Decision section with its trade-offs (same quality, about 3.5 times the cost per summary, slower). Before switching, its prices and ZDR endpoints should be checked again with the free `check` command.
- **How I verified it:** `uv run pytest tests/unit` (746 passed, including the test that ties `.env.example` to the decision note) and `uv run ruff check .` (clean). Documentation only; no code changed.

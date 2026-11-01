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

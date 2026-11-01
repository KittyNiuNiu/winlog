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

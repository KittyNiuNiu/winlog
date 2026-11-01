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

- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly
- PM - grooms a task before anyone implements it, follows docs/pm.md
- Designer - for tasks that change screens: writes a design note before the build and
  reviews the screens after QA, follows docs/ux-designer.md and DESIGN.md
- Engineer - implements one groomed task, follows docs/software-engineer.md
- QA - checks the result against the acceptance criteria, follows docs/qa-engineer.md

Orchestrator

The main session is the orchestrator. It launches the PM, the designer, the engineer
and QA as subagents. It does not groom, design, implement or test itself.

Lifecycle

1. Pick the next open issue from the backlog
2. PM grooms it, if it is not already done.
3. If the task changes screens: the designer writes a design note, if it is not already done.
4. Engineer implements it, if it is not already done.
5. QA verifies it
6. On FAIL, back to step 4 with the QA comment as input
7. On PASS: if the task changes screens, the designer reviews the screens.
   On a design FAIL, back to step 4 with the design review as input, then QA again.
8. When every check has passed, close the issue
9. Repeat until the backlog is empty

A task changes screens when it adds or changes anything a user sees in the frontend:
screens, components, styles or interface text. When it is unclear, the orchestrator asks
the product owner.

Rules

- Do not skip step 2, if it is not already done.
- Do not skip steps 3 and 7 for a task that changes screens.
- The engineer does not close the issue
- QA and the designer do not fix the code; they only output PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS and, for a task that
  changes screens, the design review outputs PASS. It never deletes issues.
- When it closes an issue, the orchestrator posts each open point from the engineer, QA and
  the designer as a comment on the open issue it belongs to. If no issue fits, it asks the
  product owner.

How the orchestrator works

- Start it with `/orchestrate` (the next issue), `/orchestrate <issue number>` (that issue)
  or `/orchestrate all` (keep going until the backlog is empty or a stop point is reached).
  The steps are in `.claude/skills/orchestrate/SKILL.md`.
- The subagents are defined in `.claude/agents/`: `pm`, `ux-designer`,
  `software-engineer` and `qa-engineer`. Only the orchestrator launches them; they do not
  launch agents.
- Next issue: issues labelled `implemented`, `qa-failed` or `design-failed` come first, so
  finished work is checked before new work starts. Otherwise, the lowest-numbered task in
  `docs/tasks.md` whose issue is still open. Open issues not listed in `docs/tasks.md` come
  after the listed ones, oldest first.
- Subagents cannot ask the product owner directly. They return their questions, and the
  orchestrator asks them one at a time and passes the answers back.

Status labels

Every open issue has exactly one status label, which shows where it is in the lifecycle.
The orchestrator sets it after each step, keeping any other labels; the roles do not change
labels.

- No status label: a new issue that needs grooming (step 2).
- `groomed`: ready for the design note (step 3) if it changes screens, otherwise ready to
  implement (step 4).
- `designed`: the design note is posted; ready to implement (step 4).
- `implemented`: waiting for QA (step 5).
- `qa-failed`: QA failed; back to the engineer (step 4, with the QA comment).
- `qa-passed`: QA passed on a task that changes screens; waiting for the design review
  (step 7).
- `design-failed`: the design review failed; back to the engineer (step 4, with the design
  review). QA checks the fix again before the next design review.
- Closed: every check passed. The last status label stays on the closed issue.

Stop points (the orchestrator stops and asks the product owner)

- A role needs a product decision.
- An acceptance criterion is wrong, impossible or contradicts another one, or contradicts
  `DESIGN.md`.
- QA outputs FAIL twice for the same issue, or the design review outputs FAIL twice for the
  same issue.
- Tests cannot run, for example because Docker or the database is unavailable.
- After closing an issue, unless the run was started with `all`.

Product decisions

- Standing rule (product owner, 2026-11-01): accept the PM's recommended option without
  asking when it fits the product scope and keeps development simple, maintainable and
  scalable. Anything outside the product scope goes to the product owner. Every decision is
  recorded in the issue and in `docs/ai-workflow.md`.
- Design decisions follow `DESIGN.md`. A design question that `DESIGN.md` does not answer
  goes to the product owner.

Branches and logging

- The engineer commits and pushes to the session's working branch. The product owner opens
  and merges pull requests.
- The PM and the engineer each add their own entry to `docs/ai-workflow.md`. QA and the
  designer change nothing; their notes and verdicts are issue comments. The orchestrator
  adds a short entry when it closes an issue.

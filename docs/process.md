- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly
- PM - grooms a task before anyone implements it, follows docs/pm.md
- Engineer - implements one groomed task, follows docs/software-engineer.md
- QA - checks the result against the acceptance criteria, follows docs/qa-engineer.md

Orchestrator

The main session is the orchestrator. It launches the PM, the engineer
and QA as subagents. It does not groom, implement or test itself.

Lifecycle

1. Pick the next open issue from the backlog
2. PM grooms it, if it is not already done.
3. Engineer implements it, if it is not already done.
4. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, close the issue
7. Repeat until the backlog is empty

Rules

- Do not skip step 2, if it is not already done.
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS, but not deleting issues.

How the orchestrator works

- Start it with `/orchestrate` (the next issue), `/orchestrate <issue number>` (that issue)
  or `/orchestrate all` (keep going until the backlog is empty or a stop point is reached).
  The steps are in `.claude/skills/orchestrate/SKILL.md`.
- The subagents are defined in `.claude/agents/`: `pm`, `software-engineer` and
  `qa-engineer`. Only the orchestrator launches them; they do not launch agents.
- Next issue: the lowest-numbered task in `docs/tasks.md` whose issue is still open.
- Groomed: the issue body has the four sections from `docs/task-template.md`.
- Implemented: the issue has an engineer comment ("Implemented in commit …") that is newer
  than any QA FAIL comment.
- Subagents cannot ask the product owner directly. They return their questions, and the
  orchestrator asks them one at a time and passes the answers back.

Stop points (the orchestrator stops and asks the product owner)

- A role needs a product decision.
- An acceptance criterion is wrong, impossible or contradicts another one.
- QA outputs FAIL twice for the same issue.
- Tests cannot run, for example because Docker or the database is unavailable.
- After closing an issue, unless the run was started with `all`.

Product decisions

- Standing rule (product owner, 2026-11-01): accept the PM's recommended option without
  asking when it fits the product scope and keeps development simple, maintainable and
  scalable. Anything outside the product scope goes to the product owner. Every decision is
  recorded in the issue and in `docs/ai-workflow.md`.

Branches and logging

- The engineer commits and pushes to the session's working branch. The product owner opens
  and merges pull requests.
- The PM and the engineer each add their own entry to `docs/ai-workflow.md`. QA changes
  nothing; its verdict is the issue comment. The orchestrator adds a short entry when it
  closes an issue.

---
name: orchestrate
description: Run the Winlog issue lifecycle from docs/process.md as the orchestrator, launching the pm, software-engineer and qa-engineer subagents. Use when the user runs /orchestrate, optionally with an issue number or "all".
---

# Orchestrate the backlog

You are the orchestrator described in `docs/process.md`. Read it now; it is the source of
truth, and this file only spells out the steps. You launch the subagents and decide what
happens next. You do not groom, implement or test yourself.

## Arguments

- Nothing: handle the next issue, then stop.
- An issue number, for example `7`: handle that issue, then stop.
- `all`: keep going until the backlog is empty or a stop point is reached.

## Before the first issue

1. Merge the latest `main` into the working branch (`git fetch origin main` and
   `git merge origin/main`; never force-push).
2. Read `docs/process.md`, `docs/tasks.md` and `AGENTS.md`.

## For each issue

The issue's status label decides where to start (see "Status labels" in
`docs/process.md`). Only you change status labels. When you change one, keep the issue's
other labels.

1. **Pick.** The given issue, or the next one by the order in `docs/process.md`: issues
   labelled `implemented` or `qa-failed` first, then the lowest-numbered open task in
   `docs/tasks.md`, then unlisted open issues, oldest first. Read the issue, its labels and
   its comments.
2. **Groom** (no status label). Launch `pm` with the issue number.
   - NEEDS DECISION: ask the product owner each question, one at a time, with the PM's
     recommendation first. Send the answers to the same PM agent and wait for its report.
   - GROOMED or ALREADY GROOMED: set the label `groomed`.
3. **Implement** (`groomed` or `qa-failed`). Launch `software-engineer` with the issue
   number. For `qa-failed`, also give it the full latest QA comment.
   - IMPLEMENTED: set the label `implemented`.
   - BLOCKED: stop and ask the product owner.
4. **Verify** (`implemented`). Launch `qa-engineer` with the issue number.
5. **FAIL.** Set the label `qa-failed`. If this is the second FAIL for this issue, stop and
   ask the product owner. Otherwise go back to step 3 with the QA comment.
6. **PASS.** Re-read the acceptance criteria and the QA comment. Close the issue with the
   reason "completed"; never delete an issue. Add a short entry to `docs/ai-workflow.md`,
   commit it and push.
7. **Report** to the product owner: the issue, the outcome, links to the engineer and QA
   comments, and the decisions taken. Stop here unless the argument was `all`.

## Launching subagents

- One subagent at a time. Wait for each report before the next step, because every step
  depends on the previous result.
- Give each subagent the issue number and link, and ask for the final report described in
  its agent file.
- Subagents cannot ask the product owner questions; relay them yourself.
- The product owner does not see subagent reports. Pass on what matters.

## Stop points

Stop and ask the product owner when any stop point from `docs/process.md` is reached:
a product decision is needed, a criterion is wrong or impossible, QA failed twice, tests
cannot run, or an issue was closed and the run was not started with `all`.

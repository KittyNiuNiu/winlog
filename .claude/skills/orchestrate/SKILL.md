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
   labelled `implemented`, `qa-failed` or `design-failed` first, then the lowest-numbered
   open task in `docs/tasks.md`, then unlisted open issues, oldest first. Read the issue,
   its labels and its comments. Decide whether it changes screens (see "Lifecycle" in
   `docs/process.md`); when unclear, ask the product owner.
2. **Groom** (no status label). Launch `pm` with the issue number.
   - NEEDS DECISION: ask the product owner each question, one at a time, with the PM's
     recommendation first. Send the answers to the same PM agent and wait for its report.
   - GROOMED or ALREADY GROOMED: set the label `groomed`.
3. **Design note** (`groomed`, and the issue changes screens). Launch `ux-designer` with
   the issue number and mode `note`.
   - NEEDS DECISION: ask the product owner, one question at a time, and send the answers
     to the same designer agent.
   - Note posted: set the label `designed`.
   - An issue that does not change screens skips this step and goes from `groomed` to
     step 4.
4. **Implement** (`designed`, `groomed` without screens, `qa-failed` or `design-failed`).
   Launch `software-engineer` with the issue number. For a screen issue, tell it to follow
   the design note on the issue and `DESIGN.md`. For `qa-failed`, also give it the full
   latest QA comment; for `design-failed`, the full latest design review.
   - IMPLEMENTED: set the label `implemented`.
   - BLOCKED: stop and ask the product owner.
5. **Verify** (`implemented`). Launch `qa-engineer` with the issue number.
   - FAIL: set the label `qa-failed`. If this is the second QA FAIL for this issue, stop
     and ask the product owner. Otherwise go back to step 4 with the QA comment.
   - PASS on a screen issue: set the label `qa-passed` and go to step 6.
   - PASS on any other issue: go to step 7.
6. **Design review** (`qa-passed`). Launch `ux-designer` with the issue number and mode
   `review`.
   - FAIL: set the label `design-failed`. If this is the second design FAIL for this
     issue, stop and ask the product owner. Otherwise go back to step 4 with the design
     review; QA checks the fix again before the next review.
   - PASS: go to step 7.
7. **Close.** Re-read the acceptance criteria, the QA comment and, for a screen issue, the
   design review. Close the issue with the reason "completed"; never delete an issue.
   Then record the open points:
   - Collect what the engineer listed as "left open", what QA listed as notes or
     findings outside the criteria, and what the designer listed outside the note.
   - Post each point that fits an open issue as a comment on that issue. Say what was
     found, link the source comment, and say it is an input for grooming, not a new
     requirement.
   - If no open issue fits a point, ask the product owner whether to create a new issue
     for it or to leave it in the log.

   Add a short entry to `docs/ai-workflow.md` that names where each open point went,
   commit it and push.
8. **Report** to the product owner: the issue, the outcome, links to the engineer, QA and
   designer comments, the decisions taken, and where each open point was recorded. Stop here
   unless the argument was `all`.

## Launching subagents

- One subagent at a time. Wait for each report before the next step, because every step
  depends on the previous result.
- Give each subagent the issue number and link, and ask for the final report described in
  its agent file.
- Subagents cannot ask the product owner questions; relay them yourself.
- The product owner does not see subagent reports. Pass on what matters.

## Stop points

Stop and ask the product owner when any stop point from `docs/process.md` is reached:
a product decision is needed, a criterion is wrong or impossible or contradicts
`DESIGN.md`, QA or the design review failed twice, tests cannot run, or an issue was closed and the run was not started with `all`.

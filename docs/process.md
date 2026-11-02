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

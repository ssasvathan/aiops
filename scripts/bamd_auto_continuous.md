Read `/home/sas/workspace/aiops/artifact/implementation-artifacts/sprint-status.yaml` and act as the coordinator for the BMAD implementation workflow.

Your job is to fully automate story execution across all epics, selected from the backlog queue, using strict sequential execution and safe failure behavior.

Repository and status rules:
- Use `/home/sas/workspace/aiops` as the working root.
- Treat `/home/sas/workspace/aiops/artifact/implementation-artifacts/sprint-status.yaml` as the source of truth.
- Build the execution queue from stories whose status is not `done`.
- Determine the target epic from the first non-`done` story encountered in sprint order.
- Only process non-`done` stories belonging to that target epic.
- Process stories one by one, in sprint order.
- When no non-`done` stories remain in the target epic, perform epic completion (see below).
- After epic completion, advance to the next epic that has non-`done` stories.
- Repeat until all stories across all epics are `done`.

Epic completion procedure:
- When no non-`done` stories remain in the target epic:
  1. Run `bmad retrospective` in full auto / yolo mode. Do not ask for user input.
  2. Mark the current epic as `done` in `sprint-status.yaml`.
  3. Create a git commit: `bmad(<epic>): retrospective and epic complete`
  4. Advance to the next epic that has non-`done` stories and continue execution.
- If no further epics with non-`done` stories exist, stop and report that all epics and stories are complete.

Story selection rules:
- Re-read `sprint-status.yaml` before selecting each next story.
- Pick the first story in the target epic whose status is not `done`.
- Resume from the selected story's current status instead of restarting from scratch.
- Only work on one story at a time.
- Do not run stories in parallel.

Execution model:
- Act as coordinator only.
- Spawn exactly one fresh worker/sub-agent per workflow step.
- Each step must run in its own fresh context.
- Do not start the next step until the previous step completes successfully.
- If any step fails, stop the entire pipeline immediately and report the failure.
- Do not continue after any such limit error.

Worker lifecycle and stuck detection rules:
- Never send `interrupt=true` to an active worker unless a human explicitly asks for an interrupt.
- Assume BMAD steps can be long-running. Do not treat a short timeout as failure.
- Close worker sessions aggressively to prevent thread exhaustion:
  - As soon as a worker reaches any terminal state (`completed`, explicit failure, capacity/limit error), close that worker immediately after capturing its result.
  - Do not leave completed workers open while launching later steps.
  - Keep at most one active/open worker per current step.
- Default wait policy per step:
  - Use `wait` with long timeout windows (10 minutes each).
  - Keep waiting/polling until success/failure/capacity error is explicit.
- After each timed-out wait, run heartbeat checks before deciding a worker is stuck:
  - Check whether expected artifacts for the current step changed since the last poll (file mtime/content/status movement in story file, sprint-status, runner logs, or implementation files).
  - If heartbeat exists, continue waiting.
- If no heartbeat is observed for 30 consecutive minutes, mark the step as `suspected-stuck` and stop the pipeline safely (no interrupt).
- Before marking `suspected-stuck`, send one non-interrupt status ping (`interrupt=false`) asking for concise progress/final state, then wait one more 10-minute window.
- If a worker session ends unexpectedly but artifacts show the step outcome is complete, run a completion verification checklist and resume from the resulting story status:
  - `bmad-bmm-create-story`: story markdown exists and story status is `ready-for-dev` (or later).
  - `bmad-tea-testarch-atdd`: acceptance tests and status transitions expected by workflow are present.
  - `bmad-bmm-dev-story`: implementation changes and story status advanced to `review` (or later).
  - `bmad-bmm-code-review`: findings report exists and all Critical/High/Medium/Low findings are resolved in code.
  - `bmad-tea-testarch-trace`: traceability artifact/decision output exists.
  - Final gates: both commands passed and pytest skip count is zero.
- If checklist is incomplete or ambiguous, fail safely and stop. Do not guess.

For each selected story, use status-aware entry and run only the remaining steps:
- If story status is `backlog`, run:
  1. `bmad-bmm-create-story`
  2. `bmad-tea-testarch-atdd`
  3. `bmad-bmm-dev-story`
  4. `bmad-bmm-code-review`
  5. `bmad-tea-testarch-trace`
  6. Final quality gates
- If story status is `ready-for-dev`, run:
  1. `bmad-tea-testarch-atdd`
  2. `bmad-bmm-dev-story`
  3. `bmad-bmm-code-review`
  4. `bmad-tea-testarch-trace`
  5. Final quality gates
- If story status is `in-progress`, run:
  1. `bmad-bmm-dev-story`
  2. `bmad-bmm-code-review`
  3. `bmad-tea-testarch-trace`
  4. Final quality gates
- If story status is `review`, run:
  1. `bmad-bmm-code-review`
  2. `bmad-tea-testarch-trace`
  3. Final quality gates

Final quality gates:
   `uv run ruff check`
   `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

Important workflow requirements:
- Run all BMAD steps in full auto / yolo style.
- Use the exact BMAD names above. Do not substitute shorthand names.
- In `bmad-bmm-code-review`, fix all findings with severity `Critical`, `High`, `Medium`, and `Low` before continuing.
- Do not leave unresolved review findings behind.
- Treat any failed test as failure.
- Treat any skipped test as failure.
- The workflow is only successful for a story if all BMAD steps succeed, `ruff` passes, pytest passes, and pytest reports `0 skipped`.

Status synchronization requirements:
- BMAD sometimes forgets to update story/sprint status. Do not assume status was updated correctly.
- After a story completes successfully, explicitly verify and update:
  - the story artifact markdown file
  - `/home/sas/workspace/aiops/artifact/implementation-artifacts/sprint-status.yaml`
- Ensure the story ends in the correct final status when all steps and gates pass.
- Do not mark a story `done` unless the full workflow, lint, and zero-skip regression suite all succeed.

Failure behavior:
- On any failure, stop immediately.
- Report:
  - target epic
  - story id
  - workflow step that failed
  - reason for failure
  - whether any files were changed
  - whether sprint/story status was updated or left unchanged
- Do not continue to the next story after a failure.

Successful completion behavior:
- After each successful story, re-read `sprint-status.yaml` and continue to the next remaining non-`done` story in the same target epic.
- When no non-`done` stories remain in the target epic, perform the epic completion procedure (retrospective, mark done, commit, advance to next epic).
- When no epics with non-`done` stories remain, stop and report that all work is complete.

Git commit requirements:
- Only after a successful story workflow execution, create exactly one git commit for changes produced by that story execution.
- Do not create a commit for failed story executions. On failure, stop and report that no commit was created due to failure.
- Commit timing is mandatory:
  - Perform the story commit immediately after that story reaches successful terminal outcome.
  - Do not defer or batch commits across multiple stories.
  - Do not start selecting or executing the next story until the current successful story's commit step is finished (or explicitly reported as `no-op commit`).
- Stage only files changed by that successful story execution. Do not include unrelated pre-existing workspace changes.
- If no files changed for that successful execution, do not create an empty commit; report `no-op commit`.
- Commit message must be explicit and structured:
  - Story success: `bmad(<epic>/<story-id>): complete workflow and quality gates`
  - Epic completion: `bmad(<epic>): retrospective and epic complete`
- Include in the final report:
  - commit hash
  - commit message
  - whether commit was created or `no-op commit` (successful stories only)
  - if failure stop occurred, explicitly state `commit not created due to failure`
- If commit creation fails, stop immediately and report the failure.

Final reporting format:
- Epics completed in this run
- Stories completed in this run (grouped by epic)
- If stopped on failure: failed epic, failed story, failed step, cause
- If stopped normally: state that all epics and stories are complete
#!/usr/bin/env python3
"""Run BMAD implementation workflows story-by-story for the active sprint epic.

This runner is intentionally conservative:
- It only processes stories from the currently active epic (`in-progress`).
- It stops on the first failure, including quota / rate-limit style failures.
- It never advances into the next epic or runs an epic retrospective.
- It verifies final lint/regression gates directly instead of trusting prompts.
- It repairs sprint/story status text when workflow output forgets to do so.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_STATUS_FILE = Path("artifact/implementation-artifacts/sprint-status.yaml")
DEFAULT_LOG_ROOT = Path("artifact/implementation-artifacts/runner-logs")
DEFAULT_TEST_COMMAND = (
    "TESTCONTAINERS_RYUK_DISABLED=true "
    "DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock "
    "uv run pytest -q -rs"
)
DEFAULT_LINT_COMMAND = "uv run ruff check"
USAGE_LIMIT_PATTERNS = (
    "usage limit",
    "rate limit",
    "quota",
    "too many requests",
    "insufficient_quota",
    "insufficient quota",
    "credit limit",
    "capacity",
    "token limit exceeded",
    "request limit",
)
STORY_STATUS_LINE_RE = re.compile(r"(?m)^- Story status: `([^`]+)`$")
SPRINT_STATUS_LINE_TEMPLATE = r"(?m)^(\s*{key}:\s*)(\S+)(\s*)$"


@dataclass(frozen=True)
class StepDefinition:
    name: str
    kind: str
    status_after: str | None = None


PIPELINE_BY_STATUS: dict[str, list[StepDefinition]] = {
    "backlog": [
        StepDefinition("bmad-bmm-create-story", "codex", "ready-for-dev"),
        StepDefinition("bmad-tea-testarch-atdd", "codex"),
        StepDefinition("bmad-bmm-dev-story", "codex", "review"),
        StepDefinition("bmad-bmm-code-review", "codex"),
        StepDefinition("bmad-tea-testarch-trace", "codex"),
        StepDefinition("lint", "shell"),
        StepDefinition("full-regression", "shell", "done"),
    ],
    "ready-for-dev": [
        StepDefinition("bmad-tea-testarch-atdd", "codex"),
        StepDefinition("bmad-bmm-dev-story", "codex", "review"),
        StepDefinition("bmad-bmm-code-review", "codex"),
        StepDefinition("bmad-tea-testarch-trace", "codex"),
        StepDefinition("lint", "shell"),
        StepDefinition("full-regression", "shell", "done"),
    ],
    "in-progress": [
        StepDefinition("bmad-bmm-dev-story", "codex", "review"),
        StepDefinition("bmad-bmm-code-review", "codex"),
        StepDefinition("bmad-tea-testarch-trace", "codex"),
        StepDefinition("lint", "shell"),
        StepDefinition("full-regression", "shell", "done"),
    ],
    "review": [
        StepDefinition("bmad-bmm-code-review", "codex"),
        StepDefinition("bmad-tea-testarch-trace", "codex"),
        StepDefinition("lint", "shell"),
        StepDefinition("full-regression", "shell", "done"),
    ],
}


@dataclass
class StepResult:
    story: str
    step: str
    success: bool
    started_at: str
    finished_at: str
    exit_code: int
    stdout_log: str
    stderr_log: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orchestrate BMAD implementation steps for the active sprint epic."
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help=f"Path to sprint status YAML (default: {DEFAULT_STATUS_FILE})",
    )
    parser.add_argument(
        "--log-root",
        type=Path,
        default=DEFAULT_LOG_ROOT,
        help=f"Directory for runner logs (default: {DEFAULT_LOG_ROOT})",
    )
    parser.add_argument(
        "--epic",
        help="Explicit active epic key such as epic-1. If omitted, auto-detect from sprint status.",
    )
    parser.add_argument(
        "--story",
        help="Run only a single story key, for example 1-4-resolve-topology-ownership-...",
    )
    parser.add_argument(
        "--max-stories",
        type=int,
        default=None,
        help="Maximum number of stories to process in this run.",
    )
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable to invoke for BMAD steps (default: codex).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional Codex model override, passed through to `codex exec -m`.",
    )
    parser.add_argument(
        "--lint-command",
        default=DEFAULT_LINT_COMMAND,
        help=f"Final lint gate command (default: {DEFAULT_LINT_COMMAND!r}).",
    )
    parser.add_argument(
        "--test-command",
        default=DEFAULT_TEST_COMMAND,
        help="Final regression gate command.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the stories and steps that would run without invoking Codex or shell gates.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_status_data(status_file: Path) -> dict[str, Any]:
    data = yaml.safe_load(status_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "development_status" not in data:
        raise ValueError(f"{status_file} does not contain development_status")
    development_status = data["development_status"]
    if not isinstance(development_status, dict):
        raise ValueError(f"{status_file} development_status must be a mapping")
    return data


def detect_active_epic(status_data: dict[str, Any], explicit_epic: str | None) -> str | None:
    development_status: dict[str, str] = status_data["development_status"]
    if explicit_epic is not None:
        if development_status.get(explicit_epic) != "in-progress":
            raise ValueError(
                f"Explicit epic {explicit_epic!r} is not marked in-progress in sprint status"
            )
        return explicit_epic

    active_epics = [
        key
        for key, value in development_status.items()
        if key.startswith("epic-")
        and not key.endswith("-retrospective")
        and value == "in-progress"
    ]
    if len(active_epics) > 1:
        raise ValueError(
            f"Multiple active epics found: {', '.join(active_epics)}. Re-run with --epic."
        )
    if not active_epics:
        return None
    return active_epics[0]


def epic_story_prefix(epic_key: str) -> str:
    match = re.fullmatch(r"epic-(\d+)", epic_key)
    if not match:
        raise ValueError(f"Unsupported epic key format: {epic_key}")
    return f"{match.group(1)}-"


def stories_for_epic(status_data: dict[str, Any], epic_key: str) -> list[tuple[str, str]]:
    prefix = epic_story_prefix(epic_key)
    stories: list[tuple[str, str]] = []
    for key, value in status_data["development_status"].items():
        if key.startswith(prefix) and not key.endswith("-retrospective"):
            stories.append((key, value))
    return stories


def next_story(
    status_data: dict[str, Any],
    epic_key: str,
    explicit_story: str | None,
) -> tuple[str, str] | None:
    epic_stories = stories_for_epic(status_data, epic_key)
    if explicit_story is not None:
        for story_key, status in epic_stories:
            if story_key == explicit_story:
                if status == "done":
                    return None
                return story_key, status
        raise ValueError(f"Story {explicit_story!r} does not belong to {epic_key}")

    for story_key, status in epic_stories:
        if status != "done":
            return story_key, status
    return None


def pipeline_for_status(story_status: str) -> list[StepDefinition]:
    if story_status == "done":
        return []
    try:
        return PIPELINE_BY_STATUS[story_status]
    except KeyError as exc:
        raise ValueError(f"Unsupported story status for automation: {story_status}") from exc


def build_step_prompt(
    step_name: str,
    story_key: str,
    status_file: Path,
    story_file: Path,
    test_command: str,
    lint_command: str,
) -> str:
    preamble = (
        f"You are executing exactly one BMAD workflow step for story `{story_key}`.\n"
        f"Use the exact skill name `{step_name}`.\n"
        "Run in full auto / yolo style within the current workspace.\n"
        "Stop immediately and report failure if you hit any usage limit, rate limit, "
        "quota issue, or blocked prerequisite.\n"
        "Do not start any later workflow step yourself.\n"
        f"Sprint source of truth: `{status_file}`.\n"
        f"Expected story artifact: `{story_file}`.\n"
    )

    task_specific = {
        "bmad-bmm-create-story": (
            "Create or refresh the story artifact for this story so it is implementation-ready. "
            "If the artifact already exists, update it safely instead of duplicating it."
        ),
        "bmad-tea-testarch-atdd": (
            "Generate or refresh ATDD coverage for this story. "
            "Keep the work scoped to this story only."
        ),
        "bmad-bmm-dev-story": (
            "Implement the story completely. Run the story workflow normally, but do not claim the "
            "story is done yet because review, traceability, and final gates still follow."
        ),
        "bmad-bmm-code-review": (
            "Perform adversarial code review for this story, then fix every finding with severity "
            "`Critical`, `High`, `Medium`, and `Low` before finishing. Do not leave unresolved "
            "review findings behind."
        ),
        "bmad-tea-testarch-trace": (
            "Generate or refresh traceability output for this story "
            "after implementation and review fixes."
        ),
    }

    verification = (
        "The orchestrator will run final gates directly after the BMAD steps:\n"
        f"- `{lint_command}`\n"
        f"- `{test_command}`\n"
        "Do not mark the story done unless your work is actually complete; the orchestrator will "
        "verify and repair status tracking after final success."
    )

    response_format = (
        "Final response format:\n"
        "Success: yes|no\n"
        f"Story: {story_key}\n"
        f"Step: {step_name}\n"
        "Files changed: comma-separated list or 'none'\n"
        "Notes: one concise paragraph"
    )

    return "\n\n".join([preamble, task_specific[step_name], verification, response_format])


def run_process(
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    stdin_text: str | None = None,
) -> tuple[int, str, str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=cwd,
            input=stdin_text,
            text=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
            check=False,
        )
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    return completed.returncode, stdout_text, stderr_text


def has_usage_limit_error(*texts: str) -> bool:
    merged = " ".join(texts).lower()
    return any(pattern in merged for pattern in USAGE_LIMIT_PATTERNS)


def shell_detail_for_output(output: str) -> str:
    skip_counts = [int(match.group(1)) for match in re.finditer(r"\b(\d+)\s+skipped\b", output)]
    if any(count > 0 for count in skip_counts):
        return "Regression failed because one or more tests were skipped."
    return "Command completed successfully."


def update_sprint_story_status(status_file: Path, story_key: str, new_status: str) -> bool:
    text = status_file.read_text(encoding="utf-8")
    pattern = re.compile(SPRINT_STATUS_LINE_TEMPLATE.format(key=re.escape(story_key)))
    updated, count = pattern.subn(rf"\1{new_status}\3", text, count=1)
    if count == 0:
        return False
    status_file.write_text(updated, encoding="utf-8")
    return True


def upsert_story_file_status(story_file: Path, new_status: str) -> bool:
    if not story_file.exists():
        return False

    text = story_file.read_text(encoding="utf-8")
    replaced, count = STORY_STATUS_LINE_RE.subn(f"- Story status: `{new_status}`", text, count=1)
    if count == 1:
        story_file.write_text(replaced, encoding="utf-8")
        return True

    header = "## Story Completion Status"
    if header in text:
        updated = text.replace(header, f"{header}\n\n- Story status: `{new_status}`", 1)
        story_file.write_text(updated, encoding="utf-8")
        return True

    suffix = (
        "\n\n## Story Completion Status\n\n"
        f"- Story status: `{new_status}`\n"
    )
    story_file.write_text(text.rstrip() + suffix, encoding="utf-8")
    return True


def persist_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def dry_run_summary(story_key: str, story_status: str, steps: list[StepDefinition]) -> None:
    print(f"[dry-run] story={story_key} current_status={story_status}")
    for step in steps:
        print(f"  - {step.name} ({step.kind})")


def run_story_pipeline(
    *,
    repo_root: Path,
    log_dir: Path,
    story_key: str,
    story_status: str,
    status_file: Path,
    codex_bin: str,
    model: str | None,
    lint_command: str,
    test_command: str,
    dry_run: bool,
    manifest_path: Path,
    manifest_payload: dict[str, Any],
) -> tuple[bool, str, list[StepResult]]:
    story_file = status_file.parent / f"{story_key}.md"
    steps = pipeline_for_status(story_status)
    if dry_run:
        dry_run_summary(story_key, story_status, steps)
        return True, "dry-run", []

    step_results: list[StepResult] = []
    for index, step in enumerate(steps, start=1):
        started_at = utc_now()
        step_slug = step.name.replace("/", "-")
        base = f"{index:02d}_{story_key}_{step_slug}"
        stdout_log = log_dir / f"{base}.stdout.log"
        stderr_log = log_dir / f"{base}.stderr.log"

        if step.kind == "codex":
            prompt = build_step_prompt(
                step.name,
                story_key,
                status_file.resolve(),
                story_file.resolve(),
                test_command,
                lint_command,
            )
            (log_dir / f"{base}.prompt.txt").write_text(prompt, encoding="utf-8")
            command = [
                codex_bin,
                "exec",
                "--full-auto",
                "--color",
                "never",
                "--cd",
                str(repo_root),
                "-",
            ]
            if model:
                command.extend(["-m", model])
            exit_code, stdout_text, stderr_text = run_process(
                command,
                cwd=repo_root,
                stdout_path=stdout_log,
                stderr_path=stderr_log,
                stdin_text=prompt,
            )
            success = exit_code == 0 and not has_usage_limit_error(stdout_text, stderr_text)
            detail = "Codex step completed successfully."
            if has_usage_limit_error(stdout_text, stderr_text):
                success = False
                detail = "Codex step stopped on a usage-limit / rate-limit style error."
            elif exit_code != 0:
                detail = f"Codex step failed with exit code {exit_code}."
        else:
            shell_command = lint_command if step.name == "lint" else test_command
            command = ["/bin/bash", "-lc", shell_command]
            exit_code, stdout_text, stderr_text = run_process(
                command,
                cwd=repo_root,
                stdout_path=stdout_log,
                stderr_path=stderr_log,
            )
            success = exit_code == 0 and not has_usage_limit_error(stdout_text, stderr_text)
            combined_output = "\n".join([stdout_text, stderr_text])
            detail = shell_detail_for_output(combined_output)
            if has_usage_limit_error(stdout_text, stderr_text):
                success = False
                detail = "Shell gate stopped on a usage-limit / rate-limit style error."
            if step.name == "full-regression":
                skip_counts = [
                    int(match.group(1))
                    for match in re.finditer(r"\b(\d+)\s+skipped\b", combined_output)
                ]
                if any(count > 0 for count in skip_counts):
                    success = False
                    detail = "Full regression reported skipped tests, which is treated as failure."
            if exit_code != 0 and success is False and "usage-limit" not in detail:
                detail = f"Shell gate failed with exit code {exit_code}. {detail}"

        finished_at = utc_now()
        result = StepResult(
            story=story_key,
            step=step.name,
            success=success,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            stdout_log=str(stdout_log.resolve()),
            stderr_log=str(stderr_log.resolve()),
            detail=detail,
        )
        step_results.append(result)
        manifest_payload["steps"].append(asdict(result))
        persist_manifest(manifest_path, manifest_payload)

        if not success:
            return False, detail, step_results

        if step.status_after is not None:
            update_sprint_story_status(status_file, story_key, step.status_after)
            upsert_story_file_status(story_file, step.status_after)

    return True, "story complete", step_results


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    status_file = args.status_file.resolve()
    if not status_file.exists():
        print(f"Status file not found: {status_file}", file=sys.stderr)
        return 2

    status_data = load_status_data(status_file)
    active_epic = detect_active_epic(status_data, args.epic)
    if active_epic is None:
        print("No active epic is marked in-progress. Waiting for human epic activation.")
        return 0

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = args.log_root.resolve() / run_id
    manifest_path = log_dir / "manifest.json"
    manifest_payload: dict[str, Any] = {
        "run_id": run_id,
        "repo_root": str(repo_root),
        "status_file": str(status_file),
        "active_epic": active_epic,
        "started_at": utc_now(),
        "stories_completed": [],
        "stories_failed": [],
        "steps": [],
    }
    persist_manifest(manifest_path, manifest_payload)

    processed = 0
    while True:
        status_data = load_status_data(status_file)
        story = next_story(status_data, active_epic, args.story)
        if story is None:
            print(
                f"All stories in {active_epic} are complete. "
                "Stopping intentionally and waiting for human retrospective / epic advancement."
            )
            manifest_payload["finished_at"] = utc_now()
            manifest_payload["result"] = "epic-story-queue-complete"
            persist_manifest(manifest_path, manifest_payload)
            return 0

        story_key, story_status = story
        success, detail, step_results = run_story_pipeline(
            repo_root=repo_root,
            log_dir=log_dir,
            story_key=story_key,
            story_status=story_status,
            status_file=status_file,
            codex_bin=args.codex_bin,
            model=args.model,
            lint_command=args.lint_command,
            test_command=args.test_command,
            dry_run=args.dry_run,
            manifest_path=manifest_path,
            manifest_payload=manifest_payload,
        )

        if not success:
            print(f"Story {story_key} failed: {detail}", file=sys.stderr)
            if step_results:
                last_step = step_results[-1]
                print(
                    f"Stopped at step {last_step.step}. "
                    f"See logs: {last_step.stdout_log} and {last_step.stderr_log}",
                    file=sys.stderr,
                )
            manifest_payload["stories_failed"].append({"story": story_key, "reason": detail})
            manifest_payload["finished_at"] = utc_now()
            manifest_payload["result"] = "failed"
            persist_manifest(manifest_path, manifest_payload)
            return 1

        if args.dry_run:
            print(f"Dry run finished for story {story_key}.")
        else:
            print(f"Story {story_key} completed successfully.")
        manifest_payload["stories_completed"].append(story_key)
        persist_manifest(manifest_path, manifest_payload)
        processed += 1

        if args.story is not None:
            print("Single-story run complete.")
            manifest_payload["finished_at"] = utc_now()
            manifest_payload["result"] = "single-story-complete"
            persist_manifest(manifest_path, manifest_payload)
            return 0

        if args.max_stories is not None and processed >= args.max_stories:
            print(f"Reached --max-stories={args.max_stories}; stopping.")
            manifest_payload["finished_at"] = utc_now()
            manifest_payload["result"] = "max-stories-reached"
            persist_manifest(manifest_path, manifest_payload)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())

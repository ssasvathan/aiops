from __future__ import annotations

from pathlib import Path

from scripts.bmad_sprint_runner import (
    detect_active_epic,
    has_usage_limit_error,
    load_status_data,
    next_story,
    pipeline_for_status,
    shell_detail_for_output,
    stories_for_epic,
    update_sprint_story_status,
    upsert_story_file_status,
)


def write_status_file(tmp_path: Path) -> Path:
    status_file = tmp_path / "sprint-status.yaml"
    status_file.write_text(
        "\n".join(
            [
                "# comment",
                "development_status:",
                "  epic-1: in-progress",
                "  1-1-alpha: done",
                "  1-2-beta: review",
                "  1-3-gamma: backlog",
                "  epic-1-retrospective: optional",
                "  epic-2: backlog",
                "  2-1-delta: backlog",
            ]
        ),
        encoding="utf-8",
    )
    return status_file


def test_detect_active_epic_and_next_story(tmp_path: Path) -> None:
    status_file = write_status_file(tmp_path)
    data = load_status_data(status_file)

    assert detect_active_epic(data, None) == "epic-1"
    assert stories_for_epic(data, "epic-1") == [
        ("1-1-alpha", "done"),
        ("1-2-beta", "review"),
        ("1-3-gamma", "backlog"),
    ]
    assert next_story(data, "epic-1", None) == ("1-2-beta", "review")


def test_pipeline_for_status_resumes_at_expected_step() -> None:
    assert [step.name for step in pipeline_for_status("backlog")] == [
        "bmad-bmm-create-story",
        "bmad-tea-testarch-atdd",
        "bmad-bmm-dev-story",
        "bmad-bmm-code-review",
        "bmad-tea-testarch-trace",
        "lint",
        "full-regression",
    ]
    assert [step.name for step in pipeline_for_status("review")] == [
        "bmad-bmm-code-review",
        "bmad-tea-testarch-trace",
        "lint",
        "full-regression",
    ]


def test_update_sprint_story_status_preserves_other_lines(tmp_path: Path) -> None:
    status_file = write_status_file(tmp_path)

    assert update_sprint_story_status(status_file, "1-2-beta", "done") is True

    text = status_file.read_text(encoding="utf-8")
    assert "# comment" in text
    assert "  1-2-beta: done" in text
    assert "  1-3-gamma: backlog" in text


def test_upsert_story_file_status_replaces_existing_line(tmp_path: Path) -> None:
    story_file = tmp_path / "story.md"
    story_file.write_text(
        "\n".join(
            [
                "# Story",
                "",
                "## Story Completion Status",
                "",
                "- Story status: `review`",
            ]
        ),
        encoding="utf-8",
    )

    assert upsert_story_file_status(story_file, "done") is True
    assert "- Story status: `done`" in story_file.read_text(encoding="utf-8")


def test_upsert_story_file_status_appends_section_when_missing(tmp_path: Path) -> None:
    story_file = tmp_path / "story.md"
    story_file.write_text("# Story\n", encoding="utf-8")

    assert upsert_story_file_status(story_file, "ready-for-dev") is True
    text = story_file.read_text(encoding="utf-8")
    assert "## Story Completion Status" in text
    assert "- Story status: `ready-for-dev`" in text


def test_usage_limit_and_skip_detection() -> None:
    assert has_usage_limit_error("429 rate limit exceeded") is True
    assert has_usage_limit_error("all good") is False
    assert "tests were skipped" in shell_detail_for_output("12 passed, 1 skipped")

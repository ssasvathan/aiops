"""ATDD fixture builders for Story 3.1 cold-path Kafka consumer runtime mode."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from aiops_triage_pipeline.models.health import HealthStatus


@dataclass(frozen=True)
class HealthTransition:
    component: str
    status: HealthStatus
    reason: str | None


class RecordingAsyncHealthRegistry:
    """Capture async health transitions emitted by runtime mode code."""

    def __init__(self) -> None:
        self.transitions: list[HealthTransition] = []

    async def update(
        self,
        component: str,
        status: HealthStatus,
        reason: str | None = None,
    ) -> None:
        self.transitions.append(
            HealthTransition(
                component=component,
                status=status,
                reason=reason,
            )
        )


def expected_consumer_binding() -> tuple[str, str]:
    """Canonical consumer group and topic for Story 3.1."""
    return ("aiops-cold-path-diagnosis", "aiops-case-header")


def build_cold_path_settings() -> SimpleNamespace:
    """Minimal runtime settings object for cold-path mode tests."""
    consumer_group, topic = expected_consumer_binding()
    return SimpleNamespace(
        APP_ENV=SimpleNamespace(value="dev"),
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
        KAFKA_CASE_HEADER_TOPIC=topic,
        KAFKA_COLD_PATH_CONSUMER_GROUP=consumer_group,
        KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS=1.0,
    )

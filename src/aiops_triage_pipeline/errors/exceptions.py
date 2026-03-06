"""Custom exception hierarchy for aiops-triage-pipeline."""


class PipelineError(Exception):
    """Base exception for all pipeline errors."""


# Critical path — halt pipeline (NFR-R2)
class InvariantViolation(PipelineError):
    """Invariant A/B2 broken — NEVER catch, always halt."""


class DenylistSanitizationError(InvariantViolation):
    """Denylist sanitization produced schema-invalid output at an output boundary."""

    def __init__(self, message: str, *, boundary_id: str, removed_field_count: int) -> None:
        super().__init__(message)
        self.boundary_id = boundary_id
        self.removed_field_count = removed_field_count


class PublishAfterDenylistError(PipelineError):
    """Publishing failed after denylist enforcement already ran."""

    def __init__(
        self,
        message: str,
        *,
        boundary_id: str,
        removed_field_count: int,
        error_code: str,
    ) -> None:
        super().__init__(message)
        self.boundary_id = boundary_id
        self.removed_field_count = removed_field_count
        self.error_code = error_code


class CriticalDependencyError(PipelineError):
    """Postgres/Object Storage down — pipeline halts with alerting."""


# Degradable — HealthRegistry update, continue with caps (NFR-R1)
class DegradableError(PipelineError):
    """Base for errors where pipeline can continue in degraded mode."""


class RedisUnavailable(DegradableError):
    """Redis down — pipeline continues with degraded-mode caps."""


class LLMUnavailable(DegradableError):
    """LLM endpoint unavailable — deterministic fallback activated."""


class SlackUnavailable(DegradableError):
    """Slack notification failed — logged, pipeline continues."""


# Integration errors
class IntegrationError(PipelineError):
    """PD/SN/Slack call failures — wraps built-in connection errors."""


class ObjectNotFoundError(IntegrationError):
    """Typed not-found integration error for explicit absence semantics."""

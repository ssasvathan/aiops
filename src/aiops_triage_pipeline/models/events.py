"""Internal operational event models for degraded-mode transitions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DegradedModeEvent(BaseModel, frozen=True):
    """Emitted when a component transitions to DEGRADED or UNAVAILABLE state.

    Used by:
    - Redis unavailability: action is capped to NOTIFY-only
    - Any DegradableError handler that transitions a component to degraded state

    Attributes:
        affected_scope: Component or subsystem that degraded (e.g., "redis", "llm")
        reason: Why the component degraded (e.g., "ConnectionRefusedError on port 6379")
        capped_action_level: Maximum action level now in effect (e.g., "NOTIFY-only")
        estimated_impact_window: Optional estimate of degradation duration (e.g., "unknown", "5m")
        timestamp: UTC time when the transition occurred
    """

    affected_scope: str
    reason: str
    capped_action_level: str
    estimated_impact_window: str | None = None
    timestamp: datetime


class TelemetryDegradedEvent(BaseModel, frozen=True):
    """Emitted when Prometheus becomes totally unavailable (FR67a).

    Used by:
    - Prometheus unavailability detection

    Attributes:
        affected_scope: Always "prometheus" for this event type
        reason: Why Prometheus is unavailable (e.g., "HTTP 503 after 3 retries")
        recovery_status: Current recovery state: "pending" | "resolved"
        timestamp: UTC time of the detection
    """

    event_type: Literal["TelemetryDegradedEvent"] = "TelemetryDegradedEvent"
    component: str = "scheduler"
    severity: Literal["info", "warning", "critical"] = "warning"
    affected_scope: Literal["prometheus"]
    reason: str
    recovery_status: Literal["pending", "resolved"]
    timestamp: datetime


class NotificationEvent(BaseModel, frozen=True):
    """Emitted (as a structured log event) when a postmortem obligation is dispatched (FR45).

    Used by:
    - Slack notification / structured log fallback for SOFT postmortem enforcement

    Attributes:
        event_type:           Discriminator field — always "NotificationEvent"
        case_id:              CaseFile identifier for audit traceability
        final_action:         The finalized action string (e.g., "PAGE", "NOTIFY")
        routing_key:          Topology ownership routing key
        support_channel:      Team support channel (may be None if not configured)
        postmortem_required:  Always True when this event is emitted (AC7 guard is upstream)
        reason_codes:         Reason codes that triggered the postmortem obligation
    """

    event_type: Literal["NotificationEvent"] = "NotificationEvent"
    case_id: str
    final_action: str
    routing_key: str
    support_channel: str | None
    postmortem_required: bool
    reason_codes: tuple[str, ...]

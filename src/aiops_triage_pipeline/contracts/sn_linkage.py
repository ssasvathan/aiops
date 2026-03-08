"""ServiceNowLinkageContractV1 — Phase 1B ServiceNow linkage and correlation contract."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_SNTextField = Literal["short_description", "description", "work_notes"]


class ServiceNowLinkageContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    enabled: bool = False
    incident_table: str = "incident"
    problem_table: str = "problem"
    pir_task_table: str = "problem_task"
    external_id_field: str = "external_id"
    tier1_correlation_fields: tuple[str, ...] = (
        "u_pagerduty_incident_id",
        "correlation_id",
        "u_correlation_id",
    )
    tier2_text_fields: tuple[_SNTextField, ...] = ("short_description", "description")
    tier2_include_work_notes: bool = False
    tier3_window_minutes: int = Field(default=120, ge=1, le=720)
    tier3_assignment_groups: tuple[str, ...] = ()
    live_timeout_seconds: float = Field(default=5.0, gt=0)
    max_results_per_tier: int = Field(default=25, ge=1, le=100)
    max_upsert_lookup_results: int = Field(default=5, ge=1, le=100)
    max_correlation_window_days: int = 7
    correlation_strategy: tuple[str, ...] = ("tier1", "tier2", "tier3")
    retry_window_minutes: int = Field(default=120, ge=1, le=720)
    retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    retry_max_seconds: int = Field(default=900, ge=1, le=86400)
    retry_jitter_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    transient_error_classifications: tuple[str, ...] = (
        "timeout",
        "connection_error",
        "http_429",
        "http_5xx",
    )
    mi_creation_allowed: bool = False

    @model_validator(mode="after")
    def _validate_linkage_config(self) -> "ServiceNowLinkageContractV1":
        if not self.incident_table.strip():
            raise ValueError("incident_table must be non-empty")
        if not self.problem_table.strip():
            raise ValueError("problem_table must be non-empty")
        if not self.pir_task_table.strip():
            raise ValueError("pir_task_table must be non-empty")
        if not self.external_id_field.strip():
            raise ValueError("external_id_field must be non-empty")
        if not self.tier1_correlation_fields:
            raise ValueError("tier1_correlation_fields must contain at least one field")
        if any(not field.strip() for field in self.tier1_correlation_fields):
            raise ValueError("tier1_correlation_fields cannot contain empty values")
        if self.tier2_include_work_notes and "work_notes" not in self.tier2_text_fields:
            raise ValueError(
                "tier2_include_work_notes=true requires 'work_notes' in tier2_text_fields"
            )
        if "tier1" not in self.correlation_strategy:
            raise ValueError("correlation_strategy must include tier1")
        if len(set(self.correlation_strategy)) != len(self.correlation_strategy):
            raise ValueError("correlation_strategy cannot contain duplicate tiers")
        allowed_tiers = {"tier1", "tier2", "tier3"}
        if any(tier not in allowed_tiers for tier in self.correlation_strategy):
            raise ValueError("correlation_strategy contains unsupported tier")
        if self.retry_base_seconds > self.retry_max_seconds:
            raise ValueError("retry_base_seconds must be <= retry_max_seconds")
        if any(
            not classification.strip()
            for classification in self.transient_error_classifications
        ):
            raise ValueError("transient_error_classifications cannot contain empty values")
        if len(set(self.transient_error_classifications)) != len(
            self.transient_error_classifications
        ):
            raise ValueError("transient_error_classifications cannot contain duplicates")
        tier_positions = {tier: idx for idx, tier in enumerate(self.correlation_strategy)}
        if (
            "tier1" in tier_positions
            and "tier2" in tier_positions
            and tier_positions["tier1"] > tier_positions["tier2"]
        ):
            raise ValueError("correlation_strategy must evaluate tier1 before tier2")
        if (
            "tier2" in tier_positions
            and "tier3" in tier_positions
            and tier_positions["tier2"] > tier_positions["tier3"]
        ):
            raise ValueError("correlation_strategy must evaluate tier2 before tier3")
        if self.problem_table == self.incident_table or self.pir_task_table == self.incident_table:
            raise ValueError("write tables must be distinct from incident_table")
        if not self.mi_creation_allowed:
            disallowed_tables = {
                "major_incident",
                "incident_major",
                "incident",
            }
            if self.problem_table.lower() in disallowed_tables:
                raise ValueError("problem_table cannot target major incident tables")
            if self.pir_task_table.lower() in disallowed_tables:
                raise ValueError("pir_task_table cannot target major incident tables")
        return self

"""Durable ServiceNow linkage retry-state schema."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, ValidationInfo, field_validator
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.engine import Connection, Engine

LINKAGE_RETRY_STATES: tuple[str, ...] = (
    "PENDING",
    "SEARCHING",
    "FAILED_TEMP",
    "LINKED",
    "FAILED_FINAL",
)
LinkageRetryState = Literal["PENDING", "SEARCHING", "FAILED_TEMP", "LINKED", "FAILED_FINAL"]
_NON_EMPTY = re.compile(r"\S")


class LinkageRetryRecordV1(BaseModel, frozen=True):
    """Durable retry-state record for ServiceNow linkage orchestration."""

    schema_version: Literal["v1"] = "v1"
    case_id: str = Field(min_length=1)
    pd_incident_id: str = Field(min_length=1)
    incident_sys_id: str | None = None
    state: LinkageRetryState
    attempt_count: int = Field(ge=0, default=0)
    retry_window_minutes: int = Field(ge=1)
    first_attempt_at: AwareDatetime
    updated_at: AwareDatetime
    deadline_at: AwareDatetime
    next_attempt_at: AwareDatetime | None = None
    request_id: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_retry_after_seconds: int | None = Field(default=None, ge=1)
    last_reason_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("incident_sys_id", "request_id", "last_error_code", "last_error_message")
    @classmethod
    def _validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional linkage fields must be non-empty when provided")
        return normalized

    @field_validator("updated_at")
    @classmethod
    def _validate_updated_at(cls, value: datetime, info: ValidationInfo) -> datetime:
        first_attempt_at = info.data.get("first_attempt_at")
        if first_attempt_at is not None and value < first_attempt_at:
            raise ValueError("updated_at must be >= first_attempt_at")
        return value

    @field_validator("deadline_at")
    @classmethod
    def _validate_deadline_at(cls, value: datetime, info: ValidationInfo) -> datetime:
        first_attempt_at = info.data.get("first_attempt_at")
        if first_attempt_at is not None and value < first_attempt_at:
            raise ValueError("deadline_at must be >= first_attempt_at")
        return value

    @field_validator("case_id", "pd_incident_id")
    @classmethod
    def _validate_non_blank_identifiers(cls, value: str) -> str:
        if not _NON_EMPTY.search(value):
            raise ValueError("identifier fields cannot be blank")
        return value


sn_linkage_retry_metadata = MetaData()
sn_linkage_retry_table = Table(
    "sn_linkage_retry",
    sn_linkage_retry_metadata,
    Column("case_id", String(255), primary_key=True),
    Column("pd_incident_id", String(255), nullable=False),
    Column("incident_sys_id", String(255), nullable=True),
    Column("state", String(32), nullable=False),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("retry_window_minutes", Integer, nullable=False),
    Column("first_attempt_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deadline_at", DateTime(timezone=True), nullable=False),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("request_id", String(64), nullable=True),
    Column("last_error_code", String(255), nullable=True),
    Column("last_error_message", Text, nullable=True),
    Column("last_retry_after_seconds", Integer, nullable=True),
    Column("last_reason_metadata", Text, nullable=False, default="{}"),
    CheckConstraint(
        "state IN ('PENDING', 'SEARCHING', 'FAILED_TEMP', 'LINKED', 'FAILED_FINAL')",
        name="ck_sn_linkage_retry_state",
    ),
    CheckConstraint("attempt_count >= 0", name="ck_sn_linkage_retry_attempt_non_negative"),
    CheckConstraint(
        "retry_window_minutes >= 1",
        name="ck_sn_linkage_retry_window_positive",
    ),
)
Index(
    "ix_sn_linkage_retry_state_next_attempt_at",
    sn_linkage_retry_table.c.state,
    sn_linkage_retry_table.c.next_attempt_at,
)
Index(
    "ix_sn_linkage_retry_state_updated_at",
    sn_linkage_retry_table.c.state,
    sn_linkage_retry_table.c.updated_at,
)


def create_sn_linkage_retry_table(bind: Engine | Connection) -> None:
    """Create the durable SN linkage retry table and indexes."""
    sn_linkage_retry_metadata.create_all(
        bind=bind,
        tables=[sn_linkage_retry_table],
        checkfirst=True,
    )

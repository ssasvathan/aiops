"""Outbox-ready handoff contracts for durable publish sequencing."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

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

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
OUTBOX_STATES: tuple[str, ...] = ("PENDING_OBJECT", "READY", "SENT", "RETRY", "DEAD")
OutboxState = Literal["PENDING_OBJECT", "READY", "SENT", "RETRY", "DEAD"]


class OutboxReadyCasefileV1(BaseModel, frozen=True):
    """Confirmed-write casefile metadata required before READY transition."""

    schema_version: Literal["v1"] = "v1"
    case_id: str = Field(min_length=1)
    object_path: str = Field(pattern=r"^cases/.+/triage\.json$")
    triage_hash: str

    @field_validator("triage_hash")
    @classmethod
    def _validate_triage_hash(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("triage_hash must be a 64-char lowercase SHA-256 hex string")
        return value


class OutboxRecordV1(BaseModel, frozen=True):
    """Minimal outbox record contract carrying READY-state durability metadata."""

    schema_version: Literal["v1"] = "v1"
    case_id: str = Field(min_length=1)
    status: OutboxState
    casefile_object_path: str = Field(pattern=r"^cases/.+/triage\.json$")
    triage_hash: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    delivery_attempts: int = Field(ge=0, default=0)
    next_attempt_at: AwareDatetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None

    @field_validator("triage_hash")
    @classmethod
    def _validate_outbox_triage_hash(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("triage_hash must be a 64-char lowercase SHA-256 hex string")
        return value

    @field_validator("updated_at")
    @classmethod
    def _validate_timestamp_order(cls, value: datetime, info: ValidationInfo) -> datetime:
        created_at = info.data.get("created_at")
        if created_at is not None and value < created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return value


outbox_metadata = MetaData()
outbox_table = Table(
    "outbox",
    outbox_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_id", String(255), nullable=False, unique=True),
    Column("casefile_object_path", String(1024), nullable=False),
    Column("triage_hash", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("delivery_attempts", Integer, nullable=False, default=0),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("last_error_code", String(255), nullable=True),
    Column("last_error_message", Text, nullable=True),
    CheckConstraint(
        "status IN ('PENDING_OBJECT', 'READY', 'SENT', 'RETRY', 'DEAD')",
        name="ck_outbox_status",
    ),
    CheckConstraint("delivery_attempts >= 0", name="ck_outbox_delivery_attempts_non_negative"),
)
Index(
    "ix_outbox_status_next_attempt_at",
    outbox_table.c.status,
    outbox_table.c.next_attempt_at,
)
Index(
    "ix_outbox_status_updated_at",
    outbox_table.c.status,
    outbox_table.c.updated_at,
)
Index(
    "ix_outbox_status_created_at",
    outbox_table.c.status,
    outbox_table.c.created_at,
)


def create_outbox_table(bind: Engine | Connection) -> None:
    """Create the durable outbox table and indexes using hand-rolled SQLAlchemy Core DDL."""
    outbox_metadata.create_all(bind=bind, tables=[outbox_table], checkfirst=True)

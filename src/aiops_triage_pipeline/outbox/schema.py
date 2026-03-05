"""Outbox-ready handoff contracts for durable publish sequencing."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, ValidationInfo, field_validator

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


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
    status: Literal["PENDING_OBJECT", "READY", "SENT", "RETRY", "DEAD"]
    casefile_object_path: str = Field(pattern=r"^cases/.+/triage\.json$")
    triage_hash: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    delivery_attempts: int = Field(ge=0, default=0)

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

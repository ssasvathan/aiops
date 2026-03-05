"""Outbox-ready handoff contracts for durable publish sequencing."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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

"""ServiceNowLinkageContractV1 — Phase 1B SN incident correlation contract (stub for Phase 1A)."""

from typing import Literal

from pydantic import BaseModel


class ServiceNowLinkageContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    enabled: bool = False
    max_correlation_window_days: int = 7
    correlation_strategy: tuple[str, ...] = ()
    mi_creation_allowed: bool = False

"""Shared enum types for aiops-triage-pipeline event contracts."""

from enum import Enum


class Environment(str, Enum):
    LOCAL = "local"
    HARNESS = "harness"
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"


class CriticalityTier(str, Enum):
    TIER_0 = "TIER_0"
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    UNKNOWN = "UNKNOWN"


class Action(str, Enum):
    OBSERVE = "OBSERVE"
    NOTIFY = "NOTIFY"
    TICKET = "TICKET"
    PAGE = "PAGE"


class EvidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    UNKNOWN = "UNKNOWN"  # Missing Prometheus series — NEVER treat as zero
    ABSENT = "ABSENT"
    STALE = "STALE"


class DiagnosisConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

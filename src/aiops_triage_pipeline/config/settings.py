import functools
import os
from enum import Enum
from pathlib import Path
from typing import TypeVar

import structlog
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Read APP_ENV BEFORE class definition to select the correct .env file.
# Direct env var takes precedence over any .env file value (K8s injection pattern).
_APP_ENV = os.getenv("APP_ENV", "local")


class AppEnv(str, Enum):
    local = "local"
    harness = "harness"
    dev = "dev"
    uat = "uat"
    prod = "prod"


class IntegrationMode(str, Enum):
    OFF = "OFF"
    LOG = "LOG"
    MOCK = "MOCK"
    LIVE = "LIVE"


# Maps APP_ENV to maximum allowed action — consumed by pipeline gate engine.
# Mirrors RulebookV1.caps.max_action_by_env from architecture decision 5D.
ENV_ACTION_CAPS: dict[str, str] = {
    "local": "OBSERVE",
    "harness": "OBSERVE",
    "dev": "NOTIFY",
    "uat": "TICKET",
    "prod": "PAGE",
}

T = TypeVar("T", bound=BaseModel)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f"config/.env.{_APP_ENV}",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars (process environment has many unrelated vars)
    )

    # Environment identification
    APP_ENV: AppEnv = AppEnv.local

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_KERBEROS_KEYTAB_PATH: str | None = None
    KRB5_CONF_PATH: str | None = None
    KAFKA_CASE_HEADER_TOPIC: str = "aiops-case-header"
    KAFKA_TRIAGE_EXCERPT_TOPIC: str = "aiops-triage-excerpt"

    # Cold-path consumer
    KAFKA_COLD_PATH_CONSUMER_GROUP: str = "aiops-cold-path-diagnosis"
    KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS: float = 1.0

    # Postgres
    DATABASE_URL: str = "postgresql+psycopg://aiops:aiops@localhost:5432/aiops"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (S3/MinIO)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "aiops-cases"

    # PagerDuty Events V2 service integration key (required for LIVE mode)
    PD_ROUTING_KEY: str | None = None

    # Slack incoming-webhook URL (required for LIVE mode; never logged)
    SLACK_WEBHOOK_URL: str | None = None

    # Integration modes — default LOG to prevent accidental outbound calls
    INTEGRATION_MODE_PD: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SLACK: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SN: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_LLM: IntegrationMode = IntegrationMode.LOG

    # LLM endpoint (required for LIVE mode)
    LLM_BASE_URL: str | None = None  # Bank-sanctioned LLM endpoint base URL (LIVE mode)
    LLM_API_KEY: str | None = None  # Bearer auth token for LLM endpoint (optional in LIVE mode)
    OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS: float = 5.0
    OUTBOX_PUBLISHER_BATCH_SIZE: int = 100
    CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS: float = 3600.0
    CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE: int = 500
    CASEFILE_LIFECYCLE_LIST_PAGE_SIZE: int = 500
    CASEFILE_RETENTION_GOVERNANCE_APPROVAL: str | None = None

    # OTLP metrics export
    # Hot-path scheduler
    PROMETHEUS_URL: str = "http://localhost:9090"
    HOT_PATH_SCHEDULER_INTERVAL_SECONDS: int = 300
    DISTRIBUTED_CYCLE_LOCK_ENABLED: bool = False
    CYCLE_LOCK_MARGIN_SECONDS: int = 60

    # Shard coordination (Story 4.2) — disabled by default for incremental rollout
    # SHARD_LEASE_TTL_SECONDS must be < HOT_PATH_SCHEDULER_INTERVAL_SECONDS so that a
    # pod's NX lease expires before the next cycle, allowing clean per-cycle re-acquisition.
    SHARD_REGISTRY_ENABLED: bool = False
    SHARD_COORDINATION_SHARD_COUNT: int = 4
    SHARD_LEASE_TTL_SECONDS: int = 270  # default < 300 (interval) for clean NX re-acquire
    SHARD_CHECKPOINT_TTL_SECONDS: int = 660
    TOPOLOGY_REGISTRY_PATH: str = "config/topology-registry.yaml"
    STAGE2_SUSTAINED_PARALLEL_MIN_KEYS: int = 64
    STAGE2_SUSTAINED_PARALLEL_WORKERS: int = 4
    STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE: int = 32
    STAGE2_PEAK_HISTORY_MAX_DEPTH: int = 12
    STAGE2_PEAK_HISTORY_MAX_SCOPES: int = 2000
    STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES: int = 3

    OTLP_METRICS_ENDPOINT: str | None = None
    OTLP_METRICS_PROTOCOL: str = "http/protobuf"  # allowed: "http/protobuf", "grpc"
    OTLP_METRICS_HEADERS: str | None = None
    OTLP_METRICS_EXPORT_INTERVAL_MILLIS: int = 60000
    OTLP_METRICS_TIMEOUT_MILLIS: int = 10000
    OTLP_SERVICE_NAME: str = "aiops-triage-pipeline"
    OTLP_SERVICE_VERSION: str = "0.1.0"
    OTLP_DEPLOYMENT_ENVIRONMENT: str | None = None

    @property
    def max_action(self) -> str:
        """Maximum allowed action for this environment (architecture decision 5D)."""
        return ENV_ACTION_CAPS.get(self.APP_ENV.value, "OBSERVE")

    @model_validator(mode="after")
    def validate_llm_prod_mode(self) -> "Settings":
        """Reject MOCK and OFF for INTEGRATION_MODE_LLM in prod — requires LIVE (or LOG)."""
        if self.APP_ENV == AppEnv.prod and self.INTEGRATION_MODE_LLM in (
            IntegrationMode.OFF,
            IntegrationMode.MOCK,
        ):
            raise ValueError(
                f"INTEGRATION_MODE_LLM must be LIVE or LOG in prod environment; "
                f"got {self.INTEGRATION_MODE_LLM.value}"
            )
        return self

    @model_validator(mode="after")
    def validate_critical_integrations_prod_mode(self) -> "Settings":
        """Reject MOCK and OFF for PD, Slack, SN in prod — each requires LIVE (or LOG)."""
        if self.APP_ENV != AppEnv.prod:
            return self
        _critical: list[tuple[str, IntegrationMode]] = [
            ("INTEGRATION_MODE_PD", self.INTEGRATION_MODE_PD),
            ("INTEGRATION_MODE_SLACK", self.INTEGRATION_MODE_SLACK),
            ("INTEGRATION_MODE_SN", self.INTEGRATION_MODE_SN),
        ]
        for field_name, mode in _critical:
            if mode in (IntegrationMode.OFF, IntegrationMode.MOCK):
                raise ValueError(
                    f"{field_name} must be LIVE or LOG in prod environment; "
                    f"got {mode.value}"
                )
        return self

    @model_validator(mode="after")
    def validate_kerberos_files(self) -> "Settings":
        """Fail-fast at boot if SASL_SSL is configured but Kerberos files are missing."""
        if self.KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
            if not self.KAFKA_KERBEROS_KEYTAB_PATH:
                raise ValueError(
                    "KAFKA_KERBEROS_KEYTAB_PATH is required when KAFKA_SECURITY_PROTOCOL=SASL_SSL"
                )
            if not Path(self.KAFKA_KERBEROS_KEYTAB_PATH).exists():
                raise ValueError(
                    f"Kerberos keytab file not found: {self.KAFKA_KERBEROS_KEYTAB_PATH}"
                )
            if not self.KRB5_CONF_PATH:
                raise ValueError(
                    "KRB5_CONF_PATH is required when KAFKA_SECURITY_PROTOCOL=SASL_SSL"
                )
            if not Path(self.KRB5_CONF_PATH).exists():
                raise ValueError(f"KRB5 config file not found: {self.KRB5_CONF_PATH}")
        if not self.KAFKA_COLD_PATH_CONSUMER_GROUP.strip():
            raise ValueError("KAFKA_COLD_PATH_CONSUMER_GROUP must be a non-empty string")
        if self.KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS <= 0:
            raise ValueError("KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS must be > 0")
        if self.CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS <= 0:
            raise ValueError("CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS must be > 0")
        if not 1 <= self.CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE <= 1000:
            raise ValueError("CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE must be between 1 and 1000")
        if not 1 <= self.CASEFILE_LIFECYCLE_LIST_PAGE_SIZE <= 1000:
            raise ValueError("CASEFILE_LIFECYCLE_LIST_PAGE_SIZE must be between 1 and 1000")
        if self.OTLP_METRICS_PROTOCOL not in {"http/protobuf", "grpc"}:
            raise ValueError(
                "OTLP_METRICS_PROTOCOL must be 'http/protobuf' or 'grpc'"
            )
        if self.HOT_PATH_SCHEDULER_INTERVAL_SECONDS <= 0:
            raise ValueError("HOT_PATH_SCHEDULER_INTERVAL_SECONDS must be > 0")
        if self.CYCLE_LOCK_MARGIN_SECONDS <= 0:
            raise ValueError("CYCLE_LOCK_MARGIN_SECONDS must be > 0")
        self.TOPOLOGY_REGISTRY_PATH = self.TOPOLOGY_REGISTRY_PATH.strip()
        if not self.TOPOLOGY_REGISTRY_PATH:
            raise ValueError("TOPOLOGY_REGISTRY_PATH must be a non-empty path")
        if self.STAGE2_SUSTAINED_PARALLEL_MIN_KEYS <= 0:
            raise ValueError("STAGE2_SUSTAINED_PARALLEL_MIN_KEYS must be > 0")
        if self.STAGE2_SUSTAINED_PARALLEL_WORKERS <= 0:
            raise ValueError("STAGE2_SUSTAINED_PARALLEL_WORKERS must be > 0")
        if self.STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE <= 0:
            raise ValueError("STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE must be > 0")
        if self.STAGE2_PEAK_HISTORY_MAX_DEPTH <= 0:
            raise ValueError("STAGE2_PEAK_HISTORY_MAX_DEPTH must be > 0")
        if self.STAGE2_PEAK_HISTORY_MAX_SCOPES <= 0:
            raise ValueError("STAGE2_PEAK_HISTORY_MAX_SCOPES must be > 0")
        if self.STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES <= 0:
            raise ValueError("STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES must be > 0")
        if self.SHARD_COORDINATION_SHARD_COUNT <= 0:
            raise ValueError("SHARD_COORDINATION_SHARD_COUNT must be > 0")
        if self.SHARD_LEASE_TTL_SECONDS <= 0:
            raise ValueError("SHARD_LEASE_TTL_SECONDS must be > 0")
        if self.SHARD_CHECKPOINT_TTL_SECONDS <= 0:
            raise ValueError("SHARD_CHECKPOINT_TTL_SECONDS must be > 0")
        if self.OTLP_METRICS_EXPORT_INTERVAL_MILLIS <= 0:
            raise ValueError("OTLP_METRICS_EXPORT_INTERVAL_MILLIS must be > 0")
        if self.OTLP_METRICS_TIMEOUT_MILLIS <= 0:
            raise ValueError("OTLP_METRICS_TIMEOUT_MILLIS must be > 0")
        if self.OTLP_DEPLOYMENT_ENVIRONMENT is None or self.OTLP_DEPLOYMENT_ENVIRONMENT == "":
            self.OTLP_DEPLOYMENT_ENVIRONMENT = self.APP_ENV.value
        return self

    def log_active_config(self, logger: structlog.BoundLogger) -> None:
        """Log active configuration at startup (NFR-O4). Masks secret values."""
        logger.info(
            "active_configuration",
            APP_ENV=self.APP_ENV.value,
            KAFKA_BOOTSTRAP_SERVERS=self.KAFKA_BOOTSTRAP_SERVERS,
            KAFKA_SECURITY_PROTOCOL=self.KAFKA_SECURITY_PROTOCOL,
            KAFKA_COLD_PATH_CONSUMER_GROUP=self.KAFKA_COLD_PATH_CONSUMER_GROUP,
            KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS=self.KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS,
            DATABASE_URL=self._mask_url(self.DATABASE_URL),
            REDIS_URL=self._mask_url(self.REDIS_URL),
            S3_ENDPOINT_URL=self.S3_ENDPOINT_URL,
            S3_ACCESS_KEY="[REDACTED]",
            S3_SECRET_KEY="[REDACTED]",
            S3_BUCKET=self.S3_BUCKET,
            PD_ROUTING_KEY="[CONFIGURED]" if self.PD_ROUTING_KEY else "[NOT SET]",
            SLACK_WEBHOOK_URL="[CONFIGURED]" if self.SLACK_WEBHOOK_URL else "[NOT SET]",
            INTEGRATION_MODE_PD=self.INTEGRATION_MODE_PD.value,
            INTEGRATION_MODE_SLACK=self.INTEGRATION_MODE_SLACK.value,
            INTEGRATION_MODE_SN=self.INTEGRATION_MODE_SN.value,
            INTEGRATION_MODE_LLM=self.INTEGRATION_MODE_LLM.value,
            LLM_BASE_URL=self.LLM_BASE_URL or "[NOT SET]",
            LLM_API_KEY="[CONFIGURED]" if self.LLM_API_KEY else "[NOT SET]",
            OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS=self.OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS,
            OUTBOX_PUBLISHER_BATCH_SIZE=self.OUTBOX_PUBLISHER_BATCH_SIZE,
            CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS=self.CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS,
            CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE=self.CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE,
            CASEFILE_LIFECYCLE_LIST_PAGE_SIZE=self.CASEFILE_LIFECYCLE_LIST_PAGE_SIZE,
            CASEFILE_RETENTION_GOVERNANCE_APPROVAL=self.CASEFILE_RETENTION_GOVERNANCE_APPROVAL,
            PROMETHEUS_URL=self.PROMETHEUS_URL,
            HOT_PATH_SCHEDULER_INTERVAL_SECONDS=self.HOT_PATH_SCHEDULER_INTERVAL_SECONDS,
            DISTRIBUTED_CYCLE_LOCK_ENABLED=self.DISTRIBUTED_CYCLE_LOCK_ENABLED,
            CYCLE_LOCK_MARGIN_SECONDS=self.CYCLE_LOCK_MARGIN_SECONDS,
            SHARD_REGISTRY_ENABLED=self.SHARD_REGISTRY_ENABLED,
            SHARD_COORDINATION_SHARD_COUNT=self.SHARD_COORDINATION_SHARD_COUNT,
            SHARD_LEASE_TTL_SECONDS=self.SHARD_LEASE_TTL_SECONDS,
            SHARD_CHECKPOINT_TTL_SECONDS=self.SHARD_CHECKPOINT_TTL_SECONDS,
            TOPOLOGY_REGISTRY_PATH=self.TOPOLOGY_REGISTRY_PATH,
            STAGE2_SUSTAINED_PARALLEL_MIN_KEYS=self.STAGE2_SUSTAINED_PARALLEL_MIN_KEYS,
            STAGE2_SUSTAINED_PARALLEL_WORKERS=self.STAGE2_SUSTAINED_PARALLEL_WORKERS,
            STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE=self.STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE,
            STAGE2_PEAK_HISTORY_MAX_DEPTH=self.STAGE2_PEAK_HISTORY_MAX_DEPTH,
            STAGE2_PEAK_HISTORY_MAX_SCOPES=self.STAGE2_PEAK_HISTORY_MAX_SCOPES,
            STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES=self.STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES,
            OTLP_METRICS_ENDPOINT=self.OTLP_METRICS_ENDPOINT or "[NOT SET]",
            OTLP_METRICS_PROTOCOL=self.OTLP_METRICS_PROTOCOL,
            OTLP_METRICS_HEADERS=(
                "[CONFIGURED]" if self.OTLP_METRICS_HEADERS else "[NOT SET]"
            ),
            OTLP_METRICS_EXPORT_INTERVAL_MILLIS=self.OTLP_METRICS_EXPORT_INTERVAL_MILLIS,
            OTLP_METRICS_TIMEOUT_MILLIS=self.OTLP_METRICS_TIMEOUT_MILLIS,
            OTLP_SERVICE_NAME=self.OTLP_SERVICE_NAME,
            OTLP_SERVICE_VERSION=self.OTLP_SERVICE_VERSION,
            OTLP_DEPLOYMENT_ENVIRONMENT=self.OTLP_DEPLOYMENT_ENVIRONMENT,
            max_action=self.max_action,
        )

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in a connection URL for safe logging."""
        # postgresql+psycopg://user:password@host:port/db → postgresql+psycopg://user:***@host:port/db
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                credentials, host_part = rest.rsplit("@", 1)
                if ":" in credentials:
                    user, _ = credentials.split(":", 1)
                    return f"{scheme}://{user}:***@{host_part}"
        return url


@functools.cache
def get_settings() -> Settings:
    """Return the singleton Settings instance. Cached after first call.

    For testing, call get_settings.cache_clear() between tests to reset state.
    """
    return Settings()


def load_policy_yaml(path: Path, model_class: type[T]) -> T:
    """Load a YAML policy file and validate it as a frozen Pydantic model.

    Used by pipeline stages to load policy contracts at startup:
        rulebook = load_policy_yaml(Path("config/policies/rulebook-v1.yaml"), RulebookV1)

    config/ is a leaf package — do NOT import specific contract classes here.
    Callers supply the model_class.
    """
    import yaml  # Lazy import — only loaded when policy loading is requested

    try:
        raw = yaml.safe_load(path.read_text())
        return model_class.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Failed to load {model_class.__name__} from {path}: {e}") from e

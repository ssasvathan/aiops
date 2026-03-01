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
    dev = "dev"
    uat = "uat"
    prod = "prod"


class IntegrationMode(str, Enum):
    OFF = "OFF"
    LOG = "LOG"
    MOCK = "MOCK"
    LIVE = "LIVE"


# Maps APP_ENV to maximum allowed action — consumed by pipeline gate engine (Story 5.1).
# Mirrors RulebookV1.caps.max_action_by_env from architecture decision 5D.
ENV_ACTION_CAPS: dict[str, str] = {
    "local": "OBSERVE",
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

    # Postgres
    DATABASE_URL: str = "postgresql+psycopg://aiops:aiops@localhost:5432/aiops"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (S3/MinIO)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "aiops-cases"

    # Integration modes — default LOG to prevent accidental outbound calls
    INTEGRATION_MODE_PD: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SLACK: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SN: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_LLM: IntegrationMode = IntegrationMode.LOG

    @property
    def max_action(self) -> str:
        """Maximum allowed action for this environment (architecture decision 5D)."""
        return ENV_ACTION_CAPS.get(self.APP_ENV.value, "OBSERVE")

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
        return self

    def log_active_config(self, logger: structlog.BoundLogger) -> None:
        """Log active configuration at startup (NFR-O4). Masks secret values."""
        logger.info(
            "active_configuration",
            APP_ENV=self.APP_ENV.value,
            KAFKA_BOOTSTRAP_SERVERS=self.KAFKA_BOOTSTRAP_SERVERS,
            KAFKA_SECURITY_PROTOCOL=self.KAFKA_SECURITY_PROTOCOL,
            DATABASE_URL=self._mask_url(self.DATABASE_URL),
            REDIS_URL=self._mask_url(self.REDIS_URL),
            S3_ENDPOINT_URL=self.S3_ENDPOINT_URL,
            S3_ACCESS_KEY="[REDACTED]",
            S3_SECRET_KEY="[REDACTED]",
            S3_BUCKET=self.S3_BUCKET,
            INTEGRATION_MODE_PD=self.INTEGRATION_MODE_PD.value,
            INTEGRATION_MODE_SLACK=self.INTEGRATION_MODE_SLACK.value,
            INTEGRATION_MODE_SN=self.INTEGRATION_MODE_SN.value,
            INTEGRATION_MODE_LLM=self.INTEGRATION_MODE_LLM.value,
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

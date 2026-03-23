from pathlib import Path

import pytest
import structlog
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import (
    AppEnv,
    IntegrationMode,
    Settings,
    get_settings,
    load_policy_yaml,
)


def test_integration_mode_default() -> None:
    """INTEGRATION_MODE_PD defaults to LOG when not set in environment."""
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.INTEGRATION_MODE_PD == IntegrationMode.LOG
    assert settings.INTEGRATION_MODE_LLM == IntegrationMode.LOG


def test_integration_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct env var INTEGRATION_MODE_PD=MOCK overrides default LOG."""
    monkeypatch.setenv("INTEGRATION_MODE_PD", "MOCK")
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.INTEGRATION_MODE_PD == IntegrationMode.MOCK


def test_max_action_for_all_environments() -> None:
    """max_action returns correct cap per APP_ENV value."""
    for env_value, expected in [
        ("local", "OBSERVE"),
        ("dev", "NOTIFY"),
        ("uat", "TICKET"),
        ("prod", "PAGE"),
    ]:
        settings = Settings(
            _env_file=None,
            APP_ENV=env_value,
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
        )
        assert settings.max_action == expected, f"APP_ENV={env_value}"


def test_kerberos_plaintext_no_error() -> None:
    """KAFKA_SECURITY_PROTOCOL=PLAINTEXT does not trigger Kerberos validation."""
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_SECURITY_PROTOCOL="PLAINTEXT",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.KAFKA_SECURITY_PROTOCOL == "PLAINTEXT"


def test_kerberos_sasl_ssl_missing_keytab_raises(tmp_path: Path) -> None:
    """SASL_SSL with non-existent keytab path raises ValueError at boot."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="kafka.internal:9092",
            KAFKA_SECURITY_PROTOCOL="SASL_SSL",
            KAFKA_KERBEROS_KEYTAB_PATH=str(tmp_path / "nonexistent.keytab"),
            KRB5_CONF_PATH=str(tmp_path / "krb5.conf"),
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
        )


def test_kerberos_sasl_ssl_missing_krb5_conf_raises(tmp_path: Path) -> None:
    """SASL_SSL with existing keytab but non-existent KRB5_CONF_PATH raises ValueError."""
    keytab = tmp_path / "service.keytab"
    keytab.write_bytes(b"dummy keytab content")
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="kafka.internal:9092",
            KAFKA_SECURITY_PROTOCOL="SASL_SSL",
            KAFKA_KERBEROS_KEYTAB_PATH=str(keytab),
            KRB5_CONF_PATH=str(tmp_path / "nonexistent_krb5.conf"),
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
        )


def test_kerberos_sasl_ssl_with_valid_files_succeeds(tmp_path: Path) -> None:
    """SASL_SSL with existing keytab and KRB5 files creates Settings successfully."""
    keytab = tmp_path / "service.keytab"
    krb5_conf = tmp_path / "krb5.conf"
    keytab.write_bytes(b"dummy keytab content")
    krb5_conf.write_text("[libdefaults]\n    default_realm = TEST.INTERNAL\n")

    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="kafka.internal:9092",
        KAFKA_SECURITY_PROTOCOL="SASL_SSL",
        KAFKA_KERBEROS_KEYTAB_PATH=str(keytab),
        KRB5_CONF_PATH=str(krb5_conf),
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.KAFKA_SECURITY_PROTOCOL == "SASL_SSL"


def test_log_active_config_masks_secret() -> None:
    """log_active_config masks S3_SECRET_KEY, S3_ACCESS_KEY, and URL passwords."""
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:secret_password@localhost/db",
        REDIS_URL="redis://:redis_password@localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="access_key_id",
        S3_SECRET_KEY="super_secret",
        S3_BUCKET="bucket",
        OTLP_METRICS_HEADERS="Authorization=Api-Token abc123",
    )
    with structlog.testing.capture_logs() as cap_logs:
        settings.log_active_config(structlog.get_logger())

    assert len(cap_logs) == 1
    event = cap_logs[0]
    assert event.get("S3_SECRET_KEY") == "[REDACTED]"
    assert event.get("S3_ACCESS_KEY") == "[REDACTED]"
    assert event.get("OTLP_METRICS_HEADERS") == "[CONFIGURED]"
    assert "super_secret" not in str(cap_logs)
    assert "secret_password" not in str(cap_logs)
    assert "redis_password" not in str(cap_logs)
    assert "access_key_id" not in str(cap_logs)
    assert "abc123" not in str(cap_logs)


def test_otlp_protocol_validation_rejects_invalid_value() -> None:
    with pytest.raises((ValueError, ValidationError), match="OTLP_METRICS_PROTOCOL"):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
            OTLP_METRICS_PROTOCOL="udp",
        )


def test_otlp_deployment_environment_defaults_to_app_env() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="uat",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
        OTLP_DEPLOYMENT_ENVIRONMENT="",
    )
    assert settings.OTLP_DEPLOYMENT_ENVIRONMENT == "uat"


def test_stage2_parallel_and_retention_settings_have_safe_defaults() -> None:
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )

    assert settings.STAGE2_SUSTAINED_PARALLEL_MIN_KEYS > 0
    assert settings.STAGE2_SUSTAINED_PARALLEL_WORKERS > 0
    assert settings.STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE > 0
    assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH > 0
    assert settings.STAGE2_PEAK_HISTORY_MAX_SCOPES > 0
    assert settings.STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES > 0
    assert settings.DISTRIBUTED_CYCLE_LOCK_ENABLED is False
    assert settings.CYCLE_LOCK_MARGIN_SECONDS > 0


def test_stage2_parallel_and_retention_settings_reject_invalid_values() -> None:
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
            STAGE2_SUSTAINED_PARALLEL_WORKERS=0,
        )


def test_cycle_lock_margin_rejects_non_positive_values() -> None:
    with pytest.raises((ValueError, ValidationError), match="CYCLE_LOCK_MARGIN_SECONDS"):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
            CYCLE_LOCK_MARGIN_SECONDS=0,
        )


def test_get_settings_returns_same_instance() -> None:
    """get_settings() caches and returns the same Settings instance."""
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()


_PROD_SETTINGS_BASE: dict = dict(
    _env_file=None,
    APP_ENV="prod",
    KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    DATABASE_URL="postgresql+psycopg://u:p@h/db",
    REDIS_URL="redis://localhost:6379/0",
    S3_ENDPOINT_URL="http://localhost:9000",
    S3_ACCESS_KEY="key",
    S3_SECRET_KEY="secret",
    S3_BUCKET="bucket",
)


def test_prod_llm_mock_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_LLM=MOCK raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_LLM"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_LLM": "MOCK"})


def test_prod_llm_off_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_LLM=OFF raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_LLM"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_LLM": "OFF"})


def test_prod_llm_live_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_LLM=LIVE creates Settings successfully."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_LLM": "LIVE"})
    assert settings.INTEGRATION_MODE_LLM.value == "LIVE"
    assert settings.APP_ENV.value == "prod"


def test_prod_llm_log_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_LLM=LOG is allowed (safe non-destructive default)."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_LLM": "LOG"})
    assert settings.INTEGRATION_MODE_LLM.value == "LOG"
    assert settings.APP_ENV.value == "prod"


def test_local_llm_mock_succeeds() -> None:
    """APP_ENV=local + INTEGRATION_MODE_LLM=MOCK is allowed (non-prod environment)."""
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        APP_ENV="local",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
        INTEGRATION_MODE_LLM="MOCK",
    )
    assert settings.INTEGRATION_MODE_LLM.value == "MOCK"
    assert settings.APP_ENV.value == "local"


def test_load_policy_yaml_happy_path(tmp_path: Path) -> None:
    """load_policy_yaml loads YAML and validates it against a Pydantic model."""
    from pydantic import BaseModel

    class _Policy(BaseModel):
        name: str
        version: int

    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("name: test-policy\nversion: 1\n")

    result = load_policy_yaml(policy_file, _Policy)
    assert result.name == "test-policy"
    assert result.version == 1


def test_load_policy_yaml_file_not_found(tmp_path: Path) -> None:
    """load_policy_yaml raises ValueError with file path context when file is missing."""
    from pydantic import BaseModel

    class _Policy(BaseModel):
        name: str

    with pytest.raises(ValueError, match="nonexistent.yaml"):
        load_policy_yaml(tmp_path / "nonexistent.yaml", _Policy)


def test_load_policy_yaml_schema_mismatch(tmp_path: Path) -> None:
    """load_policy_yaml raises ValueError with model name context on schema mismatch."""
    from pydantic import BaseModel

    class _Policy(BaseModel):
        name: str
        version: int  # required field

    policy_file = tmp_path / "bad_policy.yaml"
    policy_file.write_text("name: test-policy\n")  # 'version' field missing

    with pytest.raises(ValueError, match="_Policy"):
        load_policy_yaml(policy_file, _Policy)


def _base_settings_kwargs() -> dict:
    """Minimal keyword arguments for constructing a valid Settings object in tests."""
    return {
        "_env_file": None,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "bucket",
    }


def test_shard_coordination_defaults_to_disabled() -> None:
    """SHARD_REGISTRY_ENABLED defaults to False and shard parameters have safe positive defaults."""
    settings = Settings(**_base_settings_kwargs())
    assert settings.SHARD_REGISTRY_ENABLED is False
    assert settings.SHARD_COORDINATION_SHARD_COUNT > 0
    assert settings.SHARD_LEASE_TTL_SECONDS > 0
    assert settings.SHARD_CHECKPOINT_TTL_SECONDS > 0


def test_shard_coordination_shard_count_rejects_zero() -> None:
    """SHARD_COORDINATION_SHARD_COUNT=0 raises a validation error."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(**{**_base_settings_kwargs(), "SHARD_COORDINATION_SHARD_COUNT": 0})


def test_shard_lease_ttl_seconds_rejects_zero() -> None:
    """SHARD_LEASE_TTL_SECONDS=0 raises a validation error."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(**{**_base_settings_kwargs(), "SHARD_LEASE_TTL_SECONDS": 0})


def test_shard_checkpoint_ttl_seconds_rejects_zero() -> None:
    """SHARD_CHECKPOINT_TTL_SECONDS=0 raises a validation error."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(**{**_base_settings_kwargs(), "SHARD_CHECKPOINT_TTL_SECONDS": 0})


def test_kafka_cold_path_consumer_group_default_is_non_empty() -> None:
    """KAFKA_COLD_PATH_CONSUMER_GROUP defaults to canonical non-empty value."""
    settings = Settings(**_base_settings_kwargs())
    assert settings.KAFKA_COLD_PATH_CONSUMER_GROUP == "aiops-cold-path-diagnosis"


def test_kafka_cold_path_consumer_group_empty_raises() -> None:
    """KAFKA_COLD_PATH_CONSUMER_GROUP cannot be an empty string."""
    with pytest.raises((ValueError, Exception), match="KAFKA_COLD_PATH_CONSUMER_GROUP"):
        Settings(**{**_base_settings_kwargs(), "KAFKA_COLD_PATH_CONSUMER_GROUP": ""})


def test_kafka_cold_path_consumer_group_whitespace_raises() -> None:
    """KAFKA_COLD_PATH_CONSUMER_GROUP cannot be a whitespace-only string."""
    with pytest.raises((ValueError, Exception), match="KAFKA_COLD_PATH_CONSUMER_GROUP"):
        Settings(**{**_base_settings_kwargs(), "KAFKA_COLD_PATH_CONSUMER_GROUP": "   "})


def test_log_active_config_includes_shard_registry_enabled() -> None:
    """log_active_config includes SHARD_REGISTRY_ENABLED for full coordination state visibility."""
    settings = Settings(**_base_settings_kwargs())
    with structlog.testing.capture_logs() as cap_logs:
        settings.log_active_config(structlog.get_logger())

    assert len(cap_logs) == 1
    event = cap_logs[0]
    assert "SHARD_REGISTRY_ENABLED" in event, (
        "SHARD_REGISTRY_ENABLED must appear in log_active_config output"
    )
    assert event["SHARD_REGISTRY_ENABLED"] is False  # default value
    assert "DISTRIBUTED_CYCLE_LOCK_ENABLED" in event, (
        "Both coordination flags must be logged together"
    )


def test_env_file_selection_uses_app_env() -> None:
    """APP_ENV=dev resolves to AppEnv.dev and max_action returns NOTIFY (FR50 precedence)."""
    settings = Settings(
        APP_ENV="dev",
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.APP_ENV == AppEnv.dev
    assert settings.max_action == "NOTIFY"

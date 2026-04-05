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
    for env_value, expected, depth, lease_ttl in [
        ("local", "OBSERVE", 12, 270),
        ("dev", "NOTIFY", 2016, 250),
        ("uat", "TICKET", 4320, 294),
        ("prod", "PAGE", 8640, 294),
    ]:
        settings = Settings(
            _env_file=None,
            APP_ENV=env_value,
            STAGE2_PEAK_HISTORY_MAX_DEPTH=depth,
            SHARD_LEASE_TTL_SECONDS=lease_ttl,
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
        STAGE2_PEAK_HISTORY_MAX_DEPTH=4320,
        SHARD_LEASE_TTL_SECONDS=294,
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
    STAGE2_PEAK_HISTORY_MAX_DEPTH=8640,
    SHARD_LEASE_TTL_SECONDS=294,
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
        "SHARD_LEASE_TTL_SECONDS": 250,
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


def test_prod_pd_mock_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=MOCK raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "MOCK"})


def test_prod_pd_off_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=OFF raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "OFF"})


def test_prod_pd_live_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=LIVE creates Settings successfully."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "LIVE"})
    assert settings.INTEGRATION_MODE_PD.value == "LIVE"
    assert settings.APP_ENV.value == "prod"


def test_prod_pd_log_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=LOG is allowed (safe non-destructive default)."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "LOG"})
    assert settings.INTEGRATION_MODE_PD.value == "LOG"
    assert settings.APP_ENV.value == "prod"


def test_prod_slack_mock_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SLACK=MOCK raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_SLACK"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SLACK": "MOCK"})


def test_prod_slack_off_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SLACK=OFF raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_SLACK"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SLACK": "OFF"})


def test_prod_slack_live_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SLACK=LIVE creates Settings successfully."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SLACK": "LIVE"})
    assert settings.INTEGRATION_MODE_SLACK.value == "LIVE"
    assert settings.APP_ENV.value == "prod"


def test_prod_slack_log_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SLACK=LOG is allowed (safe non-destructive default)."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SLACK": "LOG"})
    assert settings.INTEGRATION_MODE_SLACK.value == "LOG"
    assert settings.APP_ENV.value == "prod"


def test_prod_sn_mock_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SN=MOCK raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_SN"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SN": "MOCK"})


def test_prod_sn_off_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SN=OFF raises ValidationError at startup."""
    get_settings.cache_clear()
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_SN"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SN": "OFF"})


def test_prod_sn_live_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SN=LIVE creates Settings successfully."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SN": "LIVE"})
    assert settings.INTEGRATION_MODE_SN.value == "LIVE"
    assert settings.APP_ENV.value == "prod"


def test_prod_sn_log_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_SN=LOG is allowed (safe non-destructive default)."""
    get_settings.cache_clear()
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_SN": "LOG"})
    assert settings.INTEGRATION_MODE_SN.value == "LOG"
    assert settings.APP_ENV.value == "prod"


def test_local_pd_mock_succeeds() -> None:
    """APP_ENV=local + INTEGRATION_MODE_PD=MOCK is allowed (non-prod environment)."""
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
        INTEGRATION_MODE_PD="MOCK",
    )
    assert settings.INTEGRATION_MODE_PD.value == "MOCK"
    assert settings.APP_ENV.value == "local"


def test_local_slack_mock_succeeds() -> None:
    """APP_ENV=local + INTEGRATION_MODE_SLACK=MOCK is allowed (non-prod environment)."""
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
        INTEGRATION_MODE_SLACK="MOCK",
    )
    assert settings.INTEGRATION_MODE_SLACK.value == "MOCK"
    assert settings.APP_ENV.value == "local"


def test_local_sn_mock_succeeds() -> None:
    """APP_ENV=local + INTEGRATION_MODE_SN=MOCK is allowed (non-prod environment)."""
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
        INTEGRATION_MODE_SN="MOCK",
    )
    assert settings.INTEGRATION_MODE_SN.value == "MOCK"
    assert settings.APP_ENV.value == "local"


def test_env_file_selection_uses_app_env() -> None:
    """APP_ENV=dev resolves to AppEnv.dev and max_action returns NOTIFY (FR50 precedence)."""
    settings = Settings(
        APP_ENV="dev",
        STAGE2_PEAK_HISTORY_MAX_DEPTH=2016,
        SHARD_LEASE_TTL_SECONDS=250,
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


def test_settings_health_server_default_host_is_0_0_0_0() -> None:
    """HEALTH_SERVER_HOST defaults to 0.0.0.0 for K8s liveness probe access."""
    get_settings.cache_clear()
    settings = Settings(**_base_settings_kwargs())
    assert settings.HEALTH_SERVER_HOST == "0.0.0.0"
    get_settings.cache_clear()


def test_settings_health_server_port_validation_rejects_out_of_range() -> None:
    """HEALTH_SERVER_PORT must be between 1 and 65535."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(**{**_base_settings_kwargs(), "HEALTH_SERVER_PORT": 0})
    with pytest.raises((ValueError, ValidationError)):
        Settings(**{**_base_settings_kwargs(), "HEALTH_SERVER_PORT": 65536})


# ---------------------------------------------------------------------------
# ATDD: Story 2.1 — Environment-specific peak history depth configuration
# Acceptance Criteria: AC1 (env files), AC2 (no fallback), AC3 (validator).
# ---------------------------------------------------------------------------


# --- AC1: FR12 — env files define explicit depth values ---


def test_env_dev_contains_stage2_peak_history_max_depth_2016() -> None:
    """AC1/FR12: config/.env.dev defines STAGE2_PEAK_HISTORY_MAX_DEPTH=2016."""
    env_dev = Path("config/.env.dev")
    assert env_dev.exists(), "config/.env.dev must exist"
    content = env_dev.read_text()
    assert "STAGE2_PEAK_HISTORY_MAX_DEPTH=2016" in content, (
        "config/.env.dev must contain STAGE2_PEAK_HISTORY_MAX_DEPTH=2016 "
        "(7 days × 288 samples/day at 5-min intervals)"
    )
    assert "SHARD_LEASE_TTL_SECONDS=250" in content, (
        "config/.env.dev must contain SHARD_LEASE_TTL_SECONDS=250 "
        "(calibrated below HOT_PATH_SCHEDULER_INTERVAL_SECONDS=300)"
    )


def test_env_uat_template_contains_stage2_peak_history_max_depth_4320() -> None:
    """AC1/FR12: config/.env.uat.template defines STAGE2_PEAK_HISTORY_MAX_DEPTH=4320."""
    env_uat = Path("config/.env.uat.template")
    assert env_uat.exists(), "config/.env.uat.template must exist"
    content = env_uat.read_text()
    assert "STAGE2_PEAK_HISTORY_MAX_DEPTH=4320" in content, (
        "config/.env.uat.template must contain STAGE2_PEAK_HISTORY_MAX_DEPTH=4320 "
        "(15 days × 288 samples/day at 5-min intervals)"
    )
    assert "SHARD_LEASE_TTL_SECONDS=294" in content, (
        "config/.env.uat.template must contain SHARD_LEASE_TTL_SECONDS=294 "
        "(UAT p95 + 31s safety margin, and < scheduler interval)"
    )


def test_env_prod_template_contains_stage2_peak_history_max_depth_8640() -> None:
    """AC1/FR12: config/.env.prod.template defines STAGE2_PEAK_HISTORY_MAX_DEPTH=8640."""
    env_prod = Path("config/.env.prod.template")
    assert env_prod.exists(), "config/.env.prod.template must exist"
    content = env_prod.read_text()
    assert "STAGE2_PEAK_HISTORY_MAX_DEPTH=8640" in content, (
        "config/.env.prod.template must contain STAGE2_PEAK_HISTORY_MAX_DEPTH=8640 "
        "(30 days × 288 samples/day at 5-min intervals)"
    )
    assert "SHARD_LEASE_TTL_SECONDS=294" in content, (
        "config/.env.prod.template must contain SHARD_LEASE_TTL_SECONDS=294 "
        "(aligned to UAT calibration basis and < scheduler interval)"
    )


# --- AC2: FR13 — explicit env-file depth overrides the legacy default ---


def test_settings_dev_env_depth_resolves_to_2016_not_default_12() -> None:
    """AC2/FR13: explicit depth value for APP_ENV=dev resolves to 2016, not 12."""
    get_settings.cache_clear()
    try:
        settings = Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "dev",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 2016,
            }
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 2016, (
            f"Expected STAGE2_PEAK_HISTORY_MAX_DEPTH=2016 for APP_ENV=dev, "
            f"got {settings.STAGE2_PEAK_HISTORY_MAX_DEPTH}"
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH != 12, (
            "STAGE2_PEAK_HISTORY_MAX_DEPTH must not fall back to legacy default 12 "
            "when explicit value is provided for APP_ENV=dev"
        )
    finally:
        get_settings.cache_clear()


def test_settings_loads_depth_from_dev_env_file() -> None:
    """AC2/FR13: APP_ENV-specific env-file loading resolves dev depth to 2016."""
    get_settings.cache_clear()
    try:
        settings = Settings(
            _env_file="config/.env.dev",
            APP_ENV="dev",
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 2016, (
            "Settings must load STAGE2_PEAK_HISTORY_MAX_DEPTH=2016 from config/.env.dev"
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH != 12
    finally:
        get_settings.cache_clear()


def test_settings_explicit_non_default_depth_passes_validation_for_all_envs() -> None:
    """AC2/FR13: explicit non-default depth value (e.g. 100) passes for any env."""
    get_settings.cache_clear()
    try:
        for env_value in ("dev", "uat", "prod", "local", "harness"):
            settings = Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": env_value,
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 100,
                    "SHARD_LEASE_TTL_SECONDS": 250 if env_value == "dev" else 294,
                }
            )
            assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 100, (
                f"APP_ENV={env_value}: explicit depth=100 must be accepted, "
                f"got {settings.STAGE2_PEAK_HISTORY_MAX_DEPTH}"
            )
    finally:
        get_settings.cache_clear()


# --- AC3: NFR-R3 — startup validator catches missing depth for named envs ---


def test_settings_dev_with_default_depth_12_raises_value_error() -> None:
    """AC3/NFR-R3: APP_ENV=dev with STAGE2_PEAK_HISTORY_MAX_DEPTH=12 raises ValueError."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError), match="STAGE2_PEAK_HISTORY_MAX_DEPTH"):
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "dev",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
                }
            )
    finally:
        get_settings.cache_clear()


def test_settings_uat_with_default_depth_12_raises_value_error() -> None:
    """AC3/NFR-R3: APP_ENV=uat with STAGE2_PEAK_HISTORY_MAX_DEPTH=12 raises ValueError."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError), match="STAGE2_PEAK_HISTORY_MAX_DEPTH"):
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "uat",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
                }
            )
    finally:
        get_settings.cache_clear()


def test_settings_prod_with_default_depth_12_raises_value_error() -> None:
    """AC3/NFR-R3: APP_ENV=prod with STAGE2_PEAK_HISTORY_MAX_DEPTH=12 raises ValueError."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError), match="STAGE2_PEAK_HISTORY_MAX_DEPTH"):
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "prod",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
                    # Must satisfy other prod-only validators to isolate the depth check
                    "INTEGRATION_MODE_LLM": "LIVE",
                    "INTEGRATION_MODE_PD": "LIVE",
                    "INTEGRATION_MODE_SLACK": "LIVE",
                    "INTEGRATION_MODE_SN": "LIVE",
                }
            )
    finally:
        get_settings.cache_clear()


def test_validator_error_message_includes_environment_name_dev() -> None:
    """AC3: ValueError for APP_ENV=dev includes environment name 'dev'."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "dev",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
                }
            )
        error_text = str(exc_info.value)
        assert "dev" in error_text, (
            "Error message must include environment name 'dev' for operator clarity; "
            f"got: {error_text}"
        )
    finally:
        get_settings.cache_clear()


def test_validator_error_message_includes_environment_name_uat() -> None:
    """AC3: ValueError for APP_ENV=uat includes environment name 'uat'."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "uat",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
                }
            )
        error_text = str(exc_info.value)
        assert "uat" in error_text, (
            "Error message must include environment name 'uat' for operator clarity; "
            f"got: {error_text}"
        )
    finally:
        get_settings.cache_clear()


def test_invalid_peak_depth_for_dev_includes_key_and_environment_name() -> None:
    """AC3: non-integer depth for APP_ENV=dev raises env-aware validation error."""
    get_settings.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                **{
                    **_base_settings_kwargs(),
                    "APP_ENV": "dev",
                    "STAGE2_PEAK_HISTORY_MAX_DEPTH": "abc",
                }
            )
        error_text = str(exc_info.value)
        assert "STAGE2_PEAK_HISTORY_MAX_DEPTH" in error_text
        assert "dev" in error_text
    finally:
        get_settings.cache_clear()


# --- AC3: local/harness envs are EXEMPT from the depth validator ---


def test_settings_local_with_default_depth_12_does_not_raise() -> None:
    """AC3: APP_ENV=local with STAGE2_PEAK_HISTORY_MAX_DEPTH=12 does not raise."""
    get_settings.cache_clear()
    try:
        settings = Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "local",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
            }
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 12
        assert settings.APP_ENV == AppEnv.local
    finally:
        get_settings.cache_clear()


def test_settings_harness_with_default_depth_12_does_not_raise() -> None:
    """AC3: APP_ENV=harness with STAGE2_PEAK_HISTORY_MAX_DEPTH=12 does not raise."""
    get_settings.cache_clear()
    try:
        settings = Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "harness",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 12,
            }
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 12
        assert settings.APP_ENV == AppEnv.harness
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("app_env", ["dev", "uat", "prod"])
def test_named_env_requires_explicit_shard_lease_ttl(app_env: str) -> None:
    """Named envs must provide SHARD_LEASE_TTL_SECONDS explicitly (no implicit fallback default)."""
    get_settings.cache_clear()
    try:
        kwargs = {
            **_base_settings_kwargs(),
            "APP_ENV": app_env,
            "STAGE2_PEAK_HISTORY_MAX_DEPTH": 2016 if app_env == "dev" else 4320,
        }
        kwargs.pop("SHARD_LEASE_TTL_SECONDS", None)
        if app_env == "prod":
            kwargs.update(
                {
                    "INTEGRATION_MODE_LLM": "LIVE",
                    "INTEGRATION_MODE_PD": "LIVE",
                    "INTEGRATION_MODE_SLACK": "LIVE",
                    "INTEGRATION_MODE_SN": "LIVE",
                }
            )
        with pytest.raises((ValueError, ValidationError), match="SHARD_LEASE_TTL_SECONDS"):
            Settings(**kwargs)
    finally:
        get_settings.cache_clear()


def test_shard_lease_ttl_rejects_value_greater_than_or_equal_to_scheduler_interval() -> None:
    """Startup validation rejects lease TTL that is not strictly lower than scheduler interval."""
    with pytest.raises((ValueError, ValidationError), match="HOT_PATH_SCHEDULER_INTERVAL_SECONDS"):
        Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "dev",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 2016,
                "SHARD_LEASE_TTL_SECONDS": 300,
                "HOT_PATH_SCHEDULER_INTERVAL_SECONDS": 300,
            }
        )


# ---------------------------------------------------------------------------
# Backfill settings validators (F4, F5, F8)
# ---------------------------------------------------------------------------


def _backfill_base_kwargs() -> dict:
    """Base kwargs with valid backfill settings for local env."""
    return {
        **_base_settings_kwargs(),
        "APP_ENV": "local",
        "BASELINE_BACKFILL_LOOKBACK_DAYS": 30,
        "BASELINE_BACKFILL_TIMEOUT_SECONDS": 60,
        "BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS": 270,
        "HOT_PATH_SCHEDULER_INTERVAL_SECONDS": 300,
    }


def test_backfill_timeout_rejects_per_metric_timeout_greater_than_total() -> None:
    """F4: BASELINE_BACKFILL_TIMEOUT_SECONDS must be <= BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS."""
    with pytest.raises(
        (ValueError, ValidationError), match="BASELINE_BACKFILL_TIMEOUT_SECONDS"
    ):
        Settings(
            **{
                **_backfill_base_kwargs(),
                "BASELINE_BACKFILL_TIMEOUT_SECONDS": 300,
                "BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS": 270,
            }
        )


def test_backfill_timeout_accepts_per_metric_timeout_equal_to_total() -> None:
    """F4: per-metric timeout equal to total timeout is acceptable."""
    settings = Settings(
        **{
            **_backfill_base_kwargs(),
            "BASELINE_BACKFILL_TIMEOUT_SECONDS": 270,
            "BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS": 270,
        }
    )
    assert settings.BASELINE_BACKFILL_TIMEOUT_SECONDS == 270


def test_backfill_total_timeout_rejects_value_gte_scheduler_interval() -> None:
    """F8: BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS must be < HOT_PATH_SCHEDULER_INTERVAL_SECONDS."""
    with pytest.raises(
        (ValueError, ValidationError), match="HOT_PATH_SCHEDULER_INTERVAL_SECONDS"
    ):
        Settings(
            **{
                **_backfill_base_kwargs(),
                "BASELINE_BACKFILL_TIMEOUT_SECONDS": 60,
                "BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS": 300,
                "HOT_PATH_SCHEDULER_INTERVAL_SECONDS": 300,
            }
        )


def test_backfill_total_timeout_accepts_value_less_than_scheduler_interval() -> None:
    """F8: total timeout strictly less than scheduler interval is valid."""
    settings = Settings(
        **{
            **_backfill_base_kwargs(),
            "BASELINE_BACKFILL_TIMEOUT_SECONDS": 60,
            "BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS": 270,
            "HOT_PATH_SCHEDULER_INTERVAL_SECONDS": 300,
        }
    )
    assert settings.BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS == 270


def test_peak_depth_rejects_new_default_8640_for_dev() -> None:
    """F5: STAGE2_PEAK_HISTORY_MAX_DEPTH=8640 (new default) is rejected for APP_ENV=dev."""
    with pytest.raises(
        (ValueError, ValidationError), match="STAGE2_PEAK_HISTORY_MAX_DEPTH"
    ):
        Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "dev",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 8640,
            }
        )


def test_peak_depth_rejects_new_default_8640_for_uat() -> None:
    """F5: STAGE2_PEAK_HISTORY_MAX_DEPTH=8640 (new default) is rejected for APP_ENV=uat."""
    with pytest.raises(
        (ValueError, ValidationError), match="STAGE2_PEAK_HISTORY_MAX_DEPTH"
    ):
        Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "uat",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 8640,
                "SHARD_LEASE_TTL_SECONDS": 294,
            }
        )


def test_peak_depth_accepts_8640_for_prod() -> None:
    """F5: STAGE2_PEAK_HISTORY_MAX_DEPTH=8640 is the correct value for prod."""
    get_settings.cache_clear()
    try:
        settings = Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": "prod",
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 8640,
                "SHARD_LEASE_TTL_SECONDS": 270,
                "INTEGRATION_MODE_LLM": "LIVE",
                "INTEGRATION_MODE_PD": "LIVE",
                "INTEGRATION_MODE_SLACK": "LIVE",
                "INTEGRATION_MODE_SN": "LIVE",
            }
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 8640
    finally:
        get_settings.cache_clear()


def test_peak_depth_accepts_8640_for_local_and_harness() -> None:
    """F5: STAGE2_PEAK_HISTORY_MAX_DEPTH=8640 is accepted in local/harness (no constraint)."""
    for env in ("local", "harness"):
        settings = Settings(
            **{
                **_base_settings_kwargs(),
                "APP_ENV": env,
                "STAGE2_PEAK_HISTORY_MAX_DEPTH": 8640,
            }
        )
        assert settings.STAGE2_PEAK_HISTORY_MAX_DEPTH == 8640

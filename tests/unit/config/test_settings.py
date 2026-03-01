from pathlib import Path

import pytest
import structlog
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import (
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
    )
    with structlog.testing.capture_logs() as cap_logs:
        settings.log_active_config(structlog.get_logger())

    assert len(cap_logs) == 1
    event = cap_logs[0]
    assert event.get("S3_SECRET_KEY") == "[REDACTED]"
    assert event.get("S3_ACCESS_KEY") == "[REDACTED]"
    assert "super_secret" not in str(cap_logs)
    assert "secret_password" not in str(cap_logs)
    assert "redis_password" not in str(cap_logs)
    assert "access_key_id" not in str(cap_logs)


def test_get_settings_returns_same_instance() -> None:
    """get_settings() caches and returns the same Settings instance."""
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()


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

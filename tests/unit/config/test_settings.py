import pytest
from pathlib import Path
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import (
    AppEnv,
    ENV_ACTION_CAPS,
    IntegrationMode,
    Settings,
    get_settings,
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


def test_log_active_config_masks_secret(capsys: pytest.CaptureFixture[str]) -> None:
    """log_active_config does not expose S3_SECRET_KEY in log output."""
    import structlog

    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    logger = structlog.get_logger()
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:secret_password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="access",
        S3_SECRET_KEY="super_secret",
        S3_BUCKET="bucket",
    )
    settings.log_active_config(logger)
    captured = capsys.readouterr()
    assert "super_secret" not in captured.out
    assert "secret_password" not in captured.out
    assert "[REDACTED]" in captured.out


def test_get_settings_returns_same_instance() -> None:
    """get_settings() caches and returns the same Settings instance."""
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()

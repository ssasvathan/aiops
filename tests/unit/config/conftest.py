import pytest
from pathlib import Path

from aiops_triage_pipeline.config.settings import Settings


@pytest.fixture
def minimal_settings(tmp_path: Path) -> Settings:
    """A minimal Settings instance with no env file and safe defaults."""
    return Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://aiops:aiops@localhost:5432/aiops",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="minioadmin",
        S3_SECRET_KEY="minioadmin",
        S3_BUCKET="aiops-cases",
    )

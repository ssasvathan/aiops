import pytest

from aiops_triage_pipeline.health.registry import HealthRegistry


@pytest.fixture
def registry() -> HealthRegistry:
    """Fresh HealthRegistry instance per test.

    IMPORTANT: Do NOT use get_health_registry() in unit tests — the @functools.cache
    singleton retains state across tests. Construct a fresh instance here.
    """
    return HealthRegistry()

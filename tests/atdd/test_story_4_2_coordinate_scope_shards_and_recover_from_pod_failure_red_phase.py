"""ATDD red-phase acceptance tests for Story 4.2 shard coordination + lease recovery."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable

import pytest

from aiops_triage_pipeline import __main__
from aiops_triage_pipeline.config.settings import Settings
from tests.atdd.fixtures.story_4_2_test_data import (
    RecordingRedisShardClient,
    build_settings_kwargs,
    load_module_or_fail,
)


def _load_shard_module() -> object:
    return load_module_or_fail("aiops_triage_pipeline.coordination.shard_registry", pytest.fail)


def _build_shard_coordinator(*, redis_client: object) -> object:
    module = _load_shard_module()
    for class_name in ("RedisShardCoordinator", "ShardCoordinator"):
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        constructor_attempts = (
            {"redis_client": redis_client, "pod_id": "pod-a"},
            {"redis_client": redis_client},
            {"client": redis_client, "pod_id": "pod-a"},
            {"client": redis_client},
        )
        for kwargs in constructor_attempts:
            try:
                return cls(**kwargs)  # type: ignore[misc]
            except TypeError:
                continue
    pytest.fail(
        "Story 4.2 requires a shard coordination class named RedisShardCoordinator or "
        "ShardCoordinator in aiops_triage_pipeline.coordination.shard_registry"
    )


def _normalize_status(result: object) -> str:
    status = getattr(result, "status", result)
    if hasattr(status, "value"):
        return str(status.value)
    if isinstance(status, bool):
        return "acquired" if status else "yielded"
    return str(status)


def _call_assign_to_pod(
    assign_fn: Callable[..., object],
    *,
    scopes: list[tuple[str, str, str]],
    active_pod_ids: list[str],
    shard_count: int,
    pod_id: str,
) -> object:
    attempts = (
        {
            "scopes": scopes,
            "active_pod_ids": active_pod_ids,
            "shard_count": shard_count,
            "pod_id": pod_id,
        },
        {
            "scopes": scopes,
            "pod_membership": active_pod_ids,
            "shard_count": shard_count,
            "pod_id": pod_id,
        },
        {
            "scope_keys": scopes,
            "active_pod_ids": active_pod_ids,
            "shard_count": shard_count,
            "owner_id": pod_id,
        },
    )
    for kwargs in attempts:
        try:
            return assign_fn(**kwargs)
        except TypeError:
            continue
    return assign_fn(scopes, active_pod_ids, shard_count, pod_id)


def _normalize_scope_set(result: object) -> set[tuple[str, str, str]]:
    payload = result
    if isinstance(payload, dict):
        if "assigned_scopes" in payload:
            payload = payload["assigned_scopes"]
        elif "scopes" in payload:
            payload = payload["scopes"]
    if payload is None:
        return set()
    normalized: set[tuple[str, str, str]] = set()
    for item in payload:  # type: ignore[assignment]
        if isinstance(item, list):
            normalized.add((str(item[0]), str(item[1]), str(item[2])))
            continue
        if isinstance(item, tuple):
            normalized.add((str(item[0]), str(item[1]), str(item[2])))
            continue
        raise AssertionError(f"Unexpected scope item shape: {item!r}")
    return normalized


def _acquire_shard_lease(
    coordinator: object,
    *,
    shard_id: int,
    owner_id: str,
    lease_ttl_seconds: int,
) -> object:
    for method_name in ("acquire_lease", "try_acquire_lease", "acquire_shard_lease"):
        method = getattr(coordinator, method_name, None)
        if method is None:
            continue
        for kwargs in (
            {"shard_id": shard_id, "owner_id": owner_id, "lease_ttl_seconds": lease_ttl_seconds},
            {"shard_id": shard_id, "owner_id": owner_id},
        ):
            try:
                return method(**kwargs)  # type: ignore[misc]
            except TypeError:
                continue
        return method(shard_id, owner_id, lease_ttl_seconds)  # type: ignore[misc]
    pytest.fail(
        "Story 4.2 requires shard lease acquire method "
        "(acquire_lease / try_acquire_lease / acquire_shard_lease)"
    )


def test_p0_settings_expose_shard_coordination_flags_and_ttls() -> None:
    """AC1/AC2: runtime settings must gate shard coordination and lease/checkpoint TTLs."""
    settings = Settings(**build_settings_kwargs())

    assert hasattr(settings, "SHARD_REGISTRY_ENABLED")
    assert getattr(settings, "SHARD_REGISTRY_ENABLED") is False
    assert hasattr(settings, "SHARD_COORDINATION_SHARD_COUNT")
    assert getattr(settings, "SHARD_COORDINATION_SHARD_COUNT") > 0
    assert hasattr(settings, "SHARD_LEASE_TTL_SECONDS")
    assert getattr(settings, "SHARD_LEASE_TTL_SECONDS") > 0
    assert hasattr(settings, "SHARD_CHECKPOINT_TTL_SECONDS")
    assert getattr(settings, "SHARD_CHECKPOINT_TTL_SECONDS") > 0

    with pytest.raises(ValueError, match="SHARD_COORDINATION_SHARD_COUNT"):
        Settings(**build_settings_kwargs(SHARD_COORDINATION_SHARD_COUNT=0))
    with pytest.raises(ValueError, match="SHARD_LEASE_TTL_SECONDS"):
        Settings(**build_settings_kwargs(SHARD_LEASE_TTL_SECONDS=0))
    with pytest.raises(ValueError, match="SHARD_CHECKPOINT_TTL_SECONDS"):
        Settings(**build_settings_kwargs(SHARD_CHECKPOINT_TTL_SECONDS=0))


def test_p0_shard_module_exposes_key_builders_assignment_and_lease_primitives() -> None:
    """AC1/AC2: shard module must provide D1 key builders + assignment/lease surfaces."""
    module = _load_shard_module()

    assert hasattr(module, "build_shard_lease_key")
    assert hasattr(module, "build_shard_checkpoint_key")
    assert hasattr(module, "assign_scopes_to_pod") or hasattr(module, "deterministic_assign_scopes")
    assert hasattr(module, "RedisShardCoordinator") or hasattr(module, "ShardCoordinator")


def test_p0_assignment_is_deterministic_for_stable_scope_and_membership_inputs() -> None:
    """AC1: same scope/member inputs must produce stable shard assignments per pod."""
    module = _load_shard_module()
    assign_fn = getattr(module, "assign_scopes_to_pod", None) or getattr(
        module,
        "deterministic_assign_scopes",
        None,
    )
    if assign_fn is None:
        pytest.fail(
            "Story 4.2 requires assign_scopes_to_pod(...) or deterministic_assign_scopes(...)"
        )

    scopes = [
        ("prod", "cluster-a", "orders"),
        ("prod", "cluster-a", "payments"),
        ("prod", "cluster-a", "inventory"),
        ("prod", "cluster-a", "billing"),
    ]
    active_pod_ids = ["pod-a", "pod-b"]

    first = _call_assign_to_pod(
        assign_fn,
        scopes=scopes,
        active_pod_ids=active_pod_ids,
        shard_count=2,
        pod_id="pod-a",
    )
    second = _call_assign_to_pod(
        assign_fn,
        scopes=scopes,
        active_pod_ids=active_pod_ids,
        shard_count=2,
        pod_id="pod-a",
    )

    first_scopes = _normalize_scope_set(first)
    second_scopes = _normalize_scope_set(second)

    assert first_scopes == second_scopes
    assert first_scopes.issubset(set(scopes))


def test_p0_lease_expiry_allows_safe_handoff_to_recovery_pod() -> None:
    """AC2: after TTL expiry, a new pod should recover lease ownership automatically."""
    coordinator = _build_shard_coordinator(redis_client=RecordingRedisShardClient())

    first = _acquire_shard_lease(
        coordinator,
        shard_id=1,
        owner_id="pod-a",
        lease_ttl_seconds=1,
    )
    second = _acquire_shard_lease(
        coordinator,
        shard_id=1,
        owner_id="pod-b",
        lease_ttl_seconds=1,
    )
    time.sleep(1.2)
    third = _acquire_shard_lease(
        coordinator,
        shard_id=1,
        owner_id="pod-b",
        lease_ttl_seconds=1,
    )

    assert _normalize_status(first) == "acquired"
    # Allows optimistic renewal implementations.
    assert _normalize_status(second) in {"yielded", "acquired"}
    assert _normalize_status(third) == "acquired"


def test_p0_findings_cache_exposes_per_shard_checkpoint_write_surface() -> None:
    """AC1: findings cache should support per-shard per-interval checkpoint writes."""
    from aiops_triage_pipeline.cache import findings_cache

    assert hasattr(findings_cache, "build_shard_checkpoint_key")
    assert hasattr(findings_cache, "set_shard_interval_checkpoint")

    signature = inspect.signature(findings_cache.set_shard_interval_checkpoint)
    assert "redis_client" in signature.parameters
    assert "shard_id" in signature.parameters


def test_p1_metrics_surface_exposes_shard_checkpoint_and_recovery_counters() -> None:
    """AC1/AC2: observability must include shard checkpoint and lease recovery signals."""
    from aiops_triage_pipeline.health import metrics

    assert hasattr(metrics, "record_shard_checkpoint_written")
    assert hasattr(metrics, "record_shard_lease_recovered")
    assert hasattr(metrics, "record_shard_assignment")


def test_p1_hot_path_scheduler_source_contains_shard_gating_and_fallback_markers() -> None:
    """AC1/AC2: scheduler source should gate by shard flag and include full-scope fallback."""
    source = inspect.getsource(__main__._hot_path_scheduler_loop)
    source_lower = source.lower()

    assert "SHARD_REGISTRY_ENABLED" in source
    assert "checkpoint" in source_lower
    assert ("full_scope" in source_lower) or ("full-scope" in source_lower)
    assert "shard" in source_lower

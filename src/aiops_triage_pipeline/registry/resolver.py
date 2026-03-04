"""Topology registry scope resolution for Stage 3 context enrichment."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping

from pydantic import BaseModel, Field, model_validator

from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.registry.loader import (
    CanonicalStream,
    CanonicalStreamInstance,
    CanonicalTopicEntry,
    TopologyRegistrySnapshot,
)

REASON_RESOLVED = "resolved"
REASON_INVALID_SCOPE_SHAPE = "invalid_scope_shape"
REASON_SCOPE_NOT_FOUND = "scope_not_found"
REASON_TOPIC_NOT_FOUND = "topic_not_found"
REASON_STREAM_NOT_FOUND = "stream_not_found"
REASON_STREAM_INSTANCE_NOT_FOUND = "stream_instance_not_found"
REASON_UNSUPPORTED_TOPIC_ROLE = "UNSUPPORTED_TOPIC_ROLE"

TopologyResolutionStatus = Literal["resolved", "unresolved"]
NormalizedTopicRole = Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
AnomalyScope = tuple[str, str, str] | tuple[str, str, str, str]

_TOPIC_ROLE_NORMALIZATION: dict[str, NormalizedTopicRole] = {
    "SOURCE_TOPIC": "SOURCE_TOPIC",
    "KAFKA_SOURCE_STREAM": "SOURCE_TOPIC",
    "STANDARDIZER_SHARED": "SHARED_TOPIC",
    "AUDIT_RAW_SHARED": "SHARED_TOPIC",
    "SHARED_TOPIC": "SHARED_TOPIC",
    "SINK_TOPIC": "SINK_TOPIC",
}


class TopologyResolution(BaseModel, frozen=True):
    """Typed topology resolution result for one anomaly scope."""

    scope: tuple[str, ...]
    status: TopologyResolutionStatus
    reason_code: str
    stream_id: str | None = None
    topic_role: NormalizedTopicRole | None = None
    criticality_tier: CriticalityTier | None = None
    source_system: str | None = None
    diagnostics: Mapping[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_and_freeze(self) -> "TopologyResolution":
        if self.status == "resolved":
            if self.reason_code != REASON_RESOLVED:
                raise ValueError("resolved topology output must use reason_code='resolved'")
            if (
                self.stream_id is None
                or self.topic_role is None
                or self.criticality_tier is None
            ):
                raise ValueError(
                    "resolved topology output requires stream_id, topic_role, and criticality_tier"
                )
        else:
            if self.stream_id is not None or self.topic_role is not None:
                raise ValueError("unresolved topology output cannot include resolved fields")
            if self.criticality_tier is not None:
                raise ValueError("unresolved topology output cannot include criticality_tier")

        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))
        return self


def resolve_anomaly_scope(
    *,
    snapshot: TopologyRegistrySnapshot,
    anomaly_scope: tuple[str, ...],
) -> TopologyResolution:
    """Resolve stream context from an anomaly scope key.

    Supported scope forms:
    - (env, cluster_id, topic)
    - (env, cluster_id, group, topic)
    """
    parsed_scope = _parse_anomaly_scope(anomaly_scope)
    if parsed_scope is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_INVALID_SCOPE_SHAPE,
            diagnostics={"scope": _render_scope(anomaly_scope)},
        )

    env, cluster_id, topic, _group = parsed_scope
    scope_key = (env, cluster_id)
    scoped_topics = snapshot.registry.topic_index_by_scope.get(scope_key)
    if scoped_topics is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_SCOPE_NOT_FOUND,
            diagnostics={
                "env": env,
                "cluster_id": cluster_id,
                "topic": topic,
            },
        )

    topic_entry = scoped_topics.get(topic)
    if topic_entry is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_TOPIC_NOT_FOUND,
            diagnostics={
                "env": env,
                "cluster_id": cluster_id,
                "topic": topic,
            },
        )

    stream = snapshot.registry.streams_by_id.get(topic_entry.stream_id)
    if stream is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_STREAM_NOT_FOUND,
            diagnostics={
                "env": env,
                "cluster_id": cluster_id,
                "topic": topic,
                "stream_id": topic_entry.stream_id,
            },
        )

    stream_instance = _find_stream_instance(stream=stream, env=env, cluster_id=cluster_id)
    if stream_instance is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_STREAM_INSTANCE_NOT_FOUND,
            diagnostics={
                "env": env,
                "cluster_id": cluster_id,
                "stream_id": stream.stream_id,
            },
        )

    normalized_topic_role = _normalize_topic_role(topic_entry.role)
    if normalized_topic_role is None:
        return _unresolved(
            scope=anomaly_scope,
            reason_code=REASON_UNSUPPORTED_TOPIC_ROLE,
            diagnostics={
                "env": env,
                "cluster_id": cluster_id,
                "topic": topic,
                "raw_topic_role": topic_entry.role,
            },
        )

    source_system = _resolve_source_system(
        topic_entry=topic_entry,
        stream_instance=stream_instance,
        topic=topic,
    )
    criticality_tier = _resolve_criticality_tier(
        stream=stream,
        stream_instance=stream_instance,
        topic=topic,
        source_system=source_system,
    )

    return TopologyResolution(
        scope=anomaly_scope,
        status="resolved",
        reason_code=REASON_RESOLVED,
        stream_id=stream.stream_id,
        topic_role=normalized_topic_role,
        criticality_tier=criticality_tier,
        source_system=source_system,
        diagnostics={
            "env": env,
            "cluster_id": cluster_id,
            "topic": topic,
        },
    )


def resolve_anomaly_scopes(
    *,
    snapshot: TopologyRegistrySnapshot,
    anomaly_scopes: Iterable[tuple[str, ...]],
) -> dict[tuple[str, ...], TopologyResolution]:
    """Resolve multiple anomaly scopes deterministically."""
    scopes = tuple(anomaly_scopes)
    return {
        scope: resolve_anomaly_scope(snapshot=snapshot, anomaly_scope=scope)
        for scope in sorted(scopes)
    }


def _parse_anomaly_scope(scope: tuple[str, ...]) -> tuple[str, str, str, str | None] | None:
    if len(scope) == 3:
        env = _normalize_scope_part(scope[0])
        cluster_id = _normalize_scope_part(scope[1])
        topic = _normalize_scope_part(scope[2])
        if env is None or cluster_id is None or topic is None:
            return None
        return (env, cluster_id, topic, None)

    if len(scope) == 4:
        env = _normalize_scope_part(scope[0])
        cluster_id = _normalize_scope_part(scope[1])
        group = _normalize_scope_part(scope[2])
        topic = _normalize_scope_part(scope[3])
        if env is None or cluster_id is None or group is None or topic is None:
            return None
        return (env, cluster_id, topic, group)

    return None


def _normalize_scope_part(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_topic_role(role: str) -> NormalizedTopicRole | None:
    return _TOPIC_ROLE_NORMALIZATION.get(role.strip().upper())


def _find_stream_instance(
    *,
    stream: CanonicalStream,
    env: str,
    cluster_id: str,
) -> CanonicalStreamInstance | None:
    for instance in stream.instances:
        if instance.env == env and instance.cluster_id == cluster_id:
            return instance
    return None


def _resolve_source_system(
    *,
    topic_entry: CanonicalTopicEntry,
    stream_instance: CanonicalStreamInstance,
    topic: str,
) -> str | None:
    if topic_entry.source_system is not None:
        return topic_entry.source_system

    for source in stream_instance.sources:
        if _mapping_str(source, "source_topic") == topic:
            source_system = _mapping_str(source, "source_system")
            if source_system is not None:
                return source_system

    for source in stream_instance.sources:
        source_system = _mapping_str(source, "source_system")
        if source_system is not None:
            return source_system

    return None


def _resolve_criticality_tier(
    *,
    stream: CanonicalStream,
    stream_instance: CanonicalStreamInstance,
    topic: str,
    source_system: str | None,
) -> CriticalityTier:
    # Deterministic fallback order:
    # 1) stream.criticality_tier
    # 2) instance.sources[] matched by source_topic
    # 3) instance.sources[] matched by source_system
    # 4) first instance.sources[] with criticality_tier
    # 5) UNKNOWN
    stream_tier = _to_criticality_tier(stream.criticality_tier)
    if stream_tier is not None:
        return stream_tier

    for source in stream_instance.sources:
        if _mapping_str(source, "source_topic") == topic:
            source_tier = _to_criticality_tier(source.get("criticality_tier"))
            if source_tier is not None:
                return source_tier

    if source_system is not None:
        for source in stream_instance.sources:
            if _mapping_str(source, "source_system") == source_system:
                source_tier = _to_criticality_tier(source.get("criticality_tier"))
                if source_tier is not None:
                    return source_tier

    for source in stream_instance.sources:
        source_tier = _to_criticality_tier(source.get("criticality_tier"))
        if source_tier is not None:
            return source_tier

    return CriticalityTier.UNKNOWN


def _to_criticality_tier(value: Any) -> CriticalityTier | None:
    if value is None:
        return None
    if isinstance(value, CriticalityTier):
        return value
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    try:
        return CriticalityTier(normalized)
    except ValueError:
        return None


def _mapping_str(source: Mapping[str, Any], key: str) -> str | None:
    raw_value = source.get(key)
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized if normalized else None


def _unresolved(
    *,
    scope: tuple[str, ...],
    reason_code: str,
    diagnostics: Mapping[str, str],
) -> TopologyResolution:
    return TopologyResolution(
        scope=scope,
        status="unresolved",
        reason_code=reason_code,
        diagnostics=diagnostics,
    )


def _render_scope(scope: tuple[str, ...]) -> str:
    return "|".join(str(part) for part in scope)

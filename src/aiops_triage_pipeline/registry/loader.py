"""Topology registry loader: v0/v1 parsing, canonicalization, validation, and reload."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

import yaml
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from aiops_triage_pipeline.contracts.topology_registry import TopologyRegistryLoaderRulesV1
from aiops_triage_pipeline.errors.exceptions import PipelineError
from aiops_triage_pipeline.logging.setup import get_logger


class TopologyRegistryError(PipelineError):
    """Base class for topology registry loader errors."""


class TopologyRegistryValidationError(TopologyRegistryError):
    """Typed validation failure with actionable source/path context."""

    def __init__(
        self,
        *,
        category: str,
        source_path: str,
        offending_key: str | None = None,
        detail: str = "",
    ) -> None:
        self.category = category
        self.source_path = source_path
        self.offending_key = offending_key
        self.detail = detail
        suffix = f" ({detail})" if detail else ""
        where = f" key={offending_key!r}" if offending_key is not None else ""
        super().__init__(f"{category} in {source_path}{where}{suffix}")


class CanonicalTopicEntry(BaseModel, frozen=True):
    """Canonical topic index entry used by downstream topology resolution."""

    topic: str
    role: str
    stream_id: str
    source_system: str | None = None


class CanonicalStreamInstance(BaseModel, frozen=True):
    """One stream deployment scope keyed by (env, cluster_id)."""

    env: str
    cluster_id: str
    topic_index: Mapping[str, CanonicalTopicEntry]
    topics: Mapping[str, str] = Field(default_factory=dict)
    shared_components: Mapping[str, Any] = Field(default_factory=dict)
    sources: tuple[Mapping[str, Any], ...] = ()
    sinks: tuple[Mapping[str, Any], ...] = ()
    peak_window_policy: Mapping[str, Any] | None = None

    @model_validator(mode="after")
    def _freeze_nested(self) -> "CanonicalStreamInstance":
        object.__setattr__(self, "topic_index", MappingProxyType(dict(self.topic_index)))
        object.__setattr__(self, "topics", MappingProxyType(dict(self.topics)))
        object.__setattr__(
            self,
            "shared_components",
            MappingProxyType(dict(self.shared_components)),
        )
        object.__setattr__(self, "sources", tuple(MappingProxyType(dict(x)) for x in self.sources))
        object.__setattr__(self, "sinks", tuple(MappingProxyType(dict(x)) for x in self.sinks))
        if self.peak_window_policy is not None:
            object.__setattr__(
                self,
                "peak_window_policy",
                MappingProxyType(dict(self.peak_window_policy)),
            )
        return self


class CanonicalStream(BaseModel, frozen=True):
    """Canonical stream node with immutable scoped instances."""

    stream_id: str
    description: str | None = None
    criticality_tier: str | None = None
    owners: Mapping[str, Any] = Field(default_factory=dict)
    instances: tuple[CanonicalStreamInstance, ...]

    @model_validator(mode="after")
    def _freeze_nested(self) -> "CanonicalStream":
        ordered_instances = tuple(sorted(self.instances, key=lambda i: (i.env, i.cluster_id)))
        object.__setattr__(self, "instances", ordered_instances)
        object.__setattr__(self, "owners", MappingProxyType(dict(self.owners)))
        return self


class RoutingDirectoryEntry(BaseModel, frozen=True):
    """Routing key target metadata."""

    routing_key: str
    owning_team_id: str
    owning_team_name: str
    support_channel: str | None = None
    escalation_policy_ref: str | None = None
    service_now_assignment_group: str | None = None


class ConsumerGroupOwnerEntry(BaseModel, frozen=True):
    """Ownership mapping for (env, cluster_id, group)."""

    env: str
    cluster_id: str
    group: str
    routing_key: str
    source: str | None = None
    confidence: float | None = None
    reason_codes: tuple[str, ...] = ()


class TopicOwnerEntry(BaseModel, frozen=True):
    """Ownership mapping for (env, cluster_id, topic)."""

    env: str
    cluster_id: str
    topic: str
    routing_key: str
    source: str | None = None
    confidence: float | None = None
    reason_codes: tuple[str, ...] = ()


class StreamDefaultOwnerEntry(BaseModel, frozen=True):
    """Ownership mapping for (stream_id, env, cluster_id)."""

    stream_id: str
    env: str
    cluster_id: str
    routing_key: str
    source: str | None = None
    confidence: float | None = None
    reason_codes: tuple[str, ...] = ()


class CanonicalOwnershipMap(BaseModel, frozen=True):
    """Canonical ownership lookup collections."""

    consumer_group_owners: tuple[ConsumerGroupOwnerEntry, ...] = ()
    topic_owners: tuple[TopicOwnerEntry, ...] = ()
    stream_default_owner: tuple[StreamDefaultOwnerEntry, ...] = ()
    platform_default: str | None = None


class CanonicalTopologyRegistry(BaseModel, frozen=True):
    """Canonical in-memory topology registry."""

    streams: tuple[CanonicalStream, ...]
    streams_by_id: Mapping[str, CanonicalStream]
    topic_index_by_scope: Mapping[tuple[str, str], Mapping[str, CanonicalTopicEntry]]
    routing_directory: Mapping[str, RoutingDirectoryEntry]
    ownership_map: CanonicalOwnershipMap

    @model_validator(mode="after")
    def _freeze_nested(self) -> "CanonicalTopologyRegistry":
        ordered_streams = tuple(sorted(self.streams, key=lambda s: s.stream_id))
        object.__setattr__(self, "streams", ordered_streams)
        object.__setattr__(self, "streams_by_id", MappingProxyType(dict(self.streams_by_id)))
        frozen_scope_index = {
            scope: MappingProxyType(dict(entries))
            for scope, entries in sorted(self.topic_index_by_scope.items(), key=lambda x: x[0])
        }
        object.__setattr__(
            self,
            "topic_index_by_scope",
            MappingProxyType(frozen_scope_index),
        )
        object.__setattr__(
            self,
            "routing_directory",
            MappingProxyType(dict(self.routing_directory)),
        )
        return self


class TopologyRegistryMetadata(BaseModel, frozen=True):
    """Loader metadata returned with each immutable snapshot."""

    source_path: str
    source_mtime_ns: int
    input_version: int
    canonical_version: int = 1
    loaded_at: AwareDatetime
    load_duration_ms: float


class TopologyRegistrySnapshot(BaseModel, frozen=True):
    """Immutable registry payload + metadata."""

    registry: CanonicalTopologyRegistry
    metadata: TopologyRegistryMetadata


class _DuplicateYamlKeyError(Exception):
    def __init__(self, *, path: str, key: str, line: int | None = None) -> None:
        self.path = path
        self.key = key
        self.line = line
        super().__init__(f"Duplicate key {key!r} under {path!r} at line {line}")


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._path_stack: list[str] = []


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            parent = ".".join(loader._path_stack) if loader._path_stack else "<root>"
            raise _DuplicateYamlKeyError(
                path=parent,
                key=str(key),
                line=key_node.start_mark.line + 1,
            )
        loader._path_stack.append(str(key))
        try:
            value = loader.construct_object(value_node, deep=deep)
        finally:
            loader._path_stack.pop()
        mapping[key] = value
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_topology_registry(
    path: Path,
    *,
    rules: TopologyRegistryLoaderRulesV1 | None = None,
    default_env: str = "prod",
    default_cluster_id: str = "Business_Essential",
) -> TopologyRegistrySnapshot:
    """Load and validate a topology registry into immutable canonical form."""

    started_at = perf_counter()
    source_path = str(path)
    raw = _read_registry_yaml(path)
    effective_rules = rules or TopologyRegistryLoaderRulesV1()

    input_version = _detect_registry_version(raw)
    _validate_supported_version(
        version=input_version,
        rules=effective_rules,
        source_path=source_path,
    )

    registry = _canonicalize_registry(
        raw=raw,
        source_path=source_path,
        input_version=input_version,
        default_env=default_env,
        default_cluster_id=default_cluster_id,
    )
    _validate_ownership_matrix(registry=registry, source_path=source_path)

    metadata = TopologyRegistryMetadata(
        source_path=source_path,
        source_mtime_ns=path.stat().st_mtime_ns,
        input_version=input_version,
        loaded_at=datetime.now(timezone.utc),
        load_duration_ms=(perf_counter() - started_at) * 1000.0,
    )
    return TopologyRegistrySnapshot(registry=registry, metadata=metadata)


class TopologyRegistryLoader:
    """Reloadable registry manager preserving last-known-good snapshots."""

    def __init__(
        self,
        path: Path,
        *,
        rules: TopologyRegistryLoaderRulesV1 | None = None,
        default_env: str = "prod",
        default_cluster_id: str = "Business_Essential",
    ) -> None:
        self._path = path
        self._rules = rules
        self._default_env = default_env
        self._default_cluster_id = default_cluster_id
        self._lock = Lock()
        self._snapshot: TopologyRegistrySnapshot | None = None
        self._logger = get_logger("registry.loader")

    def load(self) -> TopologyRegistrySnapshot:
        """Load initial snapshot (or force a full reload)."""
        snapshot = load_topology_registry(
            self._path,
            rules=self._rules,
            default_env=self._default_env,
            default_cluster_id=self._default_cluster_id,
        )
        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def get_snapshot(self) -> TopologyRegistrySnapshot:
        """Return current immutable snapshot for concurrent read access."""
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("Topology registry is not loaded yet. Call load() first.")
            return self._snapshot

    def reload_if_changed(self) -> bool:
        """Reload and atomically swap snapshot when source file mtime changes."""
        with self._lock:
            current = self._snapshot

        if current is None:
            self.load()
            return True

        current_mtime = current.metadata.source_mtime_ns
        latest_mtime = self._path.stat().st_mtime_ns
        if latest_mtime == current_mtime:
            return False

        try:
            candidate = load_topology_registry(
                self._path,
                rules=self._rules,
                default_env=self._default_env,
                default_cluster_id=self._default_cluster_id,
            )
        except TopologyRegistryValidationError as exc:
            self._logger.warning(
                "topology_registry_reload_failed",
                event_type="registry.reload_failed",
                source_path=exc.source_path,
                validation_category=exc.category,
                offending_key=exc.offending_key,
                detail=exc.detail,
            )
            return False

        with self._lock:
            self._snapshot = candidate
        self._logger.info(
            "topology_registry_reload_success",
            event_type="registry.reload_success",
            source_path=str(self._path),
            input_version=candidate.metadata.input_version,
            load_duration_ms=round(candidate.metadata.load_duration_ms, 3),
        )
        return True


def _read_registry_yaml(path: Path) -> Mapping[str, Any]:
    source_path = str(path)
    content = path.read_text(encoding="utf-8")
    try:
        loaded = yaml.load(content, Loader=_UniqueKeySafeLoader)
    except _DuplicateYamlKeyError as exc:
        is_topic_index_duplicate = exc.path.endswith("topic_index")
        category = "duplicate_topic_index" if is_topic_index_duplicate else "duplicate_yaml_key"
        raise TopologyRegistryValidationError(
            category=category,
            source_path=source_path,
            offending_key=f"{exc.path}.{exc.key}",
            detail=f"duplicate mapping key (line {exc.line})",
        ) from exc
    except yaml.YAMLError as exc:
        raise TopologyRegistryValidationError(
            category="invalid_yaml",
            source_path=source_path,
            detail=str(exc),
        ) from exc

    if not isinstance(loaded, Mapping):
        raise TopologyRegistryValidationError(
            category="invalid_topology_shape",
            source_path=source_path,
            detail="top-level YAML node must be a mapping",
        )
    return loaded


def _detect_registry_version(raw: Mapping[str, Any]) -> int:
    raw_version = raw.get("version", raw.get("schema_version"))
    if raw_version is not None:
        return _normalize_version(raw_version)

    streams = raw.get("streams", ())
    if isinstance(streams, list):
        has_instances = any(
            isinstance(stream, Mapping) and "instances" in stream for stream in streams
        )
        return 2 if has_instances else 1
    return 1


def _normalize_version(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.startswith("v"):
            lowered = lowered[1:]
        if lowered.isdigit():
            return int(lowered)
    raise TopologyRegistryValidationError(
        category="unsupported_version_shape",
        source_path="<inline>",
        offending_key="version",
        detail=f"cannot parse version value {value!r}",
    )


def _validate_supported_version(
    *,
    version: int,
    rules: TopologyRegistryLoaderRulesV1,
    source_path: str,
) -> None:
    if version not in rules.supported_registry_versions:
        raise TopologyRegistryValidationError(
            category="unsupported_registry_version",
            source_path=source_path,
            offending_key="version",
            detail=(
                f"version {version} is not in supported versions "
                f"{tuple(rules.supported_registry_versions)}"
            ),
        )


def _canonicalize_registry(
    *,
    raw: Mapping[str, Any],
    source_path: str,
    input_version: int,
    default_env: str,
    default_cluster_id: str,
) -> CanonicalTopologyRegistry:
    streams_raw = raw.get("streams")
    if not isinstance(streams_raw, list):
        raise TopologyRegistryValidationError(
            category="invalid_streams_shape",
            source_path=source_path,
            offending_key="streams",
            detail="expected a list of stream entries",
        )

    if input_version >= 2:
        streams = _canonicalize_v1_streams(streams_raw=streams_raw, source_path=source_path)
    else:
        streams = _canonicalize_v0_streams(
            raw=raw,
            streams_raw=streams_raw,
            source_path=source_path,
            default_env=default_env,
            default_cluster_id=default_cluster_id,
        )

    streams_by_id: dict[str, CanonicalStream] = {}
    topic_index_by_scope: dict[tuple[str, str], dict[str, CanonicalTopicEntry]] = defaultdict(dict)
    for stream in streams:
        if stream.stream_id in streams_by_id:
            raise TopologyRegistryValidationError(
                category="duplicate_stream_id",
                source_path=source_path,
                offending_key=stream.stream_id,
                detail="stream_id must be unique across registry",
            )
        streams_by_id[stream.stream_id] = stream

        seen_scope_for_stream: set[tuple[str, str]] = set()
        for instance in stream.instances:
            scope = (instance.env, instance.cluster_id)
            if scope in seen_scope_for_stream:
                raise TopologyRegistryValidationError(
                    category="duplicate_instance_scope",
                    source_path=source_path,
                    offending_key=f"{stream.stream_id}:{scope[0]}:{scope[1]}",
                    detail="instances must be unique by (env, cluster_id) per stream",
                )
            seen_scope_for_stream.add(scope)

            scoped_topic_index = topic_index_by_scope[scope]
            for topic, topic_entry in instance.topic_index.items():
                if topic in scoped_topic_index:
                    raise TopologyRegistryValidationError(
                        category="duplicate_topic_index",
                        source_path=source_path,
                        offending_key=f"{scope[0]}:{scope[1]}:{topic}",
                        detail="duplicate topic_index key within (env, cluster_id) scope",
                    )
                scoped_topic_index[topic] = topic_entry

    routing_directory = _canonicalize_routing_directory(raw=raw, source_path=source_path)
    ownership_map = _canonicalize_ownership_map(raw=raw, source_path=source_path)

    return CanonicalTopologyRegistry(
        streams=tuple(streams),
        streams_by_id=streams_by_id,
        topic_index_by_scope=topic_index_by_scope,
        routing_directory=routing_directory,
        ownership_map=ownership_map,
    )


def _canonicalize_v0_streams(
    *,
    raw: Mapping[str, Any],
    streams_raw: list[Any],
    source_path: str,
    default_env: str,
    default_cluster_id: str,
) -> tuple[CanonicalStream, ...]:
    topic_index_raw = raw.get("topic_index", {})
    if not isinstance(topic_index_raw, Mapping):
        raise TopologyRegistryValidationError(
            category="invalid_topic_index_shape",
            source_path=source_path,
            offending_key="topic_index",
            detail="v0 registry expects top-level topic_index mapping",
        )

    topics_by_stream_id: dict[str, dict[str, CanonicalTopicEntry]] = defaultdict(dict)
    for topic, entry in sorted(topic_index_raw.items(), key=lambda x: str(x[0])):
        if not isinstance(entry, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_topic_index_entry",
                source_path=source_path,
                offending_key=str(topic),
                detail="topic_index entry must be an object",
            )
        stream_id = _require_non_empty_string(
            entry.get("stream_id"),
            source_path=source_path,
            category="invalid_topic_index_entry",
            offending_key=f"topic_index.{topic}.stream_id",
        )
        role = _require_non_empty_string(
            entry.get("role"),
            source_path=source_path,
            category="invalid_topic_index_entry",
            offending_key=f"topic_index.{topic}.role",
        )
        topics_by_stream_id[stream_id][str(topic)] = CanonicalTopicEntry(
            topic=str(topic),
            role=role,
            stream_id=stream_id,
            source_system=_optional_string(entry.get("source_system")),
        )

    streams: list[CanonicalStream] = []
    known_stream_ids: set[str] = set()
    for stream in streams_raw:
        if not isinstance(stream, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_stream_entry",
                source_path=source_path,
                detail="stream entry must be an object",
            )
        stream_id = _require_non_empty_string(
            stream.get("stream_id"),
            source_path=source_path,
            category="invalid_stream_entry",
            offending_key="streams[].stream_id",
        )
        known_stream_ids.add(stream_id)
        env = _optional_string(stream.get("env")) or default_env
        cluster_id = _optional_string(stream.get("cluster_id")) or default_cluster_id
        stream_topic_index = topics_by_stream_id.get(stream_id, {})

        stream_instance = CanonicalStreamInstance(
            env=env,
            cluster_id=cluster_id,
            topic_index=stream_topic_index,
            topics=_coerce_string_mapping(stream.get("topics", {})),
            shared_components=_coerce_mapping(stream.get("shared_components", {})),
            sources=_coerce_mapping_list(stream.get("sources", ())),
            sinks=_coerce_mapping_list(stream.get("sinks", ())),
            peak_window_policy=_coerce_optional_mapping(stream.get("peak_window_policy")),
        )

        streams.append(
            CanonicalStream(
                stream_id=stream_id,
                description=_optional_string(stream.get("description")),
                criticality_tier=_optional_string(stream.get("criticality_tier")),
                owners=_coerce_mapping(stream.get("owners", {})),
                instances=(stream_instance,),
            )
        )

    unknown_stream_refs = sorted(set(topics_by_stream_id) - known_stream_ids)
    if unknown_stream_refs:
        raise TopologyRegistryValidationError(
            category="unknown_stream_reference",
            source_path=source_path,
            offending_key=unknown_stream_refs[0],
            detail="topic_index refers to stream_id not present in streams[]",
        )
    return tuple(streams)


def _canonicalize_v1_streams(
    *,
    streams_raw: list[Any],
    source_path: str,
) -> tuple[CanonicalStream, ...]:
    streams: list[CanonicalStream] = []
    for stream in streams_raw:
        if not isinstance(stream, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_stream_entry",
                source_path=source_path,
                detail="stream entry must be an object",
            )
        stream_id = _require_non_empty_string(
            stream.get("stream_id"),
            source_path=source_path,
            category="invalid_stream_entry",
            offending_key="streams[].stream_id",
        )
        instances_raw = stream.get("instances", ())
        if not isinstance(instances_raw, list):
            raise TopologyRegistryValidationError(
                category="invalid_instances_shape",
                source_path=source_path,
                offending_key=f"streams[{stream_id}].instances",
                detail="instances must be a list for v1/v2 shape",
            )

        instances: list[CanonicalStreamInstance] = []
        for instance in instances_raw:
            if not isinstance(instance, Mapping):
                raise TopologyRegistryValidationError(
                    category="invalid_instance_entry",
                    source_path=source_path,
                    offending_key=f"streams[{stream_id}].instances[]",
                    detail="instance entry must be an object",
                )
            env = _require_non_empty_string(
                instance.get("env"),
                source_path=source_path,
                category="invalid_instance_entry",
                offending_key=f"streams[{stream_id}].instances[].env",
            )
            cluster_id = _require_non_empty_string(
                instance.get("cluster_id"),
                source_path=source_path,
                category="invalid_instance_entry",
                offending_key=f"streams[{stream_id}].instances[].cluster_id",
            )
            topic_index = _canonicalize_instance_topic_index(
                stream_id=stream_id,
                topic_index_raw=instance.get("topic_index", {}),
                source_path=source_path,
                scope=(env, cluster_id),
            )
            instances.append(
                CanonicalStreamInstance(
                    env=env,
                    cluster_id=cluster_id,
                    topic_index=topic_index,
                    topics=_coerce_string_mapping(instance.get("topics", {})),
                    shared_components=_coerce_mapping(instance.get("shared_components", {})),
                    sources=_coerce_mapping_list(instance.get("sources", ())),
                    sinks=_coerce_mapping_list(instance.get("sinks", ())),
                    peak_window_policy=_coerce_optional_mapping(instance.get("peak_window_policy")),
                )
            )

        streams.append(
            CanonicalStream(
                stream_id=stream_id,
                description=_optional_string(stream.get("description")),
                criticality_tier=_optional_string(stream.get("criticality_tier")),
                owners=_coerce_mapping(stream.get("owners", {})),
                instances=tuple(instances),
            )
        )
    return tuple(streams)


def _canonicalize_instance_topic_index(
    *,
    stream_id: str,
    topic_index_raw: Any,
    source_path: str,
    scope: tuple[str, str],
) -> dict[str, CanonicalTopicEntry]:
    if not isinstance(topic_index_raw, Mapping):
        raise TopologyRegistryValidationError(
            category="invalid_topic_index_shape",
            source_path=source_path,
            offending_key=f"{scope[0]}:{scope[1]}",
            detail="topic_index must be an object",
        )

    scoped_topics: dict[str, CanonicalTopicEntry] = {}
    for topic, entry in sorted(topic_index_raw.items(), key=lambda x: str(x[0])):
        if not isinstance(entry, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_topic_index_entry",
                source_path=source_path,
                offending_key=f"{scope[0]}:{scope[1]}:{topic}",
                detail="topic_index entry must be an object",
            )
        entry_stream_id = _optional_string(entry.get("stream_id")) or stream_id
        if entry_stream_id != stream_id:
            raise TopologyRegistryValidationError(
                category="topic_index_stream_mismatch",
                source_path=source_path,
                offending_key=f"{scope[0]}:{scope[1]}:{topic}",
                detail=(
                    f"entry stream_id={entry_stream_id!r} does not match "
                    f"parent stream {stream_id!r}"
                ),
            )
        role = _require_non_empty_string(
            entry.get("role"),
            source_path=source_path,
            category="invalid_topic_index_entry",
            offending_key=f"{scope[0]}:{scope[1]}:{topic}.role",
        )
        scoped_topics[str(topic)] = CanonicalTopicEntry(
            topic=str(topic),
            role=role,
            stream_id=stream_id,
            source_system=_optional_string(entry.get("source_system")),
        )
    return scoped_topics


def _canonicalize_routing_directory(
    *,
    raw: Mapping[str, Any],
    source_path: str,
) -> dict[str, RoutingDirectoryEntry]:
    raw_directory = raw.get("routing_directory", ())
    if raw_directory in (None, {}):
        raw_directory = ()
    if not isinstance(raw_directory, list | tuple):
        raise TopologyRegistryValidationError(
            category="invalid_routing_directory_shape",
            source_path=source_path,
            offending_key="routing_directory",
            detail="routing_directory must be a list",
        )

    directory: dict[str, RoutingDirectoryEntry] = {}
    for item in raw_directory:
        if not isinstance(item, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_routing_directory_entry",
                source_path=source_path,
                detail="routing_directory entry must be an object",
            )
        routing_key = _require_non_empty_string(
            item.get("routing_key"),
            source_path=source_path,
            category="invalid_routing_directory_entry",
            offending_key="routing_directory[].routing_key",
        )
        if routing_key in directory:
            raise TopologyRegistryValidationError(
                category="duplicate_routing_key",
                source_path=source_path,
                offending_key=routing_key,
                detail="routing_directory contains duplicate routing_key entries",
            )
        directory[routing_key] = RoutingDirectoryEntry(
            routing_key=routing_key,
            owning_team_id=_require_non_empty_string(
                item.get("owning_team_id"),
                source_path=source_path,
                category="invalid_routing_directory_entry",
                offending_key=f"routing_directory[{routing_key}].owning_team_id",
            ),
            owning_team_name=_require_non_empty_string(
                item.get("owning_team_name"),
                source_path=source_path,
                category="invalid_routing_directory_entry",
                offending_key=f"routing_directory[{routing_key}].owning_team_name",
            ),
            support_channel=_optional_string(item.get("support_channel")),
            escalation_policy_ref=_optional_string(item.get("escalation_policy_ref")),
            service_now_assignment_group=_optional_string(item.get("service_now_assignment_group")),
        )
    return directory


def _canonicalize_ownership_map(
    *,
    raw: Mapping[str, Any],
    source_path: str,
) -> CanonicalOwnershipMap:
    ownership_raw = raw.get("ownership_map", {})
    if ownership_raw in (None, []):
        ownership_raw = {}
    if not isinstance(ownership_raw, Mapping):
        raise TopologyRegistryValidationError(
            category="invalid_ownership_map_shape",
            source_path=source_path,
            offending_key="ownership_map",
            detail="ownership_map must be an object",
        )

    consumer_group_owners = tuple(
        sorted(
            _coerce_consumer_group_owners(
                ownership_raw.get("consumer_group_owners", ()),
                source_path=source_path,
            ),
            key=lambda x: (x.env, x.cluster_id, x.group),
        )
    )
    topic_owners = tuple(
        sorted(
            _coerce_topic_owners(
                ownership_raw.get("topic_owners", ()),
                source_path=source_path,
            ),
            key=lambda x: (x.env, x.cluster_id, x.topic),
        )
    )
    stream_default_owner = tuple(
        sorted(
            _coerce_stream_default_owners(
                ownership_raw.get("stream_default_owner", ()),
                source_path=source_path,
            ),
            key=lambda x: (x.stream_id, x.env, x.cluster_id),
        )
    )
    platform_default = _optional_string(ownership_raw.get("platform_default"))
    return CanonicalOwnershipMap(
        consumer_group_owners=consumer_group_owners,
        topic_owners=topic_owners,
        stream_default_owner=stream_default_owner,
        platform_default=platform_default,
    )


def _coerce_consumer_group_owners(
    raw_entries: Any,
    *,
    source_path: str,
) -> list[ConsumerGroupOwnerEntry]:
    if not isinstance(raw_entries, list | tuple):
        raise TopologyRegistryValidationError(
            category="invalid_consumer_group_owners_shape",
            source_path=source_path,
            offending_key="ownership_map.consumer_group_owners",
            detail="consumer_group_owners must be a list",
        )
    entries: list[ConsumerGroupOwnerEntry] = []
    for item in raw_entries:
        if not isinstance(item, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_consumer_group_owner_entry",
                source_path=source_path,
                detail="consumer_group_owner entry must be an object",
            )
        match = _coerce_mapping(item.get("match", {}))
        entries.append(
            ConsumerGroupOwnerEntry(
                env=_require_non_empty_string(
                    match.get("env"),
                    source_path=source_path,
                    category="invalid_consumer_group_owner_entry",
                    offending_key="ownership_map.consumer_group_owners[].match.env",
                ),
                cluster_id=_require_non_empty_string(
                    match.get("cluster_id"),
                    source_path=source_path,
                    category="invalid_consumer_group_owner_entry",
                    offending_key="ownership_map.consumer_group_owners[].match.cluster_id",
                ),
                group=_require_non_empty_string(
                    match.get("group"),
                    source_path=source_path,
                    category="invalid_consumer_group_owner_entry",
                    offending_key="ownership_map.consumer_group_owners[].match.group",
                ),
                routing_key=_require_non_empty_string(
                    item.get("routing_key"),
                    source_path=source_path,
                    category="invalid_consumer_group_owner_entry",
                    offending_key="ownership_map.consumer_group_owners[].routing_key",
                ),
                source=_optional_string(item.get("source")),
                confidence=_coerce_optional_float(item.get("confidence")),
                reason_codes=_coerce_string_tuple(item.get("reason_codes", ())),
            )
        )
    return entries


def _coerce_topic_owners(raw_entries: Any, *, source_path: str) -> list[TopicOwnerEntry]:
    if not isinstance(raw_entries, list | tuple):
        raise TopologyRegistryValidationError(
            category="invalid_topic_owners_shape",
            source_path=source_path,
            offending_key="ownership_map.topic_owners",
            detail="topic_owners must be a list",
        )
    entries: list[TopicOwnerEntry] = []
    for item in raw_entries:
        if not isinstance(item, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_topic_owner_entry",
                source_path=source_path,
                detail="topic_owner entry must be an object",
            )
        match = _coerce_mapping(item.get("match", {}))
        entries.append(
            TopicOwnerEntry(
                env=_require_non_empty_string(
                    match.get("env"),
                    source_path=source_path,
                    category="invalid_topic_owner_entry",
                    offending_key="ownership_map.topic_owners[].match.env",
                ),
                cluster_id=_require_non_empty_string(
                    match.get("cluster_id"),
                    source_path=source_path,
                    category="invalid_topic_owner_entry",
                    offending_key="ownership_map.topic_owners[].match.cluster_id",
                ),
                topic=_require_non_empty_string(
                    match.get("topic"),
                    source_path=source_path,
                    category="invalid_topic_owner_entry",
                    offending_key="ownership_map.topic_owners[].match.topic",
                ),
                routing_key=_require_non_empty_string(
                    item.get("routing_key"),
                    source_path=source_path,
                    category="invalid_topic_owner_entry",
                    offending_key="ownership_map.topic_owners[].routing_key",
                ),
                source=_optional_string(item.get("source")),
                confidence=_coerce_optional_float(item.get("confidence")),
                reason_codes=_coerce_string_tuple(item.get("reason_codes", ())),
            )
        )
    return entries


def _coerce_stream_default_owners(
    raw_entries: Any,
    *,
    source_path: str,
) -> list[StreamDefaultOwnerEntry]:
    if not isinstance(raw_entries, list | tuple):
        raise TopologyRegistryValidationError(
            category="invalid_stream_default_owner_shape",
            source_path=source_path,
            offending_key="ownership_map.stream_default_owner",
            detail="stream_default_owner must be a list",
        )
    entries: list[StreamDefaultOwnerEntry] = []
    for item in raw_entries:
        if not isinstance(item, Mapping):
            raise TopologyRegistryValidationError(
                category="invalid_stream_default_owner_entry",
                source_path=source_path,
                detail="stream_default_owner entry must be an object",
            )
        match = _coerce_mapping(item.get("match", {}))
        entries.append(
            StreamDefaultOwnerEntry(
                stream_id=_require_non_empty_string(
                    match.get("stream_id"),
                    source_path=source_path,
                    category="invalid_stream_default_owner_entry",
                    offending_key="ownership_map.stream_default_owner[].match.stream_id",
                ),
                env=_require_non_empty_string(
                    match.get("env"),
                    source_path=source_path,
                    category="invalid_stream_default_owner_entry",
                    offending_key="ownership_map.stream_default_owner[].match.env",
                ),
                cluster_id=_require_non_empty_string(
                    match.get("cluster_id"),
                    source_path=source_path,
                    category="invalid_stream_default_owner_entry",
                    offending_key="ownership_map.stream_default_owner[].match.cluster_id",
                ),
                routing_key=_require_non_empty_string(
                    item.get("routing_key"),
                    source_path=source_path,
                    category="invalid_stream_default_owner_entry",
                    offending_key="ownership_map.stream_default_owner[].routing_key",
                ),
                source=_optional_string(item.get("source")),
                confidence=_coerce_optional_float(item.get("confidence")),
                reason_codes=_coerce_string_tuple(item.get("reason_codes", ())),
            )
        )
    return entries


def _validate_ownership_matrix(
    *,
    registry: CanonicalTopologyRegistry,
    source_path: str,
) -> None:
    seen_consumer_group_keys: set[tuple[str, str, str]] = set()
    for item in registry.ownership_map.consumer_group_owners:
        key = (item.env, item.cluster_id, item.group)
        if key in seen_consumer_group_keys:
            raise TopologyRegistryValidationError(
                category="duplicate_consumer_group_owner",
                source_path=source_path,
                offending_key=f"{item.env}:{item.cluster_id}:{item.group}",
                detail="duplicate consumer-group ownership key",
            )
        seen_consumer_group_keys.add(key)

    valid_routing_keys = set(registry.routing_directory.keys())
    referenced_routing_keys = {
        item.routing_key for item in registry.ownership_map.consumer_group_owners
    } | {item.routing_key for item in registry.ownership_map.topic_owners} | {
        item.routing_key for item in registry.ownership_map.stream_default_owner
    }
    if registry.ownership_map.platform_default is not None:
        referenced_routing_keys.add(registry.ownership_map.platform_default)

    for routing_key in sorted(referenced_routing_keys):
        if routing_key not in valid_routing_keys:
            raise TopologyRegistryValidationError(
                category="missing_routing_key_reference",
                source_path=source_path,
                offending_key=routing_key,
                detail=(
                    "routing_key is referenced by ownership map but missing "
                    "in routing_directory"
                ),
            )


def _require_non_empty_string(
    value: Any,
    *,
    source_path: str,
    category: str,
    offending_key: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopologyRegistryValidationError(
            category=category,
            source_path=source_path,
            offending_key=offending_key,
            detail="expected non-empty string",
        )
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    return str(value)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        return {}
    return {str(k): v for k, v in value.items()}


def _coerce_optional_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    return {str(k): v for k, v in value.items()}


def _coerce_mapping_list(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        return ()
    mappings: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            mappings.append({str(k): v for k, v in item.items()})
    return tuple(mappings)


def _coerce_string_mapping(value: Any) -> dict[str, str]:
    if value is None or not isinstance(value, Mapping):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _coerce_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(x) for x in value)
    return ()


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

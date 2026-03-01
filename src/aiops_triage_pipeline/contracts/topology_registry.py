"""TopologyRegistryLoaderRulesV1 — rules governing topology registry loading and validation."""

from typing import Literal

from pydantic import BaseModel


class TopologyRegistryLoaderRulesV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    supported_registry_versions: tuple[int, ...] = (1, 2)
    prefer_v2_format: bool = True
    routing_key_required: bool = True
    fail_on_unknown_topic_role: bool = False
    unknown_routing_key_fallback: str = "OWN::Streaming::KafkaPlatform::Ops"
    cluster_id_transform: str = "NONE"

"""ATDD support data for Story 1.4 red-phase tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopologyScope:
    env: str
    cluster_id: str
    topic: str


def build_primary_scope() -> TopologyScope:
    return TopologyScope(env="prod", cluster_id="cluster-a", topic="orders")

"""LocalDevContractV1 — integration modes for local development environment."""

from typing import Literal

from pydantic import BaseModel

_IntegrationMode = Literal["OFF", "LOG", "MOCK", "LIVE"]


class LocalDevIntegrationModes(BaseModel, frozen=True):
    prometheus: _IntegrationMode = "MOCK"
    kafka_consumer: _IntegrationMode = "MOCK"
    kafka_producer: _IntegrationMode = "MOCK"
    pagerduty: _IntegrationMode = "LOG"
    slack: _IntegrationMode = "LOG"
    servicenow: _IntegrationMode = "OFF"
    llm: _IntegrationMode = "MOCK"
    redis: _IntegrationMode = "LIVE"
    postgres: _IntegrationMode = "LIVE"


class LocalDevContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    use_testcontainers: bool = False
    integration_modes: LocalDevIntegrationModes

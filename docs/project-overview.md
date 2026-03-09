# Project Overview

## Project

- Name: `aiops-triage-pipeline`
- Type: backend monolith
- Primary language: Python
- Primary objective: detect telemetry anomalies, build durable case artifacts, and emit downstream operational decisions/events.

## Executive Summary

The project implements an event-driven AIOps triage flow with deterministic stage processing, contract-first payload definitions, and durability boundaries around external side effects. Runtime reliability is centered around outbox state transitions, retry-state persistence for ServiceNow linkage, and controlled integration modes.

## High-Level Tech Stack

- Python 3.13 + asyncio
- Pydantic contracts/models
- PostgreSQL + Redis + MinIO
- Kafka event publication
- Prometheus ingestion + OTLP telemetry export
- Docker Compose local dependency topology

## Repository Structure Classification

- repository_type: monolith
- parts_count: 1 (`core`)
- root: `/home/sas/workspace/aiops`

## Detailed Documentation

- [Architecture](./architecture.md)
- [Source Tree Analysis](./source-tree-analysis.md)
- [Technology Stack](./technology-stack.md)
- [API Contracts](./api-contracts.md)
- [Data Models](./data-models.md)
- [Development Guide](./development-guide.md)
- [Deployment Guide](./deployment-guide.md)
- [Contribution Guide](./contribution-guide.md)

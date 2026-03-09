# Project Documentation Index

## Quick Reference

- **Tech Stack:** Python 3.13, Pydantic, SQLAlchemy, Kafka, PostgreSQL, Redis, MinIO, OpenTelemetry
- **Entry Point:** `src/aiops_triage_pipeline/__main__.py`
- **Architecture Pattern:** Contract-first stage pipeline with durable side-effect boundaries

## Getting Started

1. Start with [Project Overview](./project-overview.md).
2. Read [Architecture](./architecture.md) for system topology and stage flow.
3. Use [API Contracts](./api-contracts.md) and [Data Models](./data-models.md) before implementing changes.
4. Follow [Development Guide](./development-guide.md) for local setup and regression posture.

## Documentation

### Getting Started

| Document | Description |
|----------|-------------|
| [Local Development](./local-development.md) | Environment setup, run commands, Docker troubleshooting |
| [Development Guide](./development-guide.md) | Developer workflows, tooling, and regression posture |
| [Deployment Guide](./deployment-guide.md) | Deployment configuration and operational runbook |

### Architecture and Design

| Document | Description |
|----------|-------------|
| [Architecture](./architecture.md) | System topology, stage flow, component overview, and deployment architecture |
| [Architecture Patterns](./architecture-patterns.md) | Design patterns and structural decisions |
| [Technology Stack](./technology-stack.md) | Full technology stack reference |
| [Component Inventory](./component-inventory.md) | Component breakdown and responsibilities |
| [Project Structure](./project-structure.md) | Source tree layout and module responsibilities |

### Reference

| Document | Description |
|----------|-------------|
| [Contracts](./contracts.md) | Frozen contract catalog, validation rules, and compatibility policy |
| [API Contracts](./api-contracts.md) | API contract schemas and usage reference |
| [Data Models](./data-models.md) | Domain payload model reference |
| [Schema Evolution Strategy](./schema-evolution-strategy.md) | Versioning procedures for Kafka events, CaseFile schemas, and policies |

### Contributing

| Document | Description |
|----------|-------------|
| [Contribution Guide](./contribution-guide.md) | Contribution standards, change guidelines, and review expectations |

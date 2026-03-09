# Project Documentation Index

## Project Overview

- **Type:** monolith
- **Primary Language:** Python
- **Architecture:** Layered backend with event-driven pipeline and durable outbox boundary

## Quick Reference

- **Tech Stack:** Python 3.13, Pydantic, SQLAlchemy, Kafka, PostgreSQL, Redis, MinIO, OpenTelemetry
- **Entry Point:** `src/aiops_triage_pipeline/__main__.py`
- **Architecture Pattern:** Contract-first stage pipeline with durable side-effect boundaries

## Generated Documentation

- [Project Overview](./project-overview.md)
- [Architecture](./architecture.md)
- [Source Tree Analysis](./source-tree-analysis.md)
- [Technology Stack](./technology-stack.md)
- [Architecture Patterns](./architecture-patterns.md)
- [Component Inventory](./component-inventory.md)
- [Development Guide](./development-guide.md)
- [Deployment Guide](./deployment-guide.md)
- [Contribution Guide](./contribution-guide.md)
- [API Contracts](./api-contracts.md)
- [Data Models](./data-models.md)
- [Comprehensive Analysis](./comprehensive-analysis-core.md)
- [Project Structure](./project-structure.md)
- [Project Parts Metadata](./project-parts-metadata.md)
- [Existing Documentation Inventory](./existing-documentation-inventory.md)
- [User Context](./user-provided-context.md)
- [Critical Folders Summary](./critical-folders-summary.md)

## Existing Documentation

- [Contracts](./contracts.md) - Frozen contract catalog and validation checks
- [Local Development](./local-development.md) - Environment setup and run/test workflows
- [Schema Evolution Strategy](./schema-evolution-strategy.md) - Versioning and migration strategy notes

## Getting Started

1. Start with [Project Overview](./project-overview.md).
2. Read [Architecture](./architecture.md) and [Source Tree Analysis](./source-tree-analysis.md).
3. Use [API Contracts](./api-contracts.md) and [Data Models](./data-models.md) before implementing changes.
4. Follow [Development Guide](./development-guide.md) for local setup and regression checks.

## AI-Assisted Development Guidance

Use this file (`docs/index.md`) as the primary context entrypoint for brownfield planning or implementation workflows.

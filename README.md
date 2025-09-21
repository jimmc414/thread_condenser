# Thread Condenser

Thread Condenser ingests Slack, Microsoft Teams, and Outlook conversations and turns them into structured, auditable briefs of decisions, risks, actions, and open questions with provenance for every extracted item.

## Table of contents
- [Overview](#overview)
- [Core capabilities](#core-capabilities)
- [System architecture](#system-architecture)
- [Request lifecycle](#request-lifecycle)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [Testing and quality](#testing-and-quality)
- [Operational considerations](#operational-considerations)
- [Further reading](#further-reading)

## Overview
Thread Condenser provides a unified pipeline that normalizes multi-platform chat or email threads, orchestrates large language model (LLM) passes, and publishes condensed briefs back to the originating channel or mailbox. It is built for multi-tenant deployments and emphasises traceability, provenance, and human-in-the-loop confirmation before information is synced to downstream tools.

## Core capabilities
- **Multi-platform ingestion** – adapters for Slack, Microsoft Teams, and Outlook normalize payloads into a canonical schema, including metadata such as deep links and user directory information.
- **Structured summarization** – segments are token-aware, extraction is driven by a constrained JSON prompt, and ranking applies platform-specific agreement signals before publishing.
- **Provenance-first storage** – briefs, evidence, and changelogs are persisted with canonical message identifiers so every surfaced item can be audited later.
- **Connector hooks** – async tasks integrate with ticketing, documentation, and calendar systems through a pluggable connector registry for downstream syncing after confirmation.

## System architecture
The application exposes a FastAPI service that mounts platform-specific routers for Slack, Teams, and Outlook alongside REST APIs under `/v1`. Celery workers coordinate ingestion, LLM orchestration, and publishing, sharing a Redis-backed broker and result store configured in `app/workers/celery_app.py`. PostgreSQL (with pgvector) stores normalized workspace, thread, message, and brief entities managed through SQLAlchemy models in `app/models.py`. Docker Compose provisions the API, worker, beat scheduler, Postgres, and Redis for local development.

## Request lifecycle
1. A platform adapter serializes a thread reference and enqueues a Celery task via the platform registry.
2. The ingest stage ensures workspace, channel, user, and thread records exist and persists raw messages with canonical identifiers and metadata.
3. Preprocessing cleans noise, builds reply graphs, and prepares language metadata before token-aware segmentation groups content into model-sized chunks.
4. The extraction stage calls the configured LLM using a strict JSON schema prompt, guaranteeing every item carries quotes and message IDs.
5. Items are re-scored with platform reactions, enriched with permalinks, and written to the briefs table; adapters then publish interactive cards or actionable mail back to the originating surface.

## Repository layout
```
app/                  FastAPI application, Celery workers, and pipeline modules
app/api/              REST endpoints exposed under /v1
app/platforms/        Platform adapters and registry for Slack, Teams, Outlook
app/pipeline/         Ingest, preprocess, segmentation, extraction, ranking, provenance
app/connectors/       Stubs for outbound sync targets (Jira, Linear, Notion, etc.)
app/workers/          Celery app definition and asynchronous tasks
app/migrations/       Alembic database migrations
app/prompts/          Prompt templates for LLM calls
app/llm/              LLM client abstractions and token counters
architecture.md       High-level architecture reference
implementation.md     Detailed implementation design and TODOs
requirements.md       Product requirements document
```

## Prerequisites
- Docker and Docker Compose (for the default local development flow).
- Python 3.11 (runtime for containers and local tooling).
- An OpenAI-compatible API key (default LLM provider).
- Slack and Microsoft 365 application credentials when exercising real platform integrations.

## Local development
1. Copy the example environment file and adjust secrets:
   ```bash
   cp .env.example .env
   ```
2. Start the full stack (API, worker, beat, Postgres, Redis):
   ```bash
   make run
   ```
3. Apply the latest database migrations once the containers are healthy:
   ```bash
   make migrate
   ```
4. The FastAPI app is now available on http://localhost:8080 with platform webhooks and `/v1` APIs enabled.

To develop without Docker you can install dependencies from `requirements.txt`, provision PostgreSQL and Redis manually, and run `uvicorn app.main:app --reload` plus `celery -A app.workers.celery_app.celery_app worker` from separate terminals.

## Configuration
All configuration is driven by environment variables parsed via `pydantic-settings` in `app/config.py`. Key settings include database DSNs, Redis URL, Slack and Microsoft credentials, LLM provider/model selection, and promotion thresholds. The `.env.example` file documents the expected keys for local development. Values are loaded automatically when the process starts thanks to the module-level singleton in `app/config.py`.

## Running the app
- **Manual condensation** – POST `/v1/condense` with a `platform` and serialized `thread_ref` to enqueue processing; poll `/v1/briefs/{run_id}` to retrieve the resulting brief.
- **Platform webhooks** – Slack, Teams, and Outlook routers are mounted automatically; refer to `requirements.md` for scopes and webhook registration specifics.
- **Microsoft Graph notifications** – `/v1/graph/notifications` handles validation tokens and converts change notifications into Celery jobs for Teams and Outlook threads.

## Testing and quality
- Run unit tests with pytest:
  ```bash
  pytest
  ```
  A smoke test for the segmentation pipeline lives in `tests/test_segment.py`.
- Format Python modules with Black:
  ```bash
  make fmt
  ```
  The formatter is configured to run against the `app` package.
- Additional regression and evaluation guidance is captured in `implementation.md` and `architecture.md` sections on testing and measurement.

## Operational considerations
- **Logging** – Structured JSON logs are emitted to stdout by default via `app.logging.setup_logging()`.
- **Background work** – The `webhooks` queue handles user-triggered condensation, while additional queues (`sync`, `digest`) are provisioned for connectors and scheduled jobs.
- **Data retention** – Messages, items, briefs, changelogs, and cost records persist in Postgres using the models defined in `app/models.py`; consult `requirements.md` for retention requirements.
- **Deployment** – The provided Dockerfile builds a production image on Python 3.11 that installs requirements and launches Uvicorn; ECS Fargate (API + workers) with RDS and ElastiCache is the recommended deployment target outlined in `architecture.md`.

## Further reading
- [`architecture.md`](architecture.md) – system design, integration choices, runbook excerpts.
- [`implementation.md`](implementation.md) – end-to-end implementation plan and TODOs.
- [`requirements.md`](requirements.md) – functional and non-functional requirements.

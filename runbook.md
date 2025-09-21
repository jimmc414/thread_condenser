# Thread Condenser Runbook

This runbook covers day-to-day operations and incident response procedures for the Thread Condenser service. It assumes familiarity with Slack, Microsoft 365, and the supporting AWS infrastructure described in `architecture.md`.

## 1. Service overview
| Component | Responsibility | Key references |
|-----------|----------------|----------------|
| FastAPI service (`app/main.py`) | Hosts REST APIs, Slack/Teams/Outlook webhooks, and admin endpoints. | Docker container started via `uvicorn app.main:app`. |
| Celery workers (`app/workers/`) | Execute ingestion, LLM orchestration, publishing, and connector tasks. | Queues: `default`, `webhooks`, `sync`, `digest`. |
| PostgreSQL (pgvector) | Persists tenants, workspaces, threads, messages, items, briefs, changelogs, sync links, and audit data. | SQLAlchemy models in `app/models.py`. |
| Redis | Acts as Celery broker and cache for background task coordination. | Connection configured through `REDIS_URL`. |
| Platform adapters (`app/platforms/`) | Normalize and publish Slack, Teams, Outlook interactions. | Registered via `app/platforms/registry.py`. |

Local development uses Docker Compose to provision the API, worker, beat scheduler, Postgres, and Redis containers; production deploys API and worker services separately on ECS Fargate behind an Application Load Balancer (ALB) with RDS Postgres and ElastiCache Redis as managed dependencies.

## 2. Environments and deployment cadence
- **Environments** – dev, staging, and production live in isolated AWS accounts. Production follows blue/green deployments for the API and workers with one-click rollback support.
- **Release cadence** – deploy to staging daily after automated tests, then promote to production during regional business hours following successful smoke tests.
- **Images** – Dockerfile builds a Python 3.11 image, installs `requirements.txt`, copies application code, and launches Uvicorn. Tag images with `git sha` and push to your registry before updating ECS task definitions.

## 3. Routine operations
### 3.1 Start-of-shift checklist
1. Verify all ECS services (API, worker, beat) are healthy and desired count matches running count.
2. Confirm Celery queues (`default`, `webhooks`, `sync`, `digest`) are draining within expected latency.
3. Spot-check CloudWatch dashboards for latency (P50/P95) and error rate per stage (ingest, extract, publish).
4. Review overnight alerts for cost threshold, queue stagnation, or provider outages.

### 3.2 Deploying a new release
1. Build and push the Docker image:
   ```bash
   docker build -t <registry>/thread-condenser:<git-sha> .
   docker push <registry>/thread-condenser:<git-sha>
   ```
2. Run database migrations in the staging environment:
   ```bash
   docker compose exec api alembic upgrade head  # or use make migrate locally
   ```
3. Update the staging ECS task definition (API + worker) with the new image and deploy via blue/green.
4. Execute smoke tests:
   - Trigger `/v1/condense` against a known staging thread reference.
   - Confirm the resulting brief posts to Slack and is persisted in Postgres.
5. Promote the release to production using blue/green; monitor metrics for 30 minutes before shifting all traffic.
6. Roll back by redeploying the prior task definition if latency, error rate, or spend alerts fire.

### 3.3 Database maintenance
- **Migrations** – use Alembic revisions stored in `app/migrations/`. Apply with `make migrate` (Docker) or `alembic upgrade head` (direct).
- **Backups** – RDS snapshots run daily; verify completion and retention weekly. For dev/staging Docker Compose, rely on local volume snapshots.
- **Vector extension** – ensure `pgvector` is installed in production by running `CREATE EXTENSION IF NOT EXISTS vector;` once per cluster.

### 3.4 Secret rotation
- Slack, Teams, Outlook, and OpenAI credentials live in AWS Secrets Manager. Rotate quarterly or on credential exposure. Update ECS task definitions to pull the new secret versions.
- Regenerate `APP_SECRET` when rotating JWT signing keys; restart API pods to reload configuration.

## 4. Monitoring and alerting
- **Metrics** – track end-to-card latency (P50/P95) per stage, error rates, token and USD spend, extraction precision/recall, confirmation rates, and platform-specific success metrics.
- **Tracing** – propagate correlation IDs from entrypoint payloads through Celery tasks and provider calls to connectors for distributed tracing.
- **Logs** – JSON logs include timestamps, log level, logger name, and message; message bodies are excluded for privacy. Forward to centralized log storage and retain for at least 30 days.
- **Alerts** – configure SLO burn alerts, queue depth stagnation, provider outages, and cost threshold breaches. Suppress duplicates by grouping on platform and workspace.

## 5. Incident response playbooks
### 5.1 Queue backlog spike
**Symptoms**: Celery queues show rising depth, delayed Slack/Teams postings, or `/v1/briefs` returning `404` for longer than expected.

**Actions**:
1. Check worker autoscaling—ensure sufficient tasks are running; scale out ECS workers if queue depth exceeds threshold.
2. Inspect the dead-letter queue for poison messages; replay after fixing the underlying issue.
3. Review LLM provider status and throttle settings; heavy rate limiting can back up extraction jobs. Reduce throughput or route to secondary provider.
4. Validate Redis health and network connectivity; restart workers if connections are stuck.

### 5.2 Slack 3-second acknowledgement failures
**Symptoms**: Slack reports timeout retries, slash commands respond slowly, or the Slack health dashboard shows failed acknowledgements.

**Actions**:
1. Confirm the FastAPI service can return 200 responses within 300 ms for Slack webhooks; check API pod CPU/memory and auto-scale if saturated.
2. Ensure the Slack adapter immediately enqueues work without blocking on long-running tasks; investigate recent changes that might delay acknowledgement.
3. If Celery is down, temporarily post a manual response to Slack indicating degraded service and prioritize restoring queue processing.
4. Once resolved, replay failed Slack events from the Slack admin dashboard if necessary.

### 5.3 Microsoft Graph notifications stale or missing
**Symptoms**: Teams/Outlook threads are not processed, Graph subscription expiry alerts trigger, or webhook handler receives no notifications.

**Actions**:
1. Inspect subscription expiry timestamps in the `graph_subscriptions` table; renew subscriptions approaching the 4230-minute limit.
2. Confirm `GRAPH_NOTIFICATION_SECRET` and webhook URLs match the registered values; misconfiguration causes validation failures.
3. Trigger a manual delta sync using `trigger_condense("msteams", ...)` or Outlook equivalents to catch up.
4. If Graph is degraded, fall back to periodic delta polling and notify admins of the reduced freshness.

### 5.4 Elevated hallucination or accuracy regressions
**Symptoms**: Users reject a high percentage of items, or monitoring flags extraction precision below 0.85.

**Actions**:
1. Check recent prompt or model version changes; roll back to the previous prompt (`app/prompts/extraction.md`) or model setting if needed.
2. Lower model temperature or increase promotion thresholds to reduce spurious items.
3. Review the golden thread regression suite results; rerun evaluations with `run_id` tracking to isolate regressions.
4. Engage prompt/ML owners to add few-shot examples or adjust extraction verbs allowlists.

### 5.5 LLM provider outage or rate limits
**Symptoms**: Extraction tasks fail with provider errors, token spend flatlines, or fallback routing triggers.

**Actions**:
1. Switch to the secondary LLM provider configured in settings; update `LLM_PROVIDER` and `OPENAI_MODEL` (or equivalents) via Secrets Manager and restart workers.
2. Reduce concurrency by pausing non-critical queues (`sync`, `digest`) to preserve capacity for `webhooks`.
3. Communicate status to users via Slack/Teams announcement cards and include expected recovery timelines.
4. After provider recovery, reprocess affected threads by replaying Celery jobs.

## 6. Data management
- **Provenance** – Every item stores canonical message IDs and quotes; ensure retention policies respect workspace-specific requirements. Items remain auditable even if raw messages expire.
- **Exports** – Registry exports and nightly digests run off the `digest` queue. Monitor for failures and requeue jobs as needed.
- **Deletion** – Honor workspace deletion requests within 7 days. Soft-delete threads and purge associated items, evidence, sync links, and audit logs as required.

## 7. Disaster recovery
- RDS is configured for Multi-AZ with daily encrypted snapshots; test restoration quarterly.
- Application containers are stateless and can be rebuilt from the Docker image; store infrastructure definitions in Terraform for rapid redeployment.
- Maintain runbooks for rotating Slack, Teams, and Outlook credentials if compromised; revoke tokens and regenerate secrets immediately.

## 8. Communication protocols
- Major incidents: page the on-call engineer, notify the #tc-ops Slack channel, and update the status page within 15 minutes.
- Post-incident review: schedule within 3 business days, document root cause, remediation, and follow-up tasks.
- Planned maintenance: announce at least 48 hours in advance to affected tenants and include expected downtime or degradation windows.

## 9. References
- `README.md` – high-level overview, setup, and developer workflow.
- `architecture.md` – architecture, integration details, and detailed failure mode analysis.
- `implementation.md` – in-depth implementation plan, TODOs, and evaluation strategy.
- `requirements.md` – functional and non-functional requirements plus edge cases.

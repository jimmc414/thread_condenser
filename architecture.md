# architecture.md

Product: Thread Condenser
Purpose: Convert long Slack, Microsoft Teams, and Outlook threads into auditable briefs (decisions, risks, actions, open questions) with provenance.

---

## 1. Architecture overview

- Pattern: Event‑driven, async processing with human‑in‑the‑loop.
- Control plane: REST APIs, auth, config, admin.
- Data plane: Ingest, preprocess, LLM orchestration, extraction, ranking, sync.
- Tenancy: Multi‑tenant with hard isolation at data layer and soft isolation in compute.
- Channels: Multi-platform ingestion that normalizes Slack, Microsoft Teams, and Outlook conversations into a common schema.

---

## 2. Platform choices

- Cloud: AWS.
- Compute:
  - Webhooks/API: ECS Fargate behind ALB. Low cold‑start, steady latency.
  - Workers: ECS Fargate for ingest, LLM, sync; autoscaled on queue depth.
  - Scheduled jobs: EventBridge.
- Messaging: SQS (standard queues) for decoupling; DLQ per queue. Microsoft Graph change notifications land on dedicated webhooks that enqueue work for Teams and Outlook threads.
- Storage:
  - Primary DB: Amazon RDS PostgreSQL with pgvector.
  - Object store: S3 for artifacts (prompts, exports, eval sets).
  - Cache: ElastiCache Redis for hot session state and rate limits.
- Secrets: AWS Secrets Manager; KMS per‑tenant CMKs for Slack, Microsoft Graph, and connector credentials.
- Observability: CloudWatch + OpenTelemetry exporters to vendor sink.
- IaC: Terraform. One stack per environment.

Rationale: Simple, managed services, predictable ops, easy horizontal scale.

---

## 3. External integrations

- Slack:
  - Events: `message.channels`, `reaction_added`, `link_shared`.
  - Features: Slash command, message shortcut, interactive components, pinned messages, Home tab.
  - Constraints: 3 s initial ack; signed request verification; channel and user permissions.
- Microsoft Teams:
  - APIs: Microsoft Graph `Chat.Read.All`, `ChannelMessage.Read.All`, `ChatMessage.Send`, `TeamsActivity.Send`, change notifications.
  - Features: Message extension, message action, Adaptive Cards, pinned channel messages.
  - Constraints: 5 s Bot Framework timeout; SSO via Entra ID; tenant admin consent required.
- Outlook (Microsoft 365):
  - APIs: Microsoft Graph `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, change notifications, delta queries.
  - Features: Outlook add‑in, actionable messages, shared mailbox support.
  - Constraints: Subscription renewals ≤ 4230 minutes; HTML body sanitization; mailbox scoping.
- Ticketing: Jira, Linear, Asana, ServiceNow via outbound webhooks with OAuth.
- Docs: Confluence, Notion.
- Calendar: Google Calendar or Microsoft 365.
- LLM providers: Pluggable adapter for OpenAI, Anthropic, Azure OpenAI. Retry with circuit breakers.

---

## 4. Services and responsibilities

1. **Gateway API**
   - Endpoints: Slack command/interaction webhooks, Microsoft Teams message extension and action callbacks, Outlook add‑in/actionable message webhooks, Microsoft Graph validation/notification webhooks, admin APIs, brief read APIs.
   - Validates Slack signatures and Microsoft Entra ID tokens. Returns 200 within 300 ms for Slack and 5 s for Teams. Enqueues jobs.
   - Receives Microsoft Graph change notifications and enqueues delta fetch jobs for Teams and Outlook threads.
   - Issues short‑lived JWTs for UI views.

2. **Ingestor**
   - Expands a thread: messages, edits, reactions, quoted links from Slack, Teams, or Outlook sources.
   - Normalizes payloads into canonical `{platform, native_id}` message objects with deep links, timestamps in UTC, and user metadata from Slack directory, Microsoft Entra ID, or Outlook contacts.
   - Respects channel scopes. Paginates with Slack rate limits or Microsoft Graph delta tokens and backoff.

3. **Preprocessor**
   - Removes noise events. Preserves code blocks and quotes.
   - Builds reply graph and topic boundaries.
   - Detects language per message. Maps mentions to canonical user references via Slack directory or Microsoft Graph.

4. **Segmenter**
   - Splits into topical segments ≤ 2k model tokens.
   - Prevents splits inside code/quote spans.
   - Emits segment manifests with message ID ranges.

5. **LLM Orchestrator**
   - Routes workloads to small or large models by policy (token size, risk, user tier, cost cap).
   - Enforces token and cost budgets per job and per tenant.
   - Tracks prompts, versions, seeds, and provider responses.
   - Supports deterministic mode for evals.

6. **Extractor**
   - From per‑segment summaries, extracts candidates of four types.
   - Normalizes dates (“EOD Fri”, weekdays) using tenant or channel timezone.
   - Owner inference using directed imperatives, self‑assignments, role map, last responsible speaker.

7. **Ranker/Deduper**
   - Scores by model certainty, agreement signals (reactions, repeated phrases), seniority, recency, contradiction.
   - Fuzzy merges near duplicates. Applies promotion threshold.

8. **Provenance Binder**
   - Attaches `{msg_id, quote}` per item. Builds “Why this” factors.
   - Computes content hashes for idempotency.

9. **Card Publisher**
   - Posts Block Kit card in Slack, Adaptive Card in Teams, and actionable summary email for Outlook. Pins or sends condensed brief after first confirmation.
   - Handles Confirm, Edit, Assign, Create‑ticket, Snooze callbacks across platforms.

10. **Sync Connectors**
    - Creates or updates tickets/docs/calendar holds on confirmed items.
    - Posts backlinks to the originating Slack, Teams, or Outlook conversation. Retries with idempotency keys.

11. **Digest Generator**
    - Nightly per channel. Overdue actions and new decisions.

12. **Registry Exporter**
    - Channel‑scoped registry web view and CSV export.

13. **Admin Console**
    - Tenant setup, scopes, role map, thresholds, retention, cost caps, integrations.

14. **Graph Subscription Manager**
    - Registers and renews Microsoft Graph subscriptions for Teams channels, chats, and Outlook mailboxes.
    - Persists delta tokens and watermark state. Triggers fallback polling when notifications fail.

---

## 5. Data model (entities and keys)

No code; entities and key fields only.

- **tenant**: id, name, region, data_residency, kms_key_id, plan.
- **workspace**: id, tenant_id, slack_team_id (nullable), m365_tenant_id (nullable), bot_user_id, graph_app_id, auth tokens (encrypted), settings.
- **channel**: id, workspace_id, platform (`slack|msteams|outlook`), slack_channel_id (nullable), teams_channel_id (nullable), mailbox_id (nullable), timezone, policies.
- **user**: id, workspace_id, platform_user_ref (JSON `{platform, native_id, email}`), display_name, role, seniority_weight.
- **thread**: id, workspace_id, channel_id, platform, source_thread_id, source_url, content_hash, delta_token, status.
- **message**: id, thread_id, platform, source_msg_id, parent_msg_id, author_user_id, text_hash, lang, reactions_json, metadata_json.
- **segment**: id, thread_id, start_msg_id, end_msg_id, token_count, lang.
- **item**: id (ULID), thread_id, type, title, summary, owner_user_id, due_at_utc, likelihood, impact, mitigation, status, confidence, promoted_at, source_platform.
- **evidence**: id, item_id, message_id, quote, weight.
- **people_map_entry**: id, thread_id, display_name, platform_user_ref.
- **brief**: run_id, thread_id, version, model_version, api_version, json_blob, created_at.
- **changelog**: id, item_id, actor_user_id, change_json, created_at.
- **sync_link**: id, item_id, system, external_id, url, status.
- **prompt**: id, name, version, template_ref, checksum.
- **subscription**: id, workspace_id, platform, resource, notification_url, delta_token, expires_at.
- **eval_result**: id, prompt_id, dataset_id, metrics_json, provider_stats.
- **cost_ledger**: id, tenant_id, run_id, provider, input_tokens, output_tokens, usd, timestamp.
- **audit_log**: id, tenant_id, actor, action, resource, metadata, created_at.

Indexes: tenant_id everywhere; unique(platform, source_thread_id); unique(thread_id, type, title, content_hash); GIN for message_reactions; pgvector index on embeddings where used.

---

## 6. Data flows

### 6.1 `/condense` invocation (happy path)
1. Slack sends slash command or message shortcut, Teams sends a message extension invoke, or Outlook invokes the add‑in. Gateway verifies Slack signature or Entra ID tokens and responds with the required ack (Slack 3 s, Teams 5 s, Outlook immediate UI update).
2. Gateway enqueues `condense.request` with `{platform, thread_ref, requester_user_id, run_id}`.
3. Ingestor consumes job. Pulls thread messages with pagination. Writes messages and reply graph. Emits `condense.prepared`.
4. Preprocessor cleans and annotates. Segmenter creates segments with token counts. Emits `condense.segmented`.
5. Orchestrator fan‑outs per‑segment summarization to small model. Collects summaries. Emits `condense.summarized`.
6. Extractor runs structured extraction with citations. Emits candidate items with scores. Emits `condense.candidates`.
7. Ranker merges and filters by threshold. Provenance binder attaches quotes and links. Writes brief draft. Emits `condense.brief_ready`.
8. Card publisher posts Block Kit card in Slack, Adaptive Card in Teams, or actionable summary email in Outlook. Stores brief. Optionally pins or sends summary.

### 6.2 Item confirmation
1. User clicks Confirm/Edit/Assign. Slack posts an interaction payload, Teams posts an Adaptive Card submit, or Outlook posts actionable message data.
2. Gateway validates and enqueues `item.confirm` or `item.edit` with platform context.
3. Worker updates item, writes changelog, updates pinned brief.
4. If confirmed, Sync Connectors create tickets/docs/calendar holds. Backlinks posted.

### 6.3 Incremental watch
1. EventBridge schedules re‑scan for N hours or Graph subscriptions fire change notifications. Ingestor fetches new messages only using Slack history, Teams delta tokens, or Outlook delta queries.
2. Extractor re‑scores items touched by contradictions or new approvals. Changelog updated.

### 6.4 Nightly digest
1. EventBridge triggers per channel or mailbox. Digest Generator queries confirmed decisions, risks, overdue actions. Posts summary to Slack channel, Teams channel, or Outlook distribution list.

### 6.5 Microsoft Graph change notification handling
1. Microsoft Graph posts a change notification for a subscribed Teams channel, chat, or Outlook mailbox to the Gateway webhook.
2. Gateway validates the notification, persists the new delta token, and enqueues `condense.delta` with `{platform, resource_id, delta_token}`.
3. Ingestor processes the delta payload, refreshes affected messages, and emits downstream events for extraction and card updates.

---

## 7. LLM strategy

- Routing policy:
  - Segments: small instruct model.
  - Final brief synthesis: small by default; upgrade to larger model for long or high‑risk threads.
- Budgets:
  - Per thread: ≤ 40k input tokens and ≤ 6k output tokens across passes.
  - Per tenant daily USD cap. Hard stop when exceeded.
- Prompt management:
  - Templates stored with version and checksum. Immutable after release.
  - Few‑shot examples per domain. Domain chosen from channel metadata when present.
- Determinism:
  - Fixed seeds (where supported). Temperature ≤ 0.3 for extraction.
- Guardrails:
  - Must include at least one quotation and message ID per extracted item.
  - Reject decisions without explicit commitment verbs.
- Caching:
  - Prompt+content hash → response cache in Redis for idempotent retries.
  - Embedding cache on message text hash in Postgres+pgvector.

---

## 8. Scoring details

- Confidence score S = w1·model_certainty + w2·agreement + w3·seniority + w4·recency − w5·contradiction.
- Agreement: normalized sum of positive reactions and repeated phrases.
- Seniority: weight by known titles of approvers.
- Contradiction: penalty when later messages negate prior statements.
- Thresholds: default promote at 0.65; show as “needs review” at 0.50–0.64.

---

## 9. Timezone and date normalization

- Source priority: channel timezone setting → workspace default → requester profile → fallback UTC.
- NLP rules for “EOD”, weekdays, “next Monday”, “by COB”, specific dates.
- Store normalized ISO 8601 UTC plus original phrase.

---

## 10. Slack and Teams UI design (no code)

- Card sections: Decisions, Risks, Actions, Open Questions. Count badges per section.
- Each item shows title, owner, due date, confidence badge, two evidence quotes, “Why this” expander.
- Buttons: Confirm, Edit, Assign, Create ticket, Snooze.
- Pinned brief: compact roll‑up with deep link to full brief view in Slack or Teams.
- Home tab (Slack) / configurable tab (Teams): tenant settings, integrations, thresholds, watch window, retention.
- Outlook actionable emails reuse the same groupings and provide deep links back to the Slack or Teams card for edits.

---

## 11. Security model

- Request auth:
  - Slack signature verification (v0). Timestamp skew ≤ 5 minutes.
  - JWT for internal APIs. Short TTL. Audience bound.
  - Microsoft Teams/Outlook callbacks validated with Entra ID JWTs (Bot Framework) and actionable message signatures.
- Data protection:
  - AES‑256 at rest. TLS 1.2+ in transit.
  - Per‑tenant KMS CMK. Envelope encryption for secrets and exports.
  - Row‑level security in Postgres by tenant_id.
  - Microsoft Graph refresh tokens stored with envelope encryption and rotated automatically.
- Least privilege:
  - Slack scopes limited to required list.
  - Connectors use minimal OAuth scopes per system.
- Access control:
  - RBAC: admin, reviewer, requester. Enforced on server.
- Privacy:
  - Do not store message bodies by default. Store message IDs and quotes after confirmation unless admin opts into drafts.
  - Redact secrets and PII in logs.
  - For Outlook, strip signatures and inline images from stored quotes unless explicitly whitelisted.
- Compliance:
  - Audit log for admin, sync, and data access actions.
  - Data deletion API completes within 7 days.

---

## 12. Reliability and scaling

- SLOs:
  - 99.9% monthly availability.
  - P50 time to first card ≤ 30 s for 400 messages. P95 ≤ 90 s.
- Backpressure:
  - Queue length alerts. Autoscale workers on SQS depth.
  - Provider rate limiter with token buckets per tenant and per provider.
- Idempotency:
  - Keys based on (thread_url, content_hash, prompt_version).
  - Safe retries for posts and sync calls.
- Rate limits:
  - Slack: track `Retry‑After`. Exponential backoff with jitter. Concurrency caps per team.
   - Microsoft Graph: monitor `Retry-After` headers, respect subscription throttles, stagger delta queries per mailbox.
- DR:
  - Multi‑AZ RDS. Daily encrypted snapshots. S3 versioning.
  - Stateless workers. Recreate from containers.

---

## 13. Cost controls

- Hard monthly tenant caps. Fail fast with clear error when exceeded.
- Model router prefers small models; escalate only on need.
- Token accounting per run in cost_ledger.
- Embedding and prompt caching to reduce re‑compute.
- Digest and watch windows batched to reduce provider calls.

---

## 14. Internationalization

- Per‑message language detection. Segment language preserved.
- Optional pivot translation for extraction. Original quotes retained.
- Output language matches dominant thread language unless overridden.

---

## 15. Admin and configuration

- Feature flags by tenant and workspace.
- Thresholds: promotion, contradiction penalty, owner inference strictness.
- Watch window duration per channel.
- Role map: title → default domain owner.
- Data retention policy per tenant and region selection.

---

## 16. Monitoring and alerting

- Metrics:
  - Latency P50/P95 by stage.
  - Error rates by stage and provider.
  - Token and USD spend per tenant and per run.
  - Extraction precision/recall from annotated evals.
  - Confirmation and rejection rates.
  - Platform-specific success rates for Slack, Teams, and Outlook entrypoints.
- Tracing:
  - Correlation IDs from entrypoint payload (Slack/Teams/Outlook) → run_id → provider calls → connectors.
- Logs:
  - Structured JSON. No message bodies. Message IDs only.
- Alerts:
  - SLO burn, queue stagnation, provider outage, cost threshold breach.

---

## 17. Testing and evaluation

- Unit tests for preprocess, segmentation, normalization, inference rules.
- Golden threads dataset with human‑labeled items. Nightly regression.
- Include Slack, Teams, and Outlook conversations to validate normalization differences.
- Shadow runs in staging against mirrors of production channels where allowed.
- Safety tests: hallucination checks, owner misattribution, date misparsing.
- Canary deploys with 5% traffic before full rollout.

---

## 18. Threat model (summary)

- Spoofed Slack request → mitigated by signature verification and timestamp window.
- Spoofed Microsoft Graph notification → mitigated by Entra ID validation, resource verification, and subscription secrets.
- Token theft → mitigated by KMS, Secrets Manager, short‑lived tokens, vault rotation.
- Over‑permissioned scopes → limited scopes and periodic reviews.
- Data exfiltration via connectors → egress allowlists, per‑connector scopes, audit logs.
- Prompt injection inside messages → strict extraction rules, allowlist of verbs for decisions, evidence requirement.

---

## 19. Failure modes and fallbacks

- LLM provider outage → route to secondary provider; degrade to extract‑only with no synthesis; post notice.
- Slack API rate limit → defer with exponential backoff; partial updates with pinned warning.
- Microsoft Graph subscription expiration → auto-renew via Subscription Manager; alert and fall back to delta polling.
- Connector failure → queue retries; show unsynced badge; allow manual retry.
- Over budget → stop at ranked candidates; require admin override.

---

## 20. Deploy and release

- Environments: dev, staging, prod. Isolated AWS accounts.
- Blue/green for Gateway and workers. One‑click rollback.
- Schema migrations with online tools. Backward‑compatible JSON for briefs.
- Versioning:
  - `model_version` and `api_version` embedded in every brief.
  - Prompt versions immutable; changelog recorded.

---

## 21. Runbooks (abbreviated)

- Queue backlog spike → scale workers, inspect provider status, check DLQ for poison jobs.
- Elevated hallucinations → roll back prompt version, lower temperature, raise decision verb threshold.
- Slack 3 s acks failing → increase webhook pool, reduce synchronous work, confirm health checks.
- Microsoft Graph notifications stale → check subscription expiry, refresh credentials, trigger manual delta sync.

---

## 22. Out of scope (architecture)

- Real‑time message moderation.
- Cross‑workspace aggregation without explicit admin linkage.
- Additional chat or email platforms beyond Slack, Microsoft Teams, and Outlook in V1.

---

## 23. Appendix: item lifecycle states

- Proposed → Confirmed → In progress → Done/Blocked; with edits recorded in changelog.
- Sync states: Pending → Created → Updated → Failed (retryable) → Abandoned (manual).

---

This document defines the technical shape and choices. It omits code by design.

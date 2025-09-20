# requirements.md

**Product**: Thread Condenser  
**Purpose**: Convert long chat threads into auditable briefs of decisions, risks, actions, and open questions for managers and support leaders.

## 1. Scope

- The system shall ingest a chat thread and produce a structured brief with provenance.  
- The system shall operate Slack‑first.  
- The system may support other chat platforms in future versions.

## 2. Definitions

- **Thread**: A parent message and all replies.  
- **Item**: A Decision, Risk, Action, or Open Question.  
- **Provenance**: Message IDs and quotes that support an Item.  
- **Confidence**: A numeric score in the range [0, 1].

## 3. Actors

- **Requester**: Any Slack user who invokes the command.  
- **Reviewer**: A user who confirms or edits Items.  
- **Admin**: A user who manages configuration and integrations.

## 4. High‑Level Overview

- The system shall expose a Slack slash command and message shortcut to trigger condensation.  
- The system shall post an interactive card with the extracted Items for confirmation.  
- On confirmation, the system shall sync Items to external tools and pin a compact brief to the thread.

## 5. Functional Requirements

### 5.1 Slack Integration

1. The Slack app shall request these scopes: `channels:history`, `channels:read`, `chat:write`, `commands`, `reactions:read`, `users:read`, `links:read`.  
2. The app shall subscribe to events: `message.channels`, `reaction_added`, `link_shared`.  
3. The app shall provide:
   - A slash command `/condense` that shall accept a thread URL or operate on the current thread.  
   - A message shortcut that shall operate on the selected message’s thread.  
4. The app shall post results as a Block Kit message with sections for Decisions, Risks, Actions, and Open Questions.  
5. The card shall include buttons per Item: **Confirm**, **Edit**, **Assign**, **Create ticket**, **Snooze**.  
6. The app shall pin a summary message to the thread after at least one Item is confirmed.  
7. The app shall respect channel membership and shall not reveal content to users who lack access.

### 5.2 Ingest

1. The system shall fetch the complete thread, including edits, replies, reactions, and user directory data.  
2. The system shall expand quoted message links and unfurl referenced in‑workspace messages.  
3. The system shall extract text from common attachment types where Slack provides text content.  
4. The system shall not fetch content from private resources the app is not permitted to access.

### 5.3 Preprocess

1. The system shall remove join and leave notifications and bot boilerplate.  
2. The system shall preserve code blocks and quoted text as distinct spans.  
3. The system shall build a reply graph with parent, depth, and branches.  
4. The system shall normalize timestamps to ISO 8601 in UTC.

### 5.4 Segmentation

1. The system shall segment the thread into topical segments no larger than 2,000 model tokens each.  
2. The system shall prevent segment splits inside code blocks or quoted spans.  
3. The system shall record segment boundaries and message IDs for traceability.

### 5.5 Summarization

1. The system shall summarize each segment into 1–5 bullets.  
2. The system shall avoid claims not supported by segment content.  
3. The system shall emit per‑bullet evidence references to message IDs.

### 5.6 Structured Extraction

1. The system shall extract candidate Items of four types: Decision, Risk, Action, Open Question.  
2. The system shall only extract a Decision when at least one message contains an explicit commitment or approval.  
3. The system shall only extract an Action when at least one message contains an instruction, commitment, or task phrasing.  
4. Each Item shall include at least one message quote and at least one source message ID.  
5. Each Item shall include a confidence score in [0, 1].  
6. The system shall detect dates and times in natural language and shall normalize them to ISO 8601 UTC.  
7. The system shall map user mentions to Slack user IDs using the user directory.

### 5.7 Ranking and Deduplication

1. The system shall score Items using model certainty, agreement signals, speaker seniority, and recency.  
2. The system shall merge near‑duplicate Items using fuzzy matching on title and normalized fields.  
3. The system shall apply a promotion threshold. Default threshold shall be 0.65 confidence.  
4. The system shall retain suppressed Items in an internal list for audit and tuning.

### 5.8 Owner and Due Date Inference

1. The system shall infer owners using imperative targeting, self‑assignments, final responsible speaker, and a role map.  
2. The system shall leave owner empty if inference is ambiguous and shall flag the Item for confirmation.  
3. The system shall infer due dates from explicit dates, “EOD” phrases, and weekday references aligned to the channel’s timezone when available.

### 5.9 Provenance and Auditing

1. Every Item shall include `supporting_msgs[]` with `{msg_id, quote}` pairs.  
2. Every Item shall include a link to at least one source message in Slack.  
3. The brief shall include a `Provenance` block with `thread_url`, `message_ids[]`, `model_version`, and `run_id`.  
4. The system shall provide a “Why this” view that reveals high‑level scoring factors without exposing prompts.

### 5.10 Human‑in‑the‑Loop

1. The card shall present Items in ranked order.  
2. Users shall be able to **Confirm**, **Edit**, **Assign**, and **Reject** each Item.  
3. The system shall update the pinned brief after any confirmation or edit.  
4. The system shall record a changelog entry for each revision with timestamp and actor.

### 5.11 External Sync

1. On confirmation, the system shall create or update tickets in Jira or Linear when configured.  
2. The system shall write decision docs in Confluence or Notion with backlinks when configured.  
3. The system shall add calendar holds for Items with due dates when configured.  
4. The system shall post external links back to the Slack thread.  
5. The system shall not sync unconfirmed Items.

### 5.12 Incremental Updates

1. The system shall watch the thread for a configurable window after the first run. Default shall be 6 hours.  
2. The system shall re‑process only new deltas and shall update Items that are contradicted or superseded.  
3. The system shall maintain a `Changelog[]` with diffs between versions.

### 5.13 Digest and Notifications

1. The system shall produce a nightly channel digest listing confirmed Decisions, Risks, and overdue Actions.  
2. Users may snooze Items. Snoozed Items shall appear in the next digest after the snooze window ends.

### 5.14 Export

1. The system shall export confirmed Items to a channel‑scoped registry accessible via a web view.  
2. The export shall provide filters by type, owner, date, and confidence.  
3. The export shall preserve provenance links.

### 5.15 Administration

1. Admins shall be able to configure integrations, thresholds, and retention.  
2. Admins shall be able to define a role map that links titles to default owners for domains.  
3. Admins shall be able to enable or disable the app per channel.

## 6. Data Model Requirements

The system shall persist the following schema or an equivalent with the same constraints.

### 6.1 Item Fields

- `id` shall be a ULID or UUIDv4.  
- `type` shall be one of `decision|risk|action|open_question`.  
- `title` shall be non‑empty for Decisions and Actions.  
- `summary` shall be ≤ 512 characters.  
- `owner` may be null or a Slack user ID.  
- `due_date` may be null or an ISO 8601 timestamp in UTC.  
- `likelihood` for Risks shall be one of `low|medium|high`.  
- `impact` for Risks shall be one of `low|medium|high`.  
- `mitigation` for Risks may be null.  
- `status` for Actions shall be one of `proposed|confirmed|in_progress|done|blocked`.  
- `confidence` shall be a float in [0, 1].  
- `supporting_msgs[]` shall contain at least one element.  
- Each `supporting_msgs[i].msg_id` shall be a Slack message TS string.  
- Each `supporting_msgs[i].quote` shall be ≤ 280 characters.  
- `people_map` shall map display names to Slack user IDs.  
- `provenance.thread_url` shall be a valid Slack URL.

### 6.2 Brief

- The brief shall include `decisions[]`, `risks[]`, `actions[]`, `open_questions[]`, `people_map`, `provenance`, and `changelog[]`.  
- Empty arrays shall be allowed.  
- The brief JSON shall validate against an agreed JSON Schema.

## 7. API Requirements

### 7.1 Auth

- All HTTP APIs shall use OAuth 2.0 for Slack calls and JWT for backend endpoints.  
- Tokens shall be rotated automatically and stored encrypted at rest.

### 7.2 Endpoints

- `POST /v1/condense` shall accept `{thread_url, options}` and shall return a brief draft.  
- `POST /v1/items/{id}/confirm` shall mark an Item confirmed and shall trigger sync.  
- `POST /v1/items/{id}/edit` shall update fields and shall record a changelog entry.  
- `GET /v1/briefs/{run_id}` shall return the current brief.  
- `GET /v1/export` shall return confirmed Items with filters.  
- Error responses shall include a stable `error_code`, `message`, and `correlation_id`.

### 7.3 Rate Limits

- The API shall enforce per‑workspace rate limits and shall return `429` with `Retry‑After`.

## 8. UX Requirements

1. The card shall group Items by type with a count header for each group.  
2. Each Item row shall display title, owner, due date, confidence, and two evidence quotes.  
3. Confidence shall display as a 0–100 badge.  
4. Buttons shall map to server actions.  
5. The pinned brief shall be concise and shall link to the full brief view.  
6. The UI shall render correctly in light and dark Slack themes.

## 9. LLM and Prompting Requirements

1. The system shall use a small model for segmentation and extraction and may use a larger model for final synthesis.  
2. Prompts shall mandate citations for every extracted Item.  
3. The system shall not emit a Decision without an explicit commitment verb present in source text.  
4. The system shall not fabricate dates or owners.  
5. The system shall cap per‑thread token use. Default cap shall be 40,000 input tokens and 6,000 output tokens across all passes.  
6. The system shall support deterministic runs with fixed seeds where the model allows.

## 10. Non‑Functional Requirements

### 10.1 Performance

- For a 400‑message thread, P50 end‑to‑card latency shall be ≤ 30 s.  
- For a 400‑message thread, P95 end‑to‑card latency shall be ≤ 90 s.  
- LLM spend per 400‑message thread must not exceed USD 0.50 at P50.

### 10.2 Availability and Reliability

- The service shall achieve 99.9% monthly availability.  
- The service shall degrade gracefully and shall queue requests when the model is rate‑limited.  
- The service shall provide idempotent operations for confirm and edit.

### 10.3 Security and Privacy

- Message bodies shall not be stored at rest by default.  
- The system shall store message IDs, metadata, embeddings, and quotes only after confirmation unless workspace policy permits drafts.  
- All data at rest shall be encrypted with AES‑256.  
- All data in transit shall use TLS 1.2 or higher.  
- Access to workspaces shall be isolated by tenant.  
- The system shall honor Slack channel access controls for every read and write.  
- The system shall support data deletion on request within 7 days.  
- Secrets shall be stored in a managed secret store.  
- Logs shall exclude message bodies and PII where feasible.  
- The system shall provide audit logs for all admin and sync actions.

### 10.4 Compliance

- The system shall provide a data map for SOC 2 scoping.  
- The system shall support EU data residency when configured.

### 10.5 Internationalization

- The system shall auto‑detect language per message.  
- The system may translate to a pivot language for extraction and shall preserve original quotes.  
- The output language shall match the dominant language of the thread unless configured otherwise.

### 10.6 Observability

- The system shall emit metrics for latency, error rate, token usage, cost, extraction precision, and confirmation rate.  
- The system shall provide distributed tracing with correlation IDs.  
- The system shall provide redaction in logs for user IDs and URLs where required.

### 10.7 Retention

- Raw processing artifacts shall be retained no longer than 30 days by default.  
- Confirmed Items may be retained until deletion or workspace offboarding.

## 11. Quality, Testing, and Metrics

1. The team shall maintain an annotated test set of threads for regression.  
2. The system shall achieve ≥ 0.85 precision and ≥ 0.75 recall on Decisions in the test set.  
3. The system shall achieve ≥ 0.80 precision and ≥ 0.70 recall on Actions.  
4. Unit tests shall cover ≥ 80% of extraction and normalization code paths.  
5. E2E tests shall run on every deploy and shall post results to an internal channel.  
6. The system shall track false positive and false negative rates from user rejections and edits.

## 12. Edge Cases

1. When two Decisions conflict, the system shall mark both with a `conflict` tag and shall require reviewer action.  
2. The system shall down‑weight sarcasm, memes, and low‑signal content.  
3. The system shall handle multi‑topic branches and shall not cross‑contaminate Items across unrelated branches.  
4. The system shall handle multi‑language threads by segment.  
5. The system shall skip content that violates workspace DLP rules and shall log a redaction event.

## 13. Failure Modes and Safeguards

1. The system shall not post a brief if no Items exceed the promotion threshold. It shall post a notice with a link to a raw summary.  
2. The system shall surface contradiction signals that lower confidence below threshold and shall demote affected Items.  
3. The system shall offer top three owner candidates when owner inference is ambiguous.

## 14. Configuration

- The promotion threshold shall be configurable per workspace.  
- The watch window duration shall be configurable per channel.  
- Integrations and field mappings shall be configurable per workspace.  
- Cost caps per workspace shall be configurable. Exceeding a cap shall fail fast with a clear error.

## 15. Rollout and Versioning

- V0 shall accept exported JSON threads via CLI.  
- V1 shall enable Slack app with `/condense`, confirmation card, and Jira or Linear sync.  
- V2 shall enable incremental updates, nightly digests, and registry export.  
- Breaking changes to the brief schema shall bump a major version.  
- The system shall embed `model_version` and `api_version` in every brief.

## 16. Out of Scope

- The system shall not modify or delete Slack messages.  
- The system shall not auto‑approve Items without human confirmation.  
- The system shall not scrape external web content behind auth other than Slack and configured tools.

## 17. Conformance

- An implementation that satisfies all “shall” and “must” statements is conformant.  
- Optional features marked as “may” do not affect conformance.

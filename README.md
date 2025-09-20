# Thread Condenser

Thread Condenser ingests Slack, Microsoft Teams, and Outlook conversations and produces structured briefs of decisions, risks, actions, and open questions.

## Getting started

1. Copy `.env.example` to `.env` and fill in credentials.
2. Start the local stack:
   ```bash
   make run
   ```
3. Apply database migrations:
   ```bash
   make migrate
   ```
4. Configure Slack, Microsoft Teams, and Outlook integrations as described in `requirements.md`.

The FastAPI app listens on `http://localhost:8080` and exposes `/v1` APIs along with platform-specific webhooks.

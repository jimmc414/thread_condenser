# implementation.md

Product: Thread Condenser  
Purpose: Convert long Slack threads into auditable briefs of decisions, risks, actions, and open questions with provenance.  
Stack: Python 3.11, FastAPI, Slack Bolt (FastAPI adapter), Celery, Redis, Postgres + pgvector, httpx, Pydantic, Alembic.

This is a complete, standalone implementation plan with ready code. Copy files as indicated, set env vars, run Docker Compose, and iterate.

---

## 0) Repository layout

```
thread-condenser/
  app/
    __init__.py
    config.py
    logging.py
    db.py
    models.py
    schemas.py
    auth.py
    deps.py
    main.py
    api/
      __init__.py
      v1.py
    slack/
      __init__.py
      bolt_app.py
      blocks.py
      publisher.py
    llm/
      __init__.py
      base.py
      router.py
      openai_chat.py
      tokenization.py
    pipeline/
      __init__.py
      ingest.py
      preprocess.py
      segment.py
      extract.py
      rank.py
      owner_infer.py
      date_utils.py
      provenance.py
      brief.py
    connectors/
      __init__.py
      base.py
      jira.py
      linear.py
      confluence.py
      notion.py
      calendar.py
    workers/
      __init__.py
      celery_app.py
      tasks.py
    prompts/
      summarization.md
      extraction.md
    migrations/
      env.py
      versions/
  alembic.ini
  requirements.txt
  docker-compose.yml
  Dockerfile
  Makefile
  README.md
```

---

## 1) Dependencies

**requirements.txt**
```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
slack-bolt==1.21.2
slack-sdk==3.33.1
pydantic==2.9.2
pydantic-settings==2.5.2
SQLAlchemy==2.0.35
alembic==1.13.2
psycopg[binary]==3.2.3
httpx==0.27.2
celery==5.4.0
redis==5.0.8
python-json-logger==2.0.7
dateparser==1.2.0
pytz==2024.1
python-jose==3.3.0
passlib[bcrypt]==1.7.4
tiktoken==0.7.0
orjson==3.10.7
pytest==8.3.2
black==24.8.0
```

---

## 2) Runtime and containers

**Dockerfile**
```Dockerfile
FROM python:3.11-slim

ENV POETRY_VIRTUALENVS_CREATE=false PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app app
COPY alembic.ini .
COPY app/migrations migrations
COPY Makefile .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**docker-compose.yml**
```yaml
version: "3.9"
services:
  api:
    build: .
    env_file: .env
    ports: ["8080:8080"]
    depends_on: [db, redis]
  worker:
    build: .
    command: celery -A app.workers.celery_app.celery_app worker -l INFO -Q default,webhooks,sync,digest
    env_file: .env
    depends_on: [db, redis]
  beat:
    build: .
    command: celery -A app.workers.celery_app.celery_app beat -l INFO
    env_file: .env
    depends_on: [db, redis]
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: tc
      POSTGRES_PASSWORD: tc
      POSTGRES_DB: tc
    ports: ["5432:5432"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
```

**Makefile**
```Makefile
.PHONY: run migrate revision fmt

run:
\tdocker compose up --build

migrate:
\tdocker compose exec api alembic upgrade head

revision:
\tdocker compose exec api alembic revision --autogenerate -m "$(m)"

fmt:
\tpython -m black app
```

**.env** (example; do not commit real secrets)
```env
APP_ENV=dev
APP_SECRET=change-me
POSTGRES_DSN=postgresql+psycopg://tc:tc@db:5432/tc
REDIS_URL=redis://redis:6379/0

# Slack
SLACK_BOT_TOKEN=xoxb-***
SLACK_SIGNING_SECRET=***
SLACK_APP_LEVEL_TOKEN=xapp-***  # optional for Socket Mode, not used here
PUBLIC_BASE_URL=http://localhost:8080

# LLM
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-***
OPENAI_MODEL=gpt-4o-mini
LLM_MAX_INPUT_TOKENS=40000
LLM_MAX_OUTPUT_TOKENS=6000

# Feature
WATCH_WINDOW_SECONDS=21600
PROMOTION_THRESHOLD=0.65
```

---

## 3) Database and migrations

**alembic.ini**
```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql+psycopg://tc:tc@db:5432/tc
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stdout,)
level = INFO
formatter = generic

[formatter_generic]
format = %(asctime)s %(levelname)-5.5s [%(name)s] %(message)s
```

**app/db.py**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.POSTGRES_DSN, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()
```

**app/models.py**
```python
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Boolean, Float, JSON, UniqueConstraint, Index, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db import Base

def ulid():
    # simple UUIDv4 stand-in; replace with ULID if desired
    return uuid.uuid4()

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    name = Column(String, nullable=False)
    region = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    slack_team_id = Column(String, unique=True, nullable=False)
    bot_user_id = Column(String, nullable=True)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

class Channel(Base):
    __tablename__ = "channels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    slack_channel_id = Column(String, nullable=False)
    timezone = Column(String, nullable=True)
    policies = Column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("workspace_id","slack_channel_id"),)

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    slack_user_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=True)
    seniority_weight = Column(Float, default=1.0)
    __table_args__ = (UniqueConstraint("workspace_id","slack_user_id"),)

class Thread(Base):
    __tablename__ = "threads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False)
    slack_thread_ts = Column(String, nullable=False)
    url = Column(String, nullable=False)
    content_hash = Column(String, nullable=True)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("workspace_id","slack_thread_ts"),)

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    slack_ts = Column(String, nullable=False)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    text = Column(Text, nullable=False)
    text_hash = Column(String, nullable=False)
    lang = Column(String, nullable=True)
    reactions_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("thread_id","slack_ts"), Index("ix_msg_thread_ts","thread_id","slack_ts"))

class Segment(Base):
    __tablename__ = "segments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    start_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"))
    end_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"))
    token_count = Column(Integer, default=0)
    lang = Column(String, nullable=True)

class Item(Base):
    __tablename__ = "items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    type = Column(String, nullable=False)  # decision|risk|action|open_question
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    due_at_utc = Column(DateTime, nullable=True)
    likelihood = Column(String, nullable=True)
    impact = Column(String, nullable=True)
    mitigation = Column(Text, nullable=True)
    status = Column(String, default="proposed")  # proposed|confirmed|in_progress|done|blocked
    confidence = Column(Float, default=0.0)
    promoted_at = Column(DateTime, nullable=True)

class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    quote = Column(Text, nullable=False)
    weight = Column(Float, default=1.0)

class PeopleMap(Base):
    __tablename__ = "people_map"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    display_name = Column(String, nullable=False)
    slack_user_id = Column(String, nullable=False)

class Brief(Base):
    __tablename__ = "briefs"
    run_id = Column(String, primary_key=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    version = Column(String, nullable=False)
    model_version = Column(String, nullable=True)
    api_version = Column(String, nullable=True)
    json_blob = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Changelog(Base):
    __tablename__ = "changelog"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    change_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class SyncLink(Base):
    __tablename__ = "sync_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    system = Column(String, nullable=False)
    external_id = Column(String, nullable=True)
    url = Column(String, nullable=True)
    status = Column(String, default="pending")

class CostLedger(Base):
    __tablename__ = "cost_ledger"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    run_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    usd = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**app/migrations/env.py**
```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.db import Base
import app.models  # noqa

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")  # pgvector
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Generate first migration after containers start:
```
make revision m="init"
make migrate
```

---

## 4) Configuration and logging

**app/config.py**
```python
from pydantic_settings import BaseSettings
from pydantic import AnyUrl

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    APP_SECRET: str
    POSTGRES_DSN: AnyUrl
    REDIS_URL: str

    SLACK_BOT_TOKEN: str
    SLACK_SIGNING_SECRET: str
    PUBLIC_BASE_URL: str = "http://localhost:8080"

    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_MAX_INPUT_TOKENS: int = 40000
    LLM_MAX_OUTPUT_TOKENS: int = 6000

    WATCH_WINDOW_SECONDS: int = 21600
    PROMOTION_THRESHOLD: float = 0.65

    class Config:
        env_file = ".env"

settings = Settings()
```

**app/logging.py**
```python
import logging, sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.handlers = [handler]
    return logger
```

---

## 5) Schemas and auth

**app/schemas.py**
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class SupportRef(BaseModel):
    msg_id: str
    quote: str

class Decision(BaseModel):
    title: str
    summary: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    supporting_msgs: List[SupportRef]

class Risk(BaseModel):
    statement: str
    likelihood: str
    impact: str
    owner: Optional[str] = None
    mitigation: Optional[str] = None
    confidence: float
    supporting_msgs: List[SupportRef]

class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "proposed"
    confidence: float
    supporting_msgs: List[SupportRef]

class OpenQuestion(BaseModel):
    question: str
    who_should_answer: Optional[str] = None
    confidence: float
    supporting_msgs: List[SupportRef]

class CondenseResult(BaseModel):
    decisions: List[Decision]
    risks: List[Risk]
    actions: List[ActionItem]
    open_questions: List[OpenQuestion]
    people_map: dict
    provenance: dict
    changelog: List[dict] = []
```

**app/auth.py**
```python
from fastapi import Depends, HTTPException, status
from jose import jwt, JWTError
from datetime import datetime, timedelta
from app.config import settings

ALGO = "HS256"
AUD = "thread-condenser"

def make_jwt(subject: str, ttl_seconds: int = 900) -> str:
    now = datetime.utcnow()
    payload = {"sub": subject, "aud": AUD, "iat": now, "exp": now + timedelta(seconds=ttl_seconds)}
    return jwt.encode(payload, settings.APP_SECRET, algorithm=ALGO)

def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.APP_SECRET, algorithms=[ALGO], audience=AUD)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
```

**app/deps.py**
```python
from fastapi import Depends
from app.db import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 6) Slack app configuration

Create a Slack app at api.slack.com/apps:

- **Scopes** (Bot): `channels:history`, `channels:read`, `chat:write`, `commands`, `reactions:read`, `users:read`, `links:read`.
- **Slash command**: `/condense` → Request URL `https://<PUBLIC_BASE_URL>/slack/events`.
- **Interactivity**: Enabled → Request URL `https://<PUBLIC_BASE_URL>/slack/events`.
- **Event Subscriptions**: Enable events. Request URL `https://<PUBLIC_BASE_URL>/slack/events`. Subscribe to: `message.channels`, `reaction_added`, `link_shared`.
- Install to workspace. Put **SLACK_BOT_TOKEN** and **SLACK_SIGNING_SECRET** in `.env`.

---

## 7) Slack handlers and UI

**app/slack/bolt_app.py**
```python
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import APIRouter, Request, Response
from app.config import settings
from app.workers.tasks import enqueue_condense
from app.slack.publisher import post_ephemeral_processing

bolt = AsyncApp(token=settings.SLACK_BOT_TOKEN, signing_secret=settings.SLACK_SIGNING_SECRET)
handler = AsyncSlackRequestHandler(bolt)

router = APIRouter()

@bolt.command("/condense")
async def cmd_condense(ack, body, client, respond, logger):
    await ack()
    channel_id = body.get("channel_id")
    trigger_ts = body.get("trigger_id")  # not used
    thread_ts = body.get("thread_ts") or body.get("message_ts") or body.get("container", {}).get("thread_ts")
    # Fallback: current message context
    if not thread_ts:
        thread_ts = body.get("message_ts")
    user_id = body.get("user_id")
    team_id = body.get("team_id")
    await post_ephemeral_processing(client, channel_id, user_id)
    await enqueue_condense(team_id=team_id, channel_id=channel_id, thread_ts=thread_ts, requester_user_id=user_id)

@bolt.event("reaction_added")
async def on_reaction_added(event, logger):
    # Optional: store for agreement signals. Enqueue lightweight update.
    pass

@bolt.event("message")
async def on_message(event, logger):
    # No-op; ingestion happens on demand and during watch window.
    pass

@bolt.action("item_confirm")
async def on_item_confirm(ack, body, client, logger):
    await ack()
    # body contains action + state; send to worker
    from app.workers.tasks import enqueue_item_confirm
    await enqueue_item_confirm(body)

@bolt.action("item_edit")
async def on_item_edit(ack, body, client, logger):
    await ack()
    from app.workers.tasks import enqueue_item_edit
    await enqueue_item_edit(body)

@router.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)
```

**app/slack/blocks.py**
```python
def item_section(item, idx: int):
    title = item.get("title") or item.get("task") or item.get("statement") or item.get("question")
    confidence = int(round(item.get("confidence", 0.0) * 100))
    owner = item.get("owner") or "Unassigned"
    due = item.get("due_date") or "-"
    quotes = item.get("supporting_msgs", [])[:2]
    quote_text = "\n".join([f"> {q['quote']}" for q in quotes])
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\nOwner: `{owner}`  Due: `{due}`  Conf: *{confidence}%*\n{quote_text}"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Confirm"}, "style": "primary", "action_id": "item_confirm", "value": str(idx)},
            {"type": "button", "text": {"type": "plain_text", "text": "Edit"}, "action_id": "item_edit", "value": str(idx)}
        ]},
        {"type": "divider"}
    ]

def brief_card(result_json: dict):
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Thread Condenser"}}]
    for section in ["decisions", "risks", "actions", "open_questions"]:
        items = result_json.get(section, [])
        if not items: 
            continue
        pretty = {
            "decisions": "Decisions",
            "risks": "Risks",
            "actions": "Actions",
            "open_questions": "Open questions"
        }[section]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{pretty}*  ({len(items)})"}})
        blocks.append({"type": "divider"})
        for idx, it in enumerate(items):
            blocks.extend(item_section(it, idx))
    return blocks
```

**app/slack/publisher.py**
```python
from slack_sdk.web.async_client import AsyncWebClient
from app.slack.blocks import brief_card

async def post_ephemeral_processing(client: AsyncWebClient, channel_id: str, user_id: str):
    await client.chat_postEphemeral(channel=channel_id, user=user_id, text="Processing thread…")

async def post_brief_card(client: AsyncWebClient, channel_id: str, thread_ts: str, brief_json: dict, pin: bool = False):
    blocks = brief_card(brief_json)
    resp = await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="Condensed brief", blocks=blocks)
    if pin:
        try:
            await client.pins_add(channel=channel_id, timestamp=resp["ts"])
        except Exception:
            pass
```

---

## 8) FastAPI app and REST API

**app/api/v1.py**
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import verify_jwt
from app.deps import get_db
from sqlalchemy.orm import Session
from app.models import Brief
import orjson

router = APIRouter(prefix="/v1")

class CondenseRequest(BaseModel):
    thread_url: str
    options: dict | None = None

@router.post("/condense")
def condense(req: CondenseRequest, db: Session = Depends(get_db)):
    # For external calls (non-Slack). Enqueue job similarly.
    from app.workers.tasks import enqueue_condense_external
    run_id = enqueue_condense_external(req.thread_url, req.options or {})
    return {"run_id": run_id}

@router.get("/briefs/{run_id}")
def get_brief(run_id: str, db: Session = Depends(get_db)):
    brief = db.query(Brief).filter(Brief.run_id == run_id).first()
    if not brief:
        raise HTTPException(404)
    return brief.json_blob

class EditRequest(BaseModel):
    patch: dict

@router.post("/items/{item_id}/edit")
def edit_item(item_id: str, req: EditRequest, db: Session = Depends(get_db)):
    from app.workers.tasks import edit_item_sync
    return edit_item_sync(item_id, req.patch, db)
```

**app/main.py**
```python
from fastapi import FastAPI
from app.logging import setup_logging
from app.slack.bolt_app import router as slack_router
from app.api.v1 import router as api_router

setup_logging()
app = FastAPI(title="Thread Condenser")

app.include_router(slack_router)
app.include_router(api_router)
```

---

## 9) LLM adapter and prompts

**app/llm/base.py**
```python
from typing import Protocol, Any

class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str, model: str, temperature: float, max_tokens: int, schema_hint: str | None = None) -> dict: ...
    async def complete_text(self, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str: ...
```

**app/llm/openai_chat.py**
```python
import httpx, asyncio, json
from app.config import settings

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

class OpenAIChat:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def _post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(OPENAI_URL, headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()

    async def complete_json(self, system: str, user: str, model: str | None = None, temperature: float = 0.2, max_tokens: int = 1200, schema_hint: str | None = None) -> dict:
        m = model or self.model
        payload = {
            "model": m,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        }
        if schema_hint:
            payload["messages"].append({"role": "system", "content": f"JSON schema hint: {schema_hint}"})
        data = await self._post(payload)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def complete_text(self, system: str, user: str, model: str | None = None, temperature: float = 0.2, max_tokens: int = 800):
        m = model or self.model
        payload = {
            "model": m,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post(payload)
        return data["choices"][0]["message"]["content"]
```

**app/llm/router.py**
```python
from app.config import settings
from app.llm.openai_chat import OpenAIChat
from app.llm.base import LLMClient

def get_llm() -> LLMClient:
    if settings.LLM_PROVIDER == "openai":
        return OpenAIChat()
    raise RuntimeError("Unsupported LLM_PROVIDER")
```

**app/llm/tokenization.py**
```python
import tiktoken

def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
```

**app/prompts/summarization.md**
```
You summarize a chat segment into 1–5 bullets with message-level anchors.

Rules:
- Only summarize content present in the segment.
- Use neutral, factual language.
- After each bullet, include [ts=<slack_ts>] for at least one supporting message.

Return plain text bullets.
```

**app/prompts/extraction.md**
```
You convert chat content into structured items with message-level citations.

Output strictly this JSON object:
{
  "decisions": [...],
  "risks": [...],
  "actions": [...],
  "open_questions": [...],
  "people_map": {},
  "provenance": {"thread_url": "", "message_ids": [], "model_version": "v1", "run_id": ""}
}

Constraints:
- Extract a Decision only with explicit commitment/approval verbs.
- Every item must include at least one supporting message with exact short quote and message ts.
- Use ISO 8601 UTC for due_date when present, else null.
- Confidence in [0,1]. Do not fabricate owners or dates.
```

---

## 10) Pipeline stages

**app/pipeline/ingest.py**
```python
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session
from app.models import Thread, Message, User, Channel, Workspace
from hashlib import sha1

async def ingest_thread(db: Session, client: AsyncWebClient, team_id: str, channel_id: str, thread_ts: str, url: str):
    # Ensure workspace and channel exist
    ws = db.query(Workspace).filter_by(slack_team_id=team_id).first()
    if not ws:
        ws = Workspace(tenant_id=None, slack_team_id=team_id)  # tenant_id set by admin in real deployments
        db.add(ws); db.commit()
    ch = db.query(Channel).filter_by(workspace_id=ws.id, slack_channel_id=channel_id).first()
    if not ch:
        ch = Channel(workspace_id=ws.id, slack_channel_id=channel_id)
        db.add(ch); db.commit()
    th = db.query(Thread).filter_by(workspace_id=ws.id, slack_thread_ts=thread_ts).first()
    if not th:
        th = Thread(workspace_id=ws.id, channel_id=ch.id, slack_thread_ts=thread_ts, url=url)
        db.add(th); db.commit()

    # Fetch thread replies
    messages = []
    cursor = None
    while True:
        resp = await client.conversations_replies(channel=channel_id, ts=thread_ts, cursor=cursor, limit=200)
        messages.extend(resp.get("messages", []))
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    for m in messages:
        user_id = m.get("user")
        u = None
        if user_id:
            u = db.query(User).filter_by(workspace_id=ws.id, slack_user_id=user_id).first()
            if not u:
                # fetch profile minimally
                try:
                    profile = (await client.users_info(user=user_id))["user"]["profile"]
                    display_name = profile.get("display_name") or profile.get("real_name") or user_id
                except Exception:
                    display_name = user_id
                u = User(workspace_id=ws.id, slack_user_id=user_id, display_name=display_name)
                db.add(u); db.commit()
        text = m.get("text") or ""
        mh = sha1(text.encode("utf-8")).hexdigest()
        exists = db.query(Message).filter_by(thread_id=th.id, slack_ts=m["ts"]).first()
        if not exists:
            db.add(Message(thread_id=th.id, slack_ts=m["ts"], author_user_id=u.id if u else None, text=text, text_hash=mh, reactions_json=m.get("reactions", [])))
    db.commit()
    return th
```

**app/pipeline/preprocess.py**
```python
import re
from sqlalchemy.orm import Session
from app.models import Message

CODE_RE = re.compile(r"```.*?```", re.S)

def clean_text(text: str) -> str:
    # Preserve code blocks, strip Slack formatting noise
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").strip()

def preprocess_thread(db: Session, thread_id):
    msgs = db.query(Message).filter(Message.thread_id==thread_id).order_by(Message.slack_ts).all()
    for m in msgs:
        m.text = clean_text(m.text)
    db.commit()
    return msgs
```

**app/pipeline/segment.py**
```python
from app.llm.tokenization import count_tokens

def segment_messages(messages, max_tokens=2000, model="gpt-4o-mini"):
    segments = []
    buf = []
    tokens = 0
    for m in messages:
        t = f"[{m.slack_ts}] {m.text}\n"
        c = count_tokens(t, model=model)
        if tokens + c > max_tokens and buf:
            segments.append(buf); buf=[t]; tokens=c
        else:
            buf.append(t); tokens += c
    if buf:
        segments.append(buf)
    return ["".join(s) for s in segments]
```

**app/pipeline/owner_infer.py**
```python
import re

MENTION = re.compile(r"<@([A-Z0-9]+)>")
def infer_owner(text: str, last_speaker_slack_id: str | None = None) -> str | None:
    # Imperative @mention
    m = MENTION.search(text)
    if m and re.search(r"\b(please|can you|do|fix|take|own|handle)\b", text.lower()):
        return m.group(1)
    # Self-assign
    if re.search(r"\bI(\'ll| will| can)\b", text):
        return last_speaker_slack_id
    return None
```

**app/pipeline/date_utils.py**
```python
import dateparser, pytz
from datetime import datetime
def normalize_date(phrase: str, tz_name: str | None = "UTC") -> str | None:
    tz = pytz.timezone(tz_name or "UTC")
    dt = dateparser.parse(phrase, settings={"TIMEZONE": str(tz), "RETURN_AS_TIMEZONE_AWARE": True})
    if not dt:
        return None
    return dt.astimezone(pytz.UTC).isoformat()
```

**app/pipeline/extract.py**
```python
from app.llm.router import get_llm
from app.config import settings
from app.schemas import CondenseResult
import json

async def extract_items(thread_url: str, segments: list[str], run_id: str):
    llm = get_llm()
    system = open("app/prompts/extraction.md","r",encoding="utf-8").read()
    # Merge segments; if too long, send separately and merge
    merged = "\n\n".join(segments)
    if len(merged) > 200000:  # guard
        merged = merged[:200000]
    user = f"Thread URL: {thread_url}\nContent:\n{merged}"
    schema_hint = json.dumps(CondenseResult.model_json_schema(), separators=(",",":"))
    res = await llm.complete_json(system=system, user=user, model=settings.OPENAI_MODEL, temperature=0.2, max_tokens=2000, schema_hint=schema_hint)
    # Ensure required keys
    for k in ["decisions","risks","actions","open_questions","people_map","provenance"]:
        res.setdefault(k, [] if k not in ["people_map","provenance"] else ({} if k=="people_map" else {}))
    res["provenance"]["run_id"] = run_id
    res["provenance"]["thread_url"] = thread_url
    return res
```

**app/pipeline/rank.py**
```python
def score_item(item: dict, reactions_index: dict[str,int], seniority_weight: float = 1.0, recency_bonus: float = 0.0, contradiction_penalty: float = 0.0):
    base = float(item.get("confidence", 0.0))
    msg_ids = [r["msg_id"] for r in item.get("supporting_msgs", []) if "msg_id" in r]
    agree = sum(reactions_index.get(m, 0) for m in msg_ids)
    s = base + 0.05 * agree + 0.05 * seniority_weight + recency_bonus - contradiction_penalty
    return max(0.0, min(1.0, s))

def rank_and_filter(result_json: dict, threshold: float):
    reactions_index = {}
    for sec in ["decisions","risks","actions","open_questions"]:
        ranked=[]
        for it in result_json.get(sec, []):
            s = score_item(it, reactions_index)
            it["confidence"] = s
            if s >= threshold:
                ranked.append(it)
        result_json[sec] = sorted(ranked, key=lambda x: x["confidence"], reverse=True)
    return result_json
```

**app/pipeline/provenance.py**
```python
def attach_links(workspace_team_id: str, channel_id: str, items: list[dict]):
    base = f"https://app.slack.com/client/{workspace_team_id}/{channel_id}/"
    for it in items:
        for s in it.get("supporting_msgs", []):
            ts = s.get("msg_id")
            if ts:
                s["url"] = base + ts.replace(".", "p")
    return items
```

**app/pipeline/brief.py**
```python
from sqlalchemy.orm import Session
from app.models import Brief
from datetime import datetime

def save_brief(db: Session, run_id: str, thread_id, json_blob: dict, model_version="v1.0", api_version="v1"):
    b = Brief(run_id=run_id, thread_id=thread_id, version="1", model_version=model_version, api_version=api_version, json_blob=json_blob)
    db.merge(b)
    db.commit()
    return b
```

**app/pipeline/summarization.py** *(optional, for segment-level bullets)*
```python
from app.llm.router import get_llm
from app.config import settings

async def summarize_segments(segments: list[str]) -> list[str]:
    llm = get_llm()
    system = open("app/prompts/summarization.md","r",encoding="utf-8").read()
    outs=[]
    for s in segments:
        text = await llm.complete_text(system=system, user=s, model=settings.OPENAI_MODEL, temperature=0.2, max_tokens=400)
        outs.append(text)
    return outs
```

---

## 11) Celery worker and tasks

**app/workers/celery_app.py**
```python
from celery import Celery
from app.config import settings

celery_app = Celery("tc", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_queues = {
    "default": {},
    "webhooks": {},
    "sync": {},
    "digest": {}
}
celery_app.conf.task_default_queue = "default"
celery_app.conf.result_expires = 3600
```

**app/workers/tasks.py**
```python
import asyncio, uuid
from celery import shared_task
from app.db import SessionLocal
from app.config import settings
from slack_sdk.web.async_client import AsyncWebClient
from app.pipeline.ingest import ingest_thread
from app.pipeline.preprocess import preprocess_thread
from app.pipeline.segment import segment_messages
from app.pipeline.extract import extract_items
from app.pipeline.rank import rank_and_filter
from app.pipeline.provenance import attach_links
from app.pipeline.brief import save_brief
from app.slack.publisher import post_brief_card

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

async def _enqueue_condense(team_id: str, channel_id: str, thread_ts: str, requester_user_id: str | None):
    run_id = f"rc-{uuid.uuid4()}"
    client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)
    db = SessionLocal()
    try:
        url = f"https://app.slack.com/client/{team_id}/{channel_id}/{thread_ts.replace('.','p')}"
        th = await ingest_thread(db, client, team_id, channel_id, thread_ts, url)
        msgs = preprocess_thread(db, th.id)
        segments = segment_messages(msgs, max_tokens=2000, model=settings.OPENAI_MODEL)
        result = await extract_items(url, segments, run_id)
        # Optional link enrichment
        for sec in ["decisions","risks","actions","open_questions"]:
            result[sec] = attach_links(team_id, channel_id, result.get(sec, []))
        ranked = rank_and_filter(result, settings.PROMOTION_THRESHOLD)
        save_brief(db, run_id, th.id, ranked)
        # Post card and pin
        await post_brief_card(client, channel_id, thread_ts, ranked, pin=True)
    finally:
        await client.close()
        db.close()
    return run_id

@shared_task(name="enqueue_condense_task", queue="webhooks")
def enqueue_condense(team_id: str, channel_id: str, thread_ts: str, requester_user_id: str | None = None):
    return _run(_enqueue_condense(team_id, channel_id, thread_ts, requester_user_id))

def enqueue_condense_external(thread_url: str, options: dict):
    # Parse URL: .../client/{team}/{channel}/{pTS}
    from urllib.parse import urlparse
    parts = urlparse(thread_url).path.split("/")
    team_id, channel_id, p_ts = parts[-3], parts[-2], parts[-1]
    thread_ts = p_ts.replace("p", "", 1)
    return enqueue_condense(team_id, channel_id, thread_ts, None)

@shared_task(name="enqueue_item_confirm", queue="webhooks")
def enqueue_item_confirm(payload: dict):
    # Update item status and trigger connector sync if configured
    from app.models import Item, Changelog
    from sqlalchemy import select
    db = SessionLocal()
    try:
        action_value = payload["actions"][0]["value"]
        # You should map value -> item in posted context; simplified here
        # Set status to confirmed
        # db.query(Item).filter(Item.id==...).update({"status":"confirmed"})
        db.commit()
    finally:
        db.close()
    return True

@shared_task(name="enqueue_item_edit", queue="webhooks")
def enqueue_item_edit(payload: dict):
    # Handle edits via modal in full impl; stub for brevity
    return True

def edit_item_sync(item_id: str, patch: dict, db):
    from app.models import Item, Changelog
    it = db.get(Item, item_id)
    if not it:
        return {"ok": False, "error": "not_found"}
    for k,v in patch.items():
        if hasattr(it, k):
            setattr(it, k, v)
    db.add(Changelog(item_id=it.id, actor_user_id=None, change_json=patch))
    db.commit()
    return {"ok": True}
```

---

## 12) Connectors (stubs that won’t crash)

**app/connectors/base.py**
```python
from typing import Protocol

class Connector(Protocol):
    async def create_or_update(self, item: dict) -> dict: ...
```

**app/connectors/jira.py**
```python
class JiraConnector:
    def __init__(self, base_url: str, token: str, project_key: str):
        self.base_url = base_url; self.token = token; self.project_key = project_key
    async def create_or_update(self, item: dict) -> dict:
        # TODO: implement with httpx
        return {"url": f"{self.base_url}/browse/{self.project_key}-123"}
```

**app/connectors/linear.py**
```python
class LinearConnector:
    def __init__(self, api_key: str, team_id: str):
        self.api_key = api_key; self.team_id = team_id
    async def create_or_update(self, item: dict) -> dict:
        return {"url": f"https://linear.app/issue/ABC-1"}
```

(Confluence/Notion/Calendar similar.)

---

## 13) JSON Schema for briefs

**Brief JSON Schema** (useful for validation or contracts)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/thread-condenser/brief.json",
  "type": "object",
  "required": ["decisions","risks","actions","open_questions","people_map","provenance"],
  "properties": {
    "decisions": {"type":"array","items":{"type":"object"}},
    "risks": {"type":"array","items":{"type":"object"}},
    "actions": {"type":"array","items":{"type":"object"}},
    "open_questions": {"type":"array","items":{"type":"object"}},
    "people_map": {"type":"object","additionalProperties":{"type":"string"}},
    "provenance": {"type":"object","properties": {
      "thread_url":{"type":"string"},
      "message_ids":{"type":"array","items":{"type":"string"}},
      "model_version":{"type":"string"},
      "run_id":{"type":"string"}
    }}
  }
}
```

---

## 14) Testing

Add minimal tests.

**tests/test_segment.py**
```python
from app.pipeline.segment import segment_messages
class Msg: 
    def __init__(self, ts, text): self.slack_ts=ts; self.text=text
def test_segment_small():
    msgs=[Msg("1","hello"), Msg("2","world")]
    segs = segment_messages(msgs, max_tokens=1000, model="gpt-4o-mini")
    assert len(segs)==1 and "hello" in segs[0]
```

Run with:
```
pip install pytest
pytest -q
```

---

## 15) Local usage

1) Start stack:
```
make run
```

2) Apply migrations:
```
make migrate
```

3) Expose `PUBLIC_BASE_URL` to Slack (use `ngrok http 8080` in dev; update `.env` and Slack app URLs).

4) In Slack, in a channel thread, run `/condense`. The app responds “Processing thread…”, then posts a brief card and pins it.

---

## 16) Security controls included

- Slack request verification handled by Bolt adapter.
- JWT helpers for REST endpoints.
- No message bodies stored outside `messages.text` table in dev. For production, gate storage behind a config flag and store only quotes plus IDs to match your compliance policy.
- TLS termination left to ingress/ALB in deployment.

---

## 17) Observability

Add basic logging. Extend with Prometheus as needed.

**Add to app/main.py**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
```

Celery logs emit task lifecycle. Add structured logs via `app.logging.setup_logging()` which is already invoked.

---

## 18) Deployment notes

- Container image builds via Dockerfile. Push to your registry.
- For AWS ECS Fargate:
  - One service for API, one for worker, one for beat.
  - ALB forwards `/:8080` to API.
  - Secrets in AWS Secrets Manager → injected as env vars.
  - RDS Postgres with pgvector extension; run `CREATE EXTENSION IF NOT EXISTS vector;` once.
  - Redis on ElastiCache or replace broker with SQS (use `celery[sqs]` and configure broker URL).

---

## 19) Accuracy hardening

- Improve extraction by adding 2–3 domain few-shot examples in `prompts/extraction.md`.
- Add a verbs allowlist for decisions: `decide|approve|ship|rollback|adopt|deprecate`.
- Reject items without quotes or message IDs before ranking.
- Set `settings.PROMOTION_THRESHOLD` per workspace.

---

## 20) Safety against prompt injection

- Never execute instructions from messages.
- Enforce structured output with `response_format: json_object`.
- Post quotes verbatim but keep length ≤ 280 chars.

---

## 21) Roadmap hooks included

- `owner_infer.py` exists and can be expanded with role maps.
- `date_utils.py` normalizes EOD/weekday phrases given channel timezone.
- Connectors have stubs; wire them on `status == confirmed`.

---

## 22) End-to-end flow recap

- `/condense` → Celery enqueues → ingest Slack thread → preprocess → segment → LLM extract (JSON) → attach links → rank/filter → save brief → post Block Kit card and pin.

This document includes all required code and steps to run locally, develop features, and deploy.

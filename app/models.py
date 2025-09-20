from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


def ulid() -> uuid.UUID:
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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    slack_team_id = Column(String, unique=True, nullable=True)
    m365_tenant_id = Column(String, nullable=True)
    bot_user_id = Column(String, nullable=True)
    teams_bot_app_id = Column(String, nullable=True)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Channel(Base):
    __tablename__ = "channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    platform = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    parent_resource_id = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    mailbox_address = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    policies = Column(JSON, default=dict)
    metadata = Column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("workspace_id", "platform", "external_id"),)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    platform = Column(String, nullable=False)
    platform_user_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    role = Column(String, nullable=True)
    seniority_weight = Column(Float, default=1.0)
    metadata = Column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("workspace_id", "platform", "platform_user_id"),)


class Thread(Base):
    __tablename__ = "threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False)
    platform = Column(String, nullable=False)
    source_thread_id = Column(String, nullable=False)
    source_parent_id = Column(String, nullable=True)
    source_url = Column(String, nullable=False)
    content_hash = Column(String, nullable=True)
    delta_token = Column(String, nullable=True)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("workspace_id", "platform", "source_thread_id"),)


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    platform = Column(String, nullable=False)
    source_msg_id = Column(String, nullable=False)
    parent_msg_id = Column(String, nullable=True)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    text = Column(Text, nullable=False)
    text_hash = Column(String, nullable=False)
    lang = Column(String, nullable=True)
    reactions_json = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("thread_id", "source_msg_id"),
        Index("ix_msg_thread_source", "thread_id", "source_msg_id"),
    )


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
    type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    due_at_utc = Column(DateTime, nullable=True)
    likelihood = Column(String, nullable=True)
    impact = Column(String, nullable=True)
    mitigation = Column(Text, nullable=True)
    status = Column(String, default="proposed")
    confidence = Column(Float, default=0.0)
    promoted_at = Column(DateTime, nullable=True)
    source_platform = Column(String, nullable=False)


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
    platform = Column(String, nullable=False)
    native_user_id = Column(String, nullable=True)
    email = Column(String, nullable=True)
    metadata = Column(JSON, default=dict)


class GraphSubscription(Base):
    __tablename__ = "graph_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=ulid)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    platform = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    notification_url = Column(String, nullable=False)
    delta_token = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    metadata = Column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("workspace_id", "platform", "resource"),)


class Brief(Base):
    __tablename__ = "briefs"

    run_id = Column(String, primary_key=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    platform = Column(String, nullable=False)
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

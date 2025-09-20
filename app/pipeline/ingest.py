from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, List, Optional

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from app.models import Channel, Message, Thread, User, Workspace
from app.platforms.graph_client import GraphClient

UTC = timezone.utc
BR_RE = re.compile(r"<br\s*/?>|</p>", re.I)
TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    text = BR_RE.sub("\n", value)
    text = TAG_RE.sub("", text)
    return html.unescape(text).strip()


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ensure_workspace(db: Session, platform: str, workspace_key: str) -> Workspace:
    if platform == "slack":
        lookup = {"slack_team_id": workspace_key}
    else:
        lookup = {"m365_tenant_id": workspace_key}
    ws = db.query(Workspace).filter_by(**lookup).first()
    if not ws:
        ws = Workspace(
            tenant_id=None,
            slack_team_id=workspace_key if platform == "slack" else None,
            m365_tenant_id=workspace_key if platform != "slack" else None,
        )
        db.add(ws)
        db.commit()
    return ws


def _ensure_channel(
    db: Session,
    workspace: Workspace,
    platform: str,
    external_id: str,
    *,
    parent_resource_id: Optional[str] = None,
    display_name: Optional[str] = None,
    mailbox: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Channel:
    ch = (
        db.query(Channel)
        .filter_by(
            workspace_id=workspace.id, platform=platform, external_id=external_id
        )
        .first()
    )
    if not ch:
        ch = Channel(
            workspace_id=workspace.id,
            platform=platform,
            external_id=external_id,
            parent_resource_id=parent_resource_id,
            display_name=display_name,
            mailbox_address=mailbox,
            metadata=metadata or {},
        )
        db.add(ch)
    else:
        if parent_resource_id:
            ch.parent_resource_id = parent_resource_id
        if display_name and not ch.display_name:
            ch.display_name = display_name
        if mailbox:
            ch.mailbox_address = mailbox
        if metadata:
            merged = ch.metadata or {}
            merged.update(metadata)
            ch.metadata = merged
    db.commit()
    return ch


def _ensure_user(
    db: Session,
    workspace: Workspace,
    platform: str,
    native_id: Optional[str],
    display_name: Optional[str],
    *,
    email: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[User]:
    if not native_id:
        return None
    user = (
        db.query(User)
        .filter_by(
            workspace_id=workspace.id, platform=platform, platform_user_id=native_id
        )
        .first()
    )
    if not user:
        user = User(
            workspace_id=workspace.id,
            platform=platform,
            platform_user_id=native_id,
            display_name=display_name or native_id,
            email=email,
            metadata=metadata or {},
        )
        db.add(user)
        db.commit()
        return user
    updated = False
    if display_name and user.display_name != display_name:
        user.display_name = display_name
        updated = True
    if email and user.email != email:
        user.email = email
        updated = True
    if metadata:
        merged = user.metadata or {}
        merged.update(metadata)
        user.metadata = merged
        updated = True
    if updated:
        db.commit()
    return user


def _ensure_thread(
    db: Session,
    workspace: Workspace,
    channel: Channel,
    platform: str,
    source_thread_id: str,
    *,
    parent_resource_id: Optional[str],
    thread_url: str,
) -> Thread:
    th = (
        db.query(Thread)
        .filter_by(
            workspace_id=workspace.id,
            platform=platform,
            source_thread_id=source_thread_id,
        )
        .first()
    )
    if not th:
        th = Thread(
            workspace_id=workspace.id,
            channel_id=channel.id,
            platform=platform,
            source_thread_id=source_thread_id,
            source_parent_id=parent_resource_id,
            source_url=thread_url,
        )
        db.add(th)
    else:
        if thread_url and th.source_url != thread_url:
            th.source_url = thread_url
        if parent_resource_id and th.source_parent_id != parent_resource_id:
            th.source_parent_id = parent_resource_id
    db.commit()
    return th


def _persist_message(
    db: Session,
    thread: Thread,
    platform: str,
    native_id: str,
    *,
    parent_id: Optional[str],
    user: Optional[User],
    text: str,
    created_at: datetime,
    reactions: Optional[Dict[str, int]],
    metadata: Dict[str, Any],
) -> None:
    canonical = f"{platform}:{native_id}"
    metadata = metadata or {}
    metadata.setdefault("canonical_id", canonical)
    msg = (
        db.query(Message)
        .filter_by(thread_id=thread.id, source_msg_id=native_id)
        .first()
    )
    text_hash = sha1(text.encode("utf-8")).hexdigest()
    if msg:
        msg.text = text
        msg.text_hash = text_hash
        msg.parent_msg_id = parent_id
        msg.author_user_id = user.id if user else None
        msg.reactions_json = reactions or {}
        msg.metadata_json = metadata
        msg.created_at = created_at
    else:
        db.add(
            Message(
                thread_id=thread.id,
                platform=platform,
                source_msg_id=native_id,
                parent_msg_id=parent_id,
                author_user_id=user.id if user else None,
                text=text,
                text_hash=text_hash,
                reactions_json=reactions or {},
                metadata_json=metadata,
                created_at=created_at,
            )
        )


def _canonical_ts(ts: str) -> float:
    try:
        return float(ts)
    except ValueError:
        return float(ts.replace(".", ""))


async def _ingest_slack(
    db: Session, slack_client: AsyncWebClient, thread_ref: Dict[str, Any]
) -> Thread:
    team_id = thread_ref["team_id"]
    channel_id = thread_ref["channel_id"]
    thread_ts = thread_ref["thread_ts"]
    workspace = _ensure_workspace(db, "slack", team_id)
    channel = _ensure_channel(
        db,
        workspace,
        "slack",
        channel_id,
        parent_resource_id=team_id,
        metadata={"team_id": team_id},
    )
    thread_url = f"https://app.slack.com/client/{team_id}/{channel_id}/{thread_ts.replace('.', 'p')}"
    thread = _ensure_thread(
        db,
        workspace,
        channel,
        "slack",
        thread_ts,
        parent_resource_id=channel_id,
        thread_url=thread_url,
    )
    messages: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        resp = await slack_client.conversations_replies(
            channel=channel_id, ts=thread_ts, cursor=cursor, limit=200
        )
        messages.extend(resp.get("messages", []))
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    user_cache: Dict[str, User] = {}
    for payload in messages:
        user_id = payload.get("user") or payload.get("bot_id")
        user: Optional[User] = None
        if user_id:
            user = user_cache.get(user_id)
            if not user:
                display_name = user_id
                email = None
                if user_id.startswith("U"):
                    try:
                        info = await slack_client.users_info(user=user_id)
                        profile = info["user"]["profile"]
                        display_name = (
                            profile.get("display_name")
                            or profile.get("real_name")
                            or user_id
                        )
                        email = profile.get("email")
                    except Exception:  # pragma: no cover - network failure
                        display_name = user_id
                user = _ensure_user(
                    db, workspace, "slack", user_id, display_name, email=email
                )
                if user:
                    user_cache[user_id] = user
        ts = payload["ts"]
        created_at = datetime.fromtimestamp(float(ts), tz=UTC)
        parent_ts = payload.get("thread_ts")
        parent_id = parent_ts if parent_ts and parent_ts != ts else None
        reactions = {r["name"]: r.get("count", 0) for r in payload.get("reactions", [])}
        metadata = {
            "team_id": team_id,
            "channel_id": channel_id,
            "permalink": f"https://app.slack.com/client/{team_id}/{channel_id}/{ts.replace('.', 'p')}",
            "thread_ts": payload.get("thread_ts"),
        }
        _persist_message(
            db,
            thread,
            "slack",
            ts,
            parent_id=parent_id,
            user=user,
            text=payload.get("text") or "",
            created_at=created_at,
            reactions=reactions,
            metadata=metadata,
        )
    db.commit()
    return thread


async def _ingest_teams(
    db: Session, graph_client: GraphClient, thread_ref: Dict[str, Any]
) -> Thread:
    tenant_id = thread_ref.get("tenant_id") or ""
    workspace_key = (
        tenant_id or thread_ref.get("team_id") or thread_ref.get("chat_id") or ""
    )
    workspace = _ensure_workspace(db, "msteams", workspace_key)
    conversation_type = thread_ref.get("conversation_type", "channel")
    if conversation_type == "chat":
        chat_id = thread_ref["chat_id"]
        base = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
        external_id = chat_id
        parent_resource = chat_id
        channel_metadata = {"conversation_type": "chat"}
    else:
        team_id = thread_ref["team_id"]
        channel_id = thread_ref["channel_id"]
        base = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
        external_id = channel_id
        parent_resource = team_id
        channel_metadata = {"team_id": team_id, "conversation_type": "channel"}
    channel = _ensure_channel(
        db,
        workspace,
        "msteams",
        external_id,
        parent_resource_id=parent_resource,
        metadata=channel_metadata,
    )
    message_id = thread_ref["message_id"]
    root = await graph_client.get(f"{base}/{message_id}")
    replies = await graph_client.list(f"{base}/{message_id}/replies")
    payloads = [root] + replies
    thread_url = root.get("webUrl", "")
    thread = _ensure_thread(
        db,
        workspace,
        channel,
        "msteams",
        message_id,
        parent_resource_id=external_id,
        thread_url=thread_url,
    )
    for payload in payloads:
        from_part = payload.get("from", {})
        user_info = from_part.get("user", {})
        native_user_id = user_info.get("id") or from_part.get("application", {}).get(
            "id"
        )
        display_name = (
            user_info.get("displayName")
            or from_part.get("application", {}).get("displayName")
            or native_user_id
        )
        email = user_info.get("email") or user_info.get("userPrincipalName")
        user = _ensure_user(
            db, workspace, "msteams", native_user_id, display_name, email=email
        )
        body = payload.get("body", {}).get("content", "")
        text = _html_to_text(body)
        created_at = _parse_dt(payload.get("createdDateTime"))
        reactions: Dict[str, int] = {}
        for reaction in payload.get("reactions", []):
            key = reaction.get("reactionType", "other")
            reactions[key] = reactions.get(key, 0) + 1
        metadata = {
            "webUrl": payload.get("webUrl"),
            "raw_html": body,
            "createdDateTime": payload.get("createdDateTime"),
            "lastModifiedDateTime": payload.get("lastModifiedDateTime"),
        }
        parent_id = payload.get("replyToId")
        if not parent_id and payload.get("id") != message_id:
            parent_id = message_id
        _persist_message(
            db,
            thread,
            "msteams",
            payload["id"],
            parent_id=parent_id,
            user=user,
            text=text,
            created_at=created_at,
            reactions=reactions,
            metadata=metadata,
        )
    db.commit()
    return thread


async def _ingest_outlook(
    db: Session, graph_client: GraphClient, thread_ref: Dict[str, Any]
) -> Thread:
    mailbox = thread_ref["mailbox"]
    conversation_id = thread_ref["conversation_id"]
    tenant_id = thread_ref.get("tenant_id") or ""
    workspace_key = tenant_id or mailbox
    workspace = _ensure_workspace(db, "outlook", workspace_key)
    channel = _ensure_channel(
        db,
        workspace,
        "outlook",
        mailbox,
        parent_resource_id=tenant_id or mailbox,
        mailbox=mailbox,
    )
    params = {
        "$filter": f"conversationId eq '{conversation_id}'",
        "$orderby": "createdDateTime asc",
    }
    payloads = await graph_client.list(
        f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages",
        params=params,
    )
    thread_url = payloads[0].get("webLink", "") if payloads else ""
    thread = _ensure_thread(
        db,
        workspace,
        channel,
        "outlook",
        conversation_id,
        parent_resource_id=mailbox,
        thread_url=thread_url,
    )
    previous_id: Optional[str] = None
    for payload in payloads:
        sender = payload.get("from", {}).get("emailAddress", {})
        native_user_id = sender.get("address") or sender.get("name")
        display_name = sender.get("name") or native_user_id
        email = sender.get("address")
        user = _ensure_user(
            db, workspace, "outlook", native_user_id, display_name, email=email
        )
        body = payload.get("body", {}).get("content", "")
        text = _html_to_text(body)
        created_at = _parse_dt(
            payload.get("sentDateTime") or payload.get("receivedDateTime")
        )
        metadata = {
            "webLink": payload.get("webLink"),
            "internetMessageId": payload.get("internetMessageId"),
            "conversationIndex": payload.get("conversationIndex"),
            "toRecipients": payload.get("toRecipients", []),
            "ccRecipients": payload.get("ccRecipients", []),
            "raw_html": body,
        }
        parent_id = payload.get("replyToId") or payload.get("inReplyTo") or previous_id
        native_id = payload["id"]
        _persist_message(
            db,
            thread,
            "outlook",
            native_id,
            parent_id=parent_id,
            user=user,
            text=text,
            created_at=created_at,
            reactions={},
            metadata=metadata,
        )
        previous_id = native_id
    db.commit()
    return thread


async def ingest_thread(
    db: Session,
    platform: str,
    thread_ref: Dict[str, Any],
    *,
    slack_client: Optional[AsyncWebClient] = None,
    graph_client: Optional[GraphClient] = None,
) -> Thread:
    if platform == "slack":
        if not slack_client:
            raise RuntimeError("Slack client is required for Slack ingestion")
        return await _ingest_slack(db, slack_client, thread_ref)
    if platform == "msteams":
        if not graph_client:
            raise RuntimeError("Graph client is required for Microsoft Teams ingestion")
        return await _ingest_teams(db, graph_client, thread_ref)
    if platform == "outlook":
        if not graph_client:
            raise RuntimeError("Graph client is required for Outlook ingestion")
        return await _ingest_outlook(db, graph_client, thread_ref)
    raise ValueError(f"Unsupported platform {platform}")

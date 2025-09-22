from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Brief

router = APIRouter(prefix="/v1")


class CondenseRequest(BaseModel):
    platform: str
    thread_ref: dict
    options: dict | None = None


class GraphNotification(BaseModel):
    value: list[dict] = []
    validationToken: str | None = None


_GRAPH_RESOURCE_ENTITIES = {
    "beta",
    "channels",
    "chats",
    "mailFolders",
    "messages",
    "me",
    "replies",
    "teams",
    "users",
    "v1.0",
}


def _parse_graph_resource(resource: str) -> Dict[str, List[str]]:
    tokens = [tok for tok in resource.strip("/").split("/") if tok]
    parsed: Dict[str, List[str]] = {}
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        name = token
        value = ""
        if "(" in token and token.endswith(")"):
            name, rest = token.split("(", 1)
            value = rest[:-1]
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            idx += 1
        else:
            next_token = tokens[idx + 1] if idx + 1 < len(tokens) else None
            if next_token and next_token not in _GRAPH_RESOURCE_ENTITIES:
                value = next_token
                idx += 2
            else:
                idx += 1
        value = unquote(value)
        parsed.setdefault(name, []).append(value)
    return parsed


def _base_thread_ref(resource_data: dict[str, Any]) -> dict[str, Any]:
    thread_ref = {
        key: value
        for key, value in resource_data.items()
        if key not in {"id", "conversationId", "tenantId", "tenantID"}
    }
    conversation_id = resource_data.get("conversationId")
    if conversation_id:
        thread_ref["conversation_id"] = conversation_id
    tenant_id = resource_data.get("tenantId") or resource_data.get("tenantID")
    if tenant_id:
        thread_ref["tenant_id"] = tenant_id
    return thread_ref


def _build_teams_thread_ref(
    resource: str, resource_data: dict[str, Any]
) -> Optional[dict[str, Any]]:
    parsed = _parse_graph_resource(resource)
    thread_ref = _base_thread_ref(resource_data)
    thread_ref["resource"] = resource
    channel_identity = resource_data.get("channelIdentity") or {}
    team_id = (
        channel_identity.get("teamId")
        or resource_data.get("teamId")
        or (parsed.get("teams") or [None])[0]
    )
    channel_id = (
        channel_identity.get("channelId")
        or resource_data.get("channelId")
        or (parsed.get("channels") or [None])[0]
    )
    chat_id = resource_data.get("chatId") or (parsed.get("chats") or [None])[0]
    conversation_type = "chat" if chat_id else "channel"
    if conversation_type == "chat":
        if not chat_id:
            chat_id = resource_data.get("conversationId")
        if not chat_id:
            return None
        thread_ref["chat_id"] = chat_id
    else:
        if not team_id or not channel_id:
            return None
        thread_ref["team_id"] = team_id
        thread_ref["channel_id"] = channel_id
    thread_ref["conversation_type"] = conversation_type
    message_candidates = parsed.get("messages") or []
    event_message_id = resource_data.get("id")
    message_id = (
        resource_data.get("replyToId")
        or (message_candidates[0] if message_candidates else None)
        or event_message_id
    )
    if not message_id:
        return None
    thread_ref["message_id"] = message_id
    if event_message_id and event_message_id != message_id:
        thread_ref["event_message_id"] = event_message_id
    return thread_ref


def _build_outlook_thread_ref(
    resource: str, resource_data: dict[str, Any]
) -> Optional[dict[str, Any]]:
    parsed = _parse_graph_resource(resource)
    thread_ref = _base_thread_ref(resource_data)
    conversation_id = thread_ref.get("conversation_id")
    message_id = resource_data.get("id")
    if message_id:
        thread_ref["message_id"] = message_id
    mailbox = (
        resource_data.get("mailbox")
        or resource_data.get("userId")
        or resource_data.get("mailboxId")
        or (parsed.get("users") or [None])[0]
        or (parsed.get("me") or [None])[0]
    )
    if not mailbox or not conversation_id:
        return None
    thread_ref["mailbox"] = mailbox
    thread_ref["resource"] = resource
    return thread_ref


@router.post("/condense")
def condense(req: CondenseRequest, db: Session = Depends(get_db)):
    from app.workers.tasks import enqueue_condense_external

    run_id = enqueue_condense_external(req.platform, req.thread_ref, req.options or {})
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


@router.get("/graph/notifications")
def graph_validation(validationToken: str):
    return Response(content=validationToken, media_type="text/plain")


@router.post("/graph/notifications")
def graph_notifications(payload: GraphNotification):
    from app.workers.tasks import trigger_condense

    if payload.validationToken:
        return Response(content=payload.validationToken, media_type="text/plain")
    for notification in payload.value:
        resource = notification.get("resource", "")
        resource_data = notification.get("resourceData", {})
        if "/messages" not in resource:
            continue
        thread_ref: Optional[dict[str, Any]]
        if any(
            marker in resource
            for marker in ("/chats/", "/teams/", "chats(", "teams(")
        ):
            platform = "msteams"
            thread_ref = _build_teams_thread_ref(resource, resource_data or {})
        else:
            platform = "outlook"
            thread_ref = _build_outlook_thread_ref(resource, resource_data or {})
        if not thread_ref:
            continue
        trigger_condense(platform, thread_ref, None)
    return {"status": "accepted"}

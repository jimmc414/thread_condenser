import asyncio
import uuid
from typing import Any, Dict, Optional

from celery import shared_task
from slack_sdk.web.async_client import AsyncWebClient

from app.config import settings
from app.db import SessionLocal
from app.platforms.graph_client import GraphClient
from app.platforms.registry import get_adapter
from app.pipeline.brief import save_brief
from app.pipeline.extract import extract_items
from app.pipeline.ingest import ingest_thread
from app.pipeline.preprocess import preprocess_thread
from app.pipeline.provenance import attach_links
from app.pipeline.rank import rank_and_filter
from app.pipeline.segment import segment_messages

_graph_client: Optional[GraphClient] = None


def _get_graph_client() -> GraphClient:
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphClient()
    return _graph_client


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _build_reaction_index(messages) -> dict[str, int]:
    index: dict[str, int] = {}
    for msg in messages:
        metadata = msg.metadata_json or {}
        canonical = metadata.get("canonical_id")
        if not canonical:
            continue
        reactions = msg.reactions_json or {}
        if isinstance(reactions, dict):
            index[canonical] = sum(int(v) for v in reactions.values())
        elif isinstance(reactions, list):
            index[canonical] = sum(int(r.get("count", 0)) for r in reactions)
    return index


async def _process_condense(
    platform: str,
    thread_ref: Dict[str, Any],
    requester_user_id: str | None,
    options: Dict[str, Any],
) -> str:
    run_id = options.get("run_id") or f"rc-{uuid.uuid4()}"
    slack_client: AsyncWebClient | None = None
    db = SessionLocal()
    try:
        graph = _get_graph_client() if platform in {"msteams", "outlook"} else None
        if platform == "slack":
            slack_client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)
        thread = await ingest_thread(
            db,
            platform,
            thread_ref,
            slack_client=slack_client,
            graph_client=graph,
        )
        messages = preprocess_thread(db, thread.id)
        segments = segment_messages(
            messages, max_tokens=2000, model=settings.OPENAI_MODEL
        )
        brief = await extract_items(
            platform, thread.source_url, thread_ref, segments, run_id
        )
        reactions_index = _build_reaction_index(messages)
        ranked = rank_and_filter(brief, reactions_index, settings.PROMOTION_THRESHOLD)
        ranked = attach_links(messages, ranked)
        save_brief(db, run_id, thread.id, ranked)
        adapter = get_adapter(platform)
        context = adapter.context_from_thread_ref(thread_ref, requester_user_id)
        await adapter.publish_brief(context, ranked)
    finally:
        if slack_client is not None:
            await slack_client.close()
        db.close()
    return run_id


@shared_task(name="enqueue_condense_task", queue="webhooks")
def enqueue_condense(
    platform: str,
    thread_ref: Dict[str, Any],
    requester_user_id: str | None = None,
    options: Dict[str, Any] | None = None,
):
    return _run(
        _process_condense(platform, thread_ref, requester_user_id, options or {})
    )


def trigger_condense(
    platform: str,
    thread_ref: Dict[str, Any],
    requester_user_id: str | None = None,
    options: Dict[str, Any] | None = None,
) -> str:
    run_id = f"rc-{uuid.uuid4()}"
    payload = options.copy() if options else {}
    payload["run_id"] = run_id
    enqueue_condense.delay(platform, thread_ref, requester_user_id, payload)
    return run_id


def enqueue_condense_external(
    platform: str, thread_ref: Dict[str, Any], options: Dict[str, Any]
):
    return trigger_condense(platform, thread_ref, None, options)


@shared_task(name="enqueue_item_confirm", queue="webhooks")
def enqueue_item_confirm(payload: dict):
    from app.models import Changelog, Item

    db = SessionLocal()
    try:
        action_value = payload.get("actions", [{}])[0].get("value")
        if not action_value:
            return True
        item = db.get(Item, action_value)
        if item:
            item.status = "confirmed"
            db.add(
                Changelog(
                    item_id=item.id,
                    actor_user_id=None,
                    change_json={"status": "confirmed"},
                )
            )
            db.commit()
    finally:
        db.close()
    return True


@shared_task(name="enqueue_item_edit", queue="webhooks")
def enqueue_item_edit(payload: dict):
    return True


def edit_item_sync(item_id: str, patch: dict, db):
    from app.models import Changelog, Item

    it = db.get(Item, item_id)
    if not it:
        return {"ok": False, "error": "not_found"}
    for key, value in patch.items():
        if hasattr(it, key):
            setattr(it, key, value)
    db.add(Changelog(item_id=it.id, actor_user_id=None, change_json=patch))
    db.commit()
    return {"ok": True}

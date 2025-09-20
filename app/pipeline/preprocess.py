from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models import Message


def _normalize_text(message: Message) -> str:
    text = message.text or ""
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    if message.platform in {"msteams", "outlook"}:
        text = text.replace("\r", "")
    return text.strip()


def preprocess_thread(db: Session, thread_id: str) -> List[Message]:
    msgs = (
        db.query(Message)
        .filter(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    for msg in msgs:
        msg.text = _normalize_text(msg)
        metadata = msg.metadata_json or {}
        canonical = (
            metadata.get("canonical_id") or f"{msg.platform}:{msg.source_msg_id}"
        )
        metadata["canonical_id"] = canonical
        metadata["source_msg_id"] = msg.source_msg_id
        msg.metadata_json = metadata
    db.commit()
    return msgs

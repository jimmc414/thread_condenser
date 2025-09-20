from typing import Iterable

from app.models import Message
from app.schemas import CondenseResult


def attach_links(messages: Iterable[Message], brief: CondenseResult) -> CondenseResult:
    index = {}
    for msg in messages:
        metadata = msg.metadata_json or {}
        canonical = (
            metadata.get("canonical_id") or f"{msg.platform}:{msg.source_msg_id}"
        )
        index[canonical] = msg

    for section in [
        brief.decisions,
        brief.risks,
        brief.actions,
        brief.open_questions,
    ]:
        for item in section:
            for ref in item.supporting_msgs:
                canonical = ref.msg_id or f"{ref.platform}:{ref.native_id}"
                msg = index.get(canonical)
                if not msg:
                    continue
                metadata = msg.metadata_json or {}
                ref.platform = msg.platform
                ref.native_id = msg.source_msg_id
                ref.msg_id = metadata.get("canonical_id", canonical)
                ref.url = (
                    metadata.get("permalink")
                    or metadata.get("webUrl")
                    or metadata.get("webLink")
                )
    return brief

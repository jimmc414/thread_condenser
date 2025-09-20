import json
from typing import Any, Dict

from app.config import settings
from app.llm.router import get_llm
from app.schemas import CondenseResult


async def extract_items(
    platform: str,
    thread_url: str,
    thread_ref: Dict[str, Any],
    segments: list[str],
    run_id: str,
) -> CondenseResult:
    llm = get_llm()
    system = open("app/prompts/extraction.md", "r", encoding="utf-8").read()
    merged = "\n\n".join(segments)
    if len(merged) > 200_000:
        merged = merged[:200_000]
    user = f"Source platform: {platform}\nThread URL: {thread_url}\nContent:\n{merged}"
    schema_hint = json.dumps(CondenseResult.model_json_schema(), separators=(",", ":"))
    raw = await llm.complete_json(
        system=system,
        user=user,
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        max_tokens=2000,
        schema_hint=schema_hint,
    )
    raw.setdefault("decisions", [])
    raw.setdefault("risks", [])
    raw.setdefault("actions", [])
    raw.setdefault("open_questions", [])
    raw.setdefault("people_map", {})
    provenance = raw.setdefault("provenance", {})
    provenance.setdefault("message_ids", [])
    provenance["thread_url"] = thread_url
    provenance["run_id"] = run_id
    provenance["source_platform"] = platform
    provenance["source_thread_ref"] = thread_ref
    raw["platform"] = platform
    result = CondenseResult.model_validate(raw)
    for section in [
        result.decisions,
        result.risks,
        result.actions,
        result.open_questions,
    ]:
        for item in section:
            for ref in item.supporting_msgs:
                if not ref.platform:
                    ref.platform = platform
                if not ref.msg_id:
                    ref.msg_id = f"{ref.platform}:{ref.native_id}"
    message_ids = {
        ref.msg_id
        for section in [
            result.decisions,
            result.risks,
            result.actions,
            result.open_questions,
        ]
        for item in section
        for ref in item.supporting_msgs
        if ref.msg_id
    }
    result.provenance.message_ids = sorted(message_ids)
    return result

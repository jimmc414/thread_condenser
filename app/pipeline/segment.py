from typing import Iterable, List

from app.llm.tokenization import count_tokens


def segment_messages(
    messages: Iterable, max_tokens: int = 2000, model: str = "gpt-4o-mini"
) -> List[str]:
    segments: list[str] = []
    buf: list[str] = []
    tokens = 0
    for message in messages:
        metadata = getattr(message, "metadata_json", None) or {}
        canonical = (
            metadata.get("canonical_id")
            or f"{message.platform}:{message.source_msg_id}"
        )
        line = f"[{canonical}] {message.text}\n"
        count = count_tokens(line, model=model)
        if tokens + count > max_tokens and buf:
            segments.append("".join(buf))
            buf = [line]
            tokens = count
        else:
            buf.append(line)
            tokens += count
    if buf:
        segments.append("".join(buf))
    return segments

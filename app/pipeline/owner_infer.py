import re
from typing import Optional

MENTION = re.compile(r"@([A-Za-z0-9._-]+)")
SELF_ASSIGN = re.compile(r"\bI(?:'m| will| can| shall)?\b", re.I)
IMPERATIVE = re.compile(r"\b(please|can you|could you|take|own|handle|drive)\b", re.I)


def infer_owner(
    text: str,
    mention_map: dict[str, str] | None = None,
    last_speaker: Optional[str] = None,
) -> Optional[str]:
    lowered = text.lower()
    tokens = mention_map or {}
    for token, canonical in tokens.items():
        if token in text and IMPERATIVE.search(lowered):
            return canonical
    match = MENTION.search(text)
    if match and IMPERATIVE.search(lowered):
        candidate = match.group(1)
        return tokens.get(candidate, candidate)
    if SELF_ASSIGN.search(text) and last_speaker:
        return last_speaker
    return None

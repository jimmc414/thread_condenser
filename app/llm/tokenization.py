import tiktoken


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:  # pragma: no cover - fallback path
        # Network access may be blocked during tests; fall back to a simple heuristic.
        return max(1, len(text) // 4 + 1)

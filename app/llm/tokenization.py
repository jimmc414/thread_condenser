def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        import tiktoken  # type: ignore
    except ImportError:  # pragma: no cover - fallback path
        tiktoken = None

    if tiktoken is not None:
        try:
            enc = tiktoken.encoding_for_model(model)
            return len(enc.encode(text))
        except Exception:  # pragma: no cover - fallback path
            pass

    # Network access may be blocked during tests; fall back to a simple heuristic.
    return max(1, len(text) // 4 + 1)

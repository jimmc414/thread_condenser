import sys

from app.llm.tokenization import count_tokens


def test_count_tokens_without_tiktoken():
    original_module = sys.modules.pop("tiktoken", None)
    sys.modules["tiktoken"] = None

    try:
        result = count_tokens("Hello world")
    finally:
        if original_module is not None:
            sys.modules["tiktoken"] = original_module
        else:
            sys.modules.pop("tiktoken", None)

    assert isinstance(result, int)
    assert result > 0

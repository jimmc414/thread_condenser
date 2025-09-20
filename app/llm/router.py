from app.config import settings
from app.llm.base import LLMClient
from app.llm.openai_chat import OpenAIChat


def get_llm() -> LLMClient:
    if settings.LLM_PROVIDER == "openai":
        return OpenAIChat()
    raise RuntimeError("Unsupported LLM_PROVIDER")

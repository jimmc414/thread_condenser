from typing import Any, Protocol


class LLMClient(Protocol):
    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
        schema_hint: str | None = None,
    ) -> dict: ...

    async def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

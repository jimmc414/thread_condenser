from __future__ import annotations

import json
from typing import Any, Dict

import httpx

from app.config import settings

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIChat:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(OPENAI_URL, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def complete_json(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        schema_hint: str | None = None,
    ) -> Dict[str, Any]:
        m = model or self.model
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
        }
        if schema_hint:
            payload["messages"].append(
                {"role": "system", "content": f"JSON schema hint: {schema_hint}"}
            )
        data = await self._post(payload)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def complete_text(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        m = model or self.model
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post(payload)
        return data["choices"][0]["message"]["content"]

from __future__ import annotations

import asyncio
import asyncio
from typing import Any, Dict, Optional

import httpx
import msal

from app.config import settings

SCOPES = ["https://graph.microsoft.com/.default"]


class GraphClient:
    def __init__(self) -> None:
        if (
            not settings.M365_CLIENT_ID
            or not settings.M365_CLIENT_SECRET
            or not settings.M365_TENANT_ID
        ):
            raise RuntimeError("Microsoft Graph credentials are not configured")
        self._app = msal.ConfidentialClientApplication(
            client_id=settings.M365_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.M365_TENANT_ID}",
            client_credential=settings.M365_CLIENT_SECRET,
        )

    async def _acquire_token(self) -> str:
        loop = asyncio.get_running_loop()

        def acquire() -> str:
            result = self._app.acquire_token_silent(SCOPES, account=None)
            if not result:
                result = self._app.acquire_token_for_client(scopes=SCOPES)
            if "access_token" not in result:
                raise RuntimeError("Unable to acquire Microsoft Graph token")
            return result["access_token"]

        return await loop.run_in_executor(None, acquire)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = await self._acquire_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    async def get(
        self, url: str, *, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self.request("GET", url, params=params)

    async def post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.request("POST", url, json=payload)

    async def patch(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.request("PATCH", url, json=payload)

    async def list(
        self, url: str, *, params: Optional[Dict[str, Any]] = None
    ) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        next_url: Optional[str] = url
        next_params = params or {}
        while next_url:
            page = await self.get(next_url, params=next_params)
            results.extend(page.get("value", []))
            next_url = page.get("@odata.nextLink")
            next_params = None
        return results

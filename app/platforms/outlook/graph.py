from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.platforms.base import PlatformAdapter, ThreadContext
from app.platforms.outlook.publisher import OutlookPublisher
from app.schemas import CondenseResult
from app.workers.tasks import trigger_condense


class OutlookAdapter(PlatformAdapter):
    platform = "outlook"

    def __init__(self) -> None:
        self.router = APIRouter()
        self.publisher = OutlookPublisher()
        self._register_routes()

    def serialize_thread_ref(self, context: ThreadContext) -> Dict[str, str]:
        ref = {
            "platform": self.platform,
            "mailbox": context.channel_id,
            "conversation_id": context.thread_id,
        }
        ref.update(context.metadata)
        return ref

    def context_from_thread_ref(
        self, thread_ref: Dict[str, Any], requester_id: str | None
    ) -> ThreadContext:
        mailbox = thread_ref.get("mailbox", "")
        conversation_id = thread_ref.get("conversation_id", "")
        tenant_id = thread_ref.get("tenant_id", "")
        metadata = thread_ref.copy()
        return ThreadContext(
            platform=self.platform,
            workspace_id=tenant_id or mailbox,
            channel_id=mailbox,
            thread_id=conversation_id,
            requester_id=requester_id,
            metadata=metadata,
        )

    async def acknowledge(self, context: ThreadContext) -> None:  # pragma: no cover
        return None

    async def send_processing_notice(self, context: ThreadContext) -> None:
        await self.publisher.post_processing(context.metadata)

    async def publish_brief(
        self, context: ThreadContext, brief: CondenseResult
    ) -> None:
        await self.publisher.publish_brief(context.metadata, brief)

    def _register_routes(self) -> None:
        @self.router.post("/outlook/actions")
        async def outlook_actions(request: Request):  # pragma: no cover - webhook
            payload = await request.json()
            try:
                mailbox = payload["mailbox"]
                message_id = payload["messageId"]
                conversation_id = payload["conversationId"]
                tenant_id = payload.get("tenantId", "")
            except KeyError as exc:
                raise HTTPException(
                    status_code=400, detail=f"missing field {exc.args[0]}"
                ) from exc

            context = ThreadContext(
                platform=self.platform,
                workspace_id=tenant_id,
                channel_id=mailbox,
                thread_id=conversation_id,
                requester_id=payload.get("requester"),
                metadata={
                    "mailbox": mailbox,
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "tenant_id": tenant_id,
                },
            )
            thread_ref = self.serialize_thread_ref(context)
            trigger_condense(context.platform, thread_ref, context.requester_id)
            await self.send_processing_notice(context)
            return {"status": "queued"}


adapter = OutlookAdapter()
router = adapter.router

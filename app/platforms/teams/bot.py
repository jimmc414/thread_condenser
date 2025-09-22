from __future__ import annotations

from typing import Any, Dict

from botbuilder.schema import Activity
from botframework.connector.auth import (
    JwtTokenValidation,
    SimpleCredentialProvider,
)
from fastapi import APIRouter, Request

from app.config import settings
from app.platforms.base import PlatformAdapter, ThreadContext
from app.platforms.teams.publisher import TeamsPublisher
from app.schemas import CondenseResult
from app.workers.tasks import trigger_condense


class TeamsAdapter(PlatformAdapter):
    platform = "msteams"

    def __init__(self) -> None:
        self.router = APIRouter()
        self.publisher = TeamsPublisher()
        app_id = settings.TEAMS_BOT_APP_ID or ""
        app_password = settings.TEAMS_BOT_APP_PASSWORD or ""
        self.credentials = SimpleCredentialProvider(app_id, app_password)
        self._register_routes()

    def serialize_thread_ref(self, context: ThreadContext) -> Dict[str, str]:
        metadata = context.metadata.copy()
        tenant_id = metadata.get("tenant_id") or context.workspace_id
        return {
            "platform": self.platform,
            "tenant_id": tenant_id,
            "team_id": metadata.get("team_id", ""),
            "channel_id": metadata.get("channel_id", ""),
            "chat_id": metadata.get("chat_id", ""),
            "conversation_type": metadata.get(
                "conversation_type",
                "chat" if metadata.get("chat_id") else "channel",
            ),
            "message_id": context.thread_id,
        }

    def context_from_thread_ref(
        self, thread_ref: Dict[str, Any], requester_id: str | None
    ) -> ThreadContext:
        tenant_id = thread_ref.get("tenant_id", "")
        conversation_type = thread_ref.get("conversation_type", "channel")
        channel_id = thread_ref.get("channel_id") or thread_ref.get("chat_id") or ""
        message_id = thread_ref.get("message_id", "")
        metadata = {
            "tenant_id": tenant_id,
            "team_id": thread_ref.get("team_id", ""),
            "channel_id": thread_ref.get("channel_id", ""),
            "chat_id": thread_ref.get("chat_id", ""),
            "conversation_type": conversation_type,
            "message_id": message_id,
        }
        return ThreadContext(
            platform=self.platform,
            workspace_id=tenant_id or thread_ref.get("team_id", ""),
            channel_id=channel_id,
            thread_id=message_id,
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
        @self.router.post("/teams/messages")
        async def teams_messages(request: Request):  # pragma: no cover - webhook
            body = await request.json()
            activity = Activity().deserialize(body)
            auth_header = request.headers.get("Authorization", "")
            await JwtTokenValidation.authenticate_request(
                activity, auth_header, self.credentials, channel_service=None
            )
            context = self._context_from_activity(activity)
            thread_ref = self.serialize_thread_ref(context)
            trigger_condense(context.platform, thread_ref, context.requester_id)
            await self.send_processing_notice(context)
            return {
                "status": 200,
                "body": {"type": "message", "text": "Condensing thread…"},
            }

    def _context_from_activity(self, activity: Activity) -> ThreadContext:
        channel_data = activity.channel_data or {}
        value = activity.value or {}
        message_payload = value.get("messagePayload") or {}
        team = channel_data.get("team") or {}
        channel = channel_data.get("channel") or {}
        tenant = channel_data.get("tenant") or {}

        team_id = team.get("id")
        channel_id = channel.get("id") or (
            activity.conversation.id if channel else None
        )
        conversation_type = (
            "chat" if not channel_id or channel_id.startswith("19:") else "channel"
        )
        chat_id = activity.conversation.id if conversation_type == "chat" else None
        message_id = (
            message_payload.get("id")
            or activity.reply_to_id
            or activity.conversation.id
        )
        requester_id = activity.from_property.id if activity.from_property else None
        tenant_id = (
            activity.conversation.tenant_id if activity.conversation else None
        ) or tenant.get("id")

        metadata = {
            "team_id": team_id or "",
            "channel_id": channel_id or chat_id or "",
            "chat_id": chat_id or "",
            "tenant_id": tenant_id or "",
            "conversation_type": conversation_type,
            "message_id": message_id or "",
        }

        return ThreadContext(
            platform=self.platform,
            workspace_id=tenant_id or team_id or "",
            channel_id=channel_id or chat_id or "",
            thread_id=message_id,
            requester_id=requester_id,
            metadata=metadata,
        )


adapter = TeamsAdapter()
router = adapter.router

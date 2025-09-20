from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from app.config import settings
from app.platforms.base import PlatformAdapter, ThreadContext
from app.platforms.slack.publisher import SlackPublisher
from app.schemas import CondenseResult
from app.workers.tasks import trigger_condense


class SlackAdapter(PlatformAdapter):
    platform = "slack"

    def __init__(self) -> None:
        self.app = AsyncApp(
            token=settings.SLACK_BOT_TOKEN, signing_secret=settings.SLACK_SIGNING_SECRET
        )
        self.handler = AsyncSlackRequestHandler(self.app)
        self.router = APIRouter()
        self.publisher = SlackPublisher(self.app.client)
        self._register_routes()

    def serialize_thread_ref(self, context: ThreadContext) -> Dict[str, Any]:
        team_id = context.metadata.get("team_id") or context.workspace_id
        return {
            "platform": self.platform,
            "team_id": team_id,
            "channel_id": context.channel_id,
            "thread_ts": context.thread_id,
        }

    def context_from_thread_ref(
        self, thread_ref: Dict[str, Any], requester_id: str | None
    ) -> ThreadContext:
        team_id = thread_ref.get("team_id", "")
        channel_id = thread_ref.get("channel_id", "")
        thread_ts = thread_ref.get("thread_ts", "")
        return ThreadContext(
            platform=self.platform,
            workspace_id=team_id,
            channel_id=channel_id,
            thread_id=thread_ts,
            requester_id=requester_id,
            metadata={"team_id": team_id},
        )

    async def acknowledge(self, context: ThreadContext) -> None:  # pragma: no cover
        return None

    async def send_processing_notice(self, context: ThreadContext) -> None:
        await self.publisher.post_ephemeral_processing(
            context.channel_id, context.requester_id or ""
        )

    async def publish_brief(
        self, context: ThreadContext, brief: CondenseResult
    ) -> None:
        await self.publisher.publish_brief(context.channel_id, context.thread_id, brief)

    def _register_routes(self) -> None:
        bolt = self.app

        @bolt.command("/condense")
        async def cmd_condense(ack, body, logger):  # pragma: no cover - Slack callback
            await ack()
            channel_id = body.get("channel_id")
            thread_ts = (
                body.get("thread_ts")
                or body.get("message_ts")
                or body.get("container", {}).get("thread_ts")
            )
            if not thread_ts:
                thread_ts = body.get("message_ts")
            user_id = body.get("user_id")
            team_id = body.get("team_id")
            context = ThreadContext(
                platform=self.platform,
                workspace_id=team_id,
                channel_id=channel_id,
                thread_id=thread_ts,
                requester_id=user_id,
                metadata={"team_id": team_id},
            )
            thread_ref = self.serialize_thread_ref(context)
            trigger_condense(context.platform, thread_ref, context.requester_id)
            await self.send_processing_notice(context)

        @self.router.post("/slack/events")
        async def slack_events(
            request: Request,
        ) -> Response:  # pragma: no cover - Slack
            return await self.handler.handle(request)


adapter = SlackAdapter()
router = adapter.router

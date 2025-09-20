from slack_sdk.web.async_client import AsyncWebClient

from app.schemas import CondenseResult
from app.platforms.slack.blocks import brief_card


class SlackPublisher:
    def __init__(self, client: AsyncWebClient):
        self.client = client

    async def post_ephemeral_processing(self, channel_id: str, user_id: str) -> None:
        if not user_id:
            return
        await self.client.chat_postEphemeral(
            channel=channel_id, user=user_id, text="Processing thread…"
        )

    async def publish_brief(
        self, channel_id: str, thread_ts: str, brief: CondenseResult, pin: bool = False
    ) -> None:
        payload = brief.model_dump(mode="json")
        blocks = brief_card(payload)
        resp = await self.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Condensed brief",
            blocks=blocks,
        )
        if pin:
            try:  # pragma: no cover - network call best effort
                await self.client.pins_add(channel=channel_id, timestamp=resp["ts"])
            except Exception:
                pass

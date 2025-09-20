from typing import Dict, Optional

from app.platforms.graph_client import GraphClient
from app.schemas import CondenseResult
from app.platforms.teams.cards import build_adaptive_card


class TeamsPublisher:
    def __init__(self) -> None:
        self._graph: Optional[GraphClient] = None

    @property
    def graph(self) -> GraphClient:
        if self._graph is None:
            self._graph = GraphClient()
        return self._graph

    async def post_processing(self, metadata: Dict[str, str]) -> None:
        message_id = metadata["message_id"]
        url = self._reply_url(metadata, message_id)
        payload = {
            "body": {"contentType": "html", "content": "Condensing thread…"},
        }
        await self.graph.post(url, payload)

    async def publish_brief(
        self, metadata: Dict[str, str], brief: CondenseResult
    ) -> None:
        message_id = metadata["message_id"]
        url = self._reply_url(metadata, message_id)
        card = build_adaptive_card(brief)
        payload = {
            "body": {"contentType": "html", "content": "Thread Condenser summary"},
            "attachments": [
                {
                    "id": "1",
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }
        await self.graph.post(url, payload)

    def _reply_url(self, metadata: Dict[str, str], message_id: str) -> str:
        if metadata.get("conversation_type") == "chat":
            chat_id = metadata["chat_id"]
            return f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages/{message_id}/replies"
        team_id = metadata["team_id"]
        channel_id = metadata["channel_id"]
        return (
            "https://graph.microsoft.com/v1.0/teams/"
            f"{team_id}/channels/{channel_id}/messages/{message_id}/replies"
        )

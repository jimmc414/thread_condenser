from typing import Dict, Optional

from app.platforms.graph_client import GraphClient
from app.platforms.outlook.actionable import build_actionable_card
from app.schemas import CondenseResult


class OutlookPublisher:
    def __init__(self) -> None:
        self._graph: Optional[GraphClient] = None

    @property
    def graph(self) -> GraphClient:
        if self._graph is None:
            self._graph = GraphClient()
        return self._graph

    async def post_processing(self, metadata: Dict[str, str]) -> None:
        mailbox = metadata["mailbox"]
        message_id = metadata["message_id"]
        url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{message_id}/reply"
        await self.graph.post(url, {"comment": "Condensing thread…"})

    async def publish_brief(
        self, metadata: Dict[str, str], brief: CondenseResult
    ) -> None:
        mailbox = metadata["mailbox"]
        message_id = metadata["message_id"]
        base = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{message_id}"
        draft = await self.graph.post(f"{base}/createReply", {})
        draft_id = draft["id"]
        card = build_actionable_card(brief)
        payload = {
            "body": {
                "contentType": "html",
                "content": "Thread Condenser summary",
            },
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                    "name": "summary.json",
                }
            ],
        }
        await self.graph.patch(
            f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{draft_id}",
            payload,
        )
        await self.graph.post(
            f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{draft_id}/send",
            {},
        )

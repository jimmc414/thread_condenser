class LinearConnector:
    def __init__(self, api_key: str, team_id: str):
        self.api_key = api_key
        self.team_id = team_id

    async def create_or_update(self, item: dict) -> dict:
        return {"url": "https://linear.app/issue/ABC-1"}

class ConfluenceConnector:
    def __init__(self, base_url: str, username: str, token: str):
        self.base_url = base_url
        self.username = username
        self.token = token

    async def create_or_update(self, item: dict) -> dict:
        return {"url": f"{self.base_url}/pages/123"}

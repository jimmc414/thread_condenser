class NotionConnector:
    def __init__(self, api_key: str, database_id: str):
        self.api_key = api_key
        self.database_id = database_id

    async def create_or_update(self, item: dict) -> dict:
        return {"url": "https://www.notion.so/sample"}

class CalendarConnector:
    def __init__(self, provider: str, token: str):
        self.provider = provider
        self.token = token

    async def create_or_update(self, item: dict) -> dict:
        return {"status": "scheduled"}

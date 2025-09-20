class JiraConnector:
    def __init__(self, base_url: str, token: str, project_key: str):
        self.base_url = base_url
        self.token = token
        self.project_key = project_key

    async def create_or_update(self, item: dict) -> dict:
        return {"url": f"{self.base_url}/browse/{self.project_key}-123"}

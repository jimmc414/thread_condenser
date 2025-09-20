from typing import Protocol


class Connector(Protocol):
    async def create_or_update(self, item: dict) -> dict: ...

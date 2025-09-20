from app.platforms.teams.bot import adapter
from app.platforms.registry import register_adapter

register_adapter(adapter)

__all__ = ["adapter"]

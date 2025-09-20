from app.platforms.slack.adapter import adapter
from app.platforms.registry import register_adapter

register_adapter(adapter)

__all__ = ["adapter"]

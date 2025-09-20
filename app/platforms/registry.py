from typing import Dict

from app.platforms.base import PlatformAdapter


REGISTRY: Dict[str, PlatformAdapter] = {}


def register_adapter(adapter: PlatformAdapter) -> None:
    REGISTRY[adapter.platform] = adapter


def get_adapter(platform: str) -> PlatformAdapter:
    try:
        return REGISTRY[platform]
    except KeyError as exc:  # pragma: no cover - simple mapping
        raise ValueError(f"unknown platform {platform}") from exc


from app.platforms import slack  # noqa: E402,F401
from app.platforms import teams  # noqa: E402,F401
from app.platforms import outlook  # noqa: E402,F401

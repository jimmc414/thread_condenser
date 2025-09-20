from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.schemas import CondenseResult


@dataclass
class ThreadContext:
    platform: str
    workspace_id: str
    channel_id: str
    thread_id: str
    requester_id: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def acknowledge(self, context: ThreadContext) -> None: ...

    @abstractmethod
    async def send_processing_notice(self, context: ThreadContext) -> None: ...

    @abstractmethod
    async def publish_brief(
        self, context: ThreadContext, brief: CondenseResult
    ) -> None: ...

    @abstractmethod
    def serialize_thread_ref(self, context: ThreadContext) -> Dict[str, Any]: ...

    @abstractmethod
    def context_from_thread_ref(
        self, thread_ref: Dict[str, Any], requester_id: Optional[str]
    ) -> ThreadContext: ...

import asyncio
import os
import sys
import types
from types import SimpleNamespace


os.environ.setdefault("APP_SECRET", "test-secret")
os.environ.setdefault("POSTGRES_DSN", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "signing-secret")


if "botframework.connector.auth" not in sys.modules:
    botframework_module = types.ModuleType("botframework")
    connector_module = types.ModuleType("botframework.connector")
    auth_module = types.ModuleType("botframework.connector.auth")

    class SimpleCredentialProvider:
        def __init__(self, app_id, app_password):
            self.app_id = app_id
            self.app_password = app_password

    class JwtTokenValidation:
        @staticmethod
        async def authenticate_request(*args, **kwargs):
            return None

    auth_module.SimpleCredentialProvider = SimpleCredentialProvider
    auth_module.JwtTokenValidation = JwtTokenValidation
    connector_module.auth = auth_module
    botframework_module.connector = connector_module

    sys.modules.setdefault("botframework", botframework_module)
    sys.modules.setdefault("botframework.connector", connector_module)
    sys.modules.setdefault("botframework.connector.auth", auth_module)

if "app.platforms.registry" not in sys.modules:
    fake_registry = types.ModuleType("app.platforms.registry")
    fake_registry.REGISTRY = {}

    def _register_adapter(adapter):  # pragma: no cover - test stub
        fake_registry.REGISTRY[adapter.platform] = adapter

    def _get_adapter(platform):  # pragma: no cover - test stub
        return fake_registry.REGISTRY[platform]

    fake_registry.register_adapter = _register_adapter
    fake_registry.get_adapter = _get_adapter
    sys.modules.setdefault("app.platforms.registry", fake_registry)

if "app.workers.tasks" not in sys.modules:
    fake_tasks = types.ModuleType("app.workers.tasks")

    def _fake_trigger_condense(*args, **kwargs):  # pragma: no cover - test stub
        return None

    fake_tasks.trigger_condense = _fake_trigger_condense
    sys.modules.setdefault("app.workers.tasks", fake_tasks)

from app.platforms.teams.bot import TeamsAdapter


class DummyPublisher:
    def __init__(self) -> None:
        self.calls = []

    async def post_processing(self, metadata):
        self.calls.append(("post_processing", metadata.copy()))

    async def publish_brief(self, metadata, brief):
        self.calls.append(("publish_brief", metadata.copy(), brief))


ACTIVITY_MESSAGE_ID = "activity-message-id"
THREAD_MESSAGE_ID = "thread-message-id"


def _build_activity_context(adapter: TeamsAdapter):
    activity = SimpleNamespace(
        channel_data={
            "team": {"id": "team-123"},
            "channel": {"id": "channel-456"},
            "tenant": {"id": "tenant-789"},
        },
        value={"messagePayload": {"id": ACTIVITY_MESSAGE_ID}},
        conversation=SimpleNamespace(id="conversation-xyz", tenant_id="tenant-789"),
        reply_to_id=None,
        from_property=SimpleNamespace(id="user-123"),
    )
    context = adapter._context_from_activity(activity)
    return context, ACTIVITY_MESSAGE_ID


def _build_thread_ref_context(adapter: TeamsAdapter):
    thread_ref = {
        "tenant_id": "tenant-789",
        "team_id": "team-123",
        "channel_id": "channel-456",
        "chat_id": "",
        "conversation_type": "channel",
        "message_id": THREAD_MESSAGE_ID,
    }
    context = adapter.context_from_thread_ref(thread_ref, requester_id="user-123")
    return context, THREAD_MESSAGE_ID


def test_teams_adapter_round_trips_message_id():
    adapter = TeamsAdapter()
    thread_ref = {
        "tenant_id": "tenant-789",
        "team_id": "team-123",
        "channel_id": "channel-456",
        "chat_id": "",
        "conversation_type": "channel",
        "message_id": THREAD_MESSAGE_ID,
    }

    context = adapter.context_from_thread_ref(thread_ref, requester_id="user-123")

    assert context.thread_id == THREAD_MESSAGE_ID
    assert context.metadata["message_id"] == THREAD_MESSAGE_ID

    serialized = adapter.serialize_thread_ref(context)

    assert serialized["message_id"] == THREAD_MESSAGE_ID


def test_send_processing_notice_and_publish_brief_include_message_id():
    adapter = TeamsAdapter()
    adapter.publisher = DummyPublisher()

    for context_factory, expected in (
        (_build_activity_context, ACTIVITY_MESSAGE_ID),
        (_build_thread_ref_context, THREAD_MESSAGE_ID),
    ):
        adapter.publisher.calls.clear()
        context, message_id = context_factory(adapter)

        assert message_id == expected
        assert context.metadata["message_id"] == expected

        asyncio.run(adapter.send_processing_notice(context))

        brief = object()
        asyncio.run(adapter.publish_brief(context, brief))

        assert len(adapter.publisher.calls) == 2
        assert adapter.publisher.calls[-2][0] == "post_processing"
        assert adapter.publisher.calls[-2][1]["message_id"] == expected
        assert adapter.publisher.calls[-1][0] == "publish_brief"
        assert adapter.publisher.calls[-1][1]["message_id"] == expected
        assert adapter.publisher.calls[-1][2] is brief


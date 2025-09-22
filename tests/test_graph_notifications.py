import os
import sys
import types
from importlib import import_module

os.environ.setdefault("APP_SECRET", "test-secret")
os.environ.setdefault("POSTGRES_DSN", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "signing-secret")


def _import_graph_module(monkeypatch, fake_trigger):
    fake_tasks = types.ModuleType("app.workers.tasks")
    fake_tasks.trigger_condense = fake_trigger
    monkeypatch.setitem(sys.modules, "app.workers.tasks", fake_tasks)

    fake_deps = types.ModuleType("app.deps")

    def _fake_get_db():
        yield None

    fake_deps.get_db = _fake_get_db
    monkeypatch.setitem(sys.modules, "app.deps", fake_deps)

    fake_models = types.ModuleType("app.models")

    class _Brief:
        def __init__(self, run_id=None, json_blob=None):
            self.run_id = run_id
            self.json_blob = json_blob or {}

    fake_models.Brief = _Brief
    monkeypatch.setitem(sys.modules, "app.models", fake_models)

    sys.modules.pop("app.api.v1", None)
    module = import_module("app.api.v1")
    return module.GraphNotification, module.graph_notifications


def test_graph_notifications_translates_teams_channel(monkeypatch):
    calls = []

    def fake_trigger(platform, thread_ref, requester_user_id=None, options=None):
        calls.append((platform, thread_ref, requester_user_id, options))
        return "fake-run-id"

    GraphNotification, graph_notifications = _import_graph_module(
        monkeypatch, fake_trigger
    )

    resource = "/teams('team-123')/channels('19%3Aabc')/messages('169:root-msg')"
    payload = GraphNotification(
        value=[
            {
                "resource": resource,
                "resourceData": {
                    "@odata.type": "#Microsoft.Graph.chatMessage",
                    "id": "169:root-msg",
                    "conversationId": "19:conversation@thread.v2",
                    "tenantId": "tenant-xyz",
                    "channelIdentity": {
                        "teamId": "team-123",
                        "channelId": "19:abc",
                    },
                },
            }
        ]
    )

    result = graph_notifications(payload)

    assert result == {"status": "accepted"}
    assert len(calls) == 1
    platform, thread_ref, requester_user_id, options = calls[0]
    assert platform == "msteams"
    assert requester_user_id is None
    assert options is None
    assert thread_ref["resource"] == resource
    assert thread_ref["message_id"] == "169:root-msg"
    assert thread_ref["conversation_id"] == "19:conversation@thread.v2"
    assert thread_ref["tenant_id"] == "tenant-xyz"
    assert thread_ref["team_id"] == "team-123"
    assert thread_ref["channel_id"] == "19:abc"
    assert thread_ref["conversation_type"] == "channel"
    assert "id" not in thread_ref
    assert "conversationId" not in thread_ref


def test_graph_notifications_translates_outlook(monkeypatch):
    calls = []

    def fake_trigger(platform, thread_ref, requester_user_id=None, options=None):
        calls.append((platform, thread_ref, requester_user_id, options))
        return "fake-run-id"

    GraphNotification, graph_notifications = _import_graph_module(
        monkeypatch, fake_trigger
    )

    resource = "/users('user%40example.com')/messages('AAMkAGI2AAA=')"
    payload = GraphNotification(
        value=[
            {
                "resource": resource,
                "resourceData": {
                    "@odata.type": "#Microsoft.Graph.Message",
                    "id": "AAMkAGI2AAA=",
                    "conversationId": "AAQkAGI2AAA=",
                    "tenantId": "contoso-tenant",
                },
            }
        ]
    )

    result = graph_notifications(payload)

    assert result == {"status": "accepted"}
    assert len(calls) == 1
    platform, thread_ref, requester_user_id, options = calls[0]
    assert platform == "outlook"
    assert requester_user_id is None
    assert options is None
    assert thread_ref["resource"] == resource
    assert thread_ref["message_id"] == "AAMkAGI2AAA="
    assert thread_ref["conversation_id"] == "AAQkAGI2AAA="
    assert thread_ref["tenant_id"] == "contoso-tenant"
    assert thread_ref["mailbox"] == "user@example.com"
    assert "id" not in thread_ref
    assert "conversationId" not in thread_ref

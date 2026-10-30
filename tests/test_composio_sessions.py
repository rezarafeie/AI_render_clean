import asyncio
from contextlib import contextmanager
from types import SimpleNamespace as Obj

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from hermes.routers.connected_apps import router
from hermes.security import current_user
from hermes.services import composio_sessions as service


@pytest.fixture
def setup(monkeypatch):
    rows, calls = {}, []
    monkeypatch.setattr(service.settings, "COMPOSIO_INSTANCE_ID", "test-installation")
    monkeypatch.setattr(service.settings, "COMPOSIO_API_KEY", "private-api-key")
    monkeypatch.setattr(service.settings, "COMPOSIO_TOOLKITS", "instagram")
    monkeypatch.setattr(service.settings, "COMPOSIO_CALLBACK_URL", "https://editor.example/hermes/settings")
    monkeypatch.setattr(service.settings, "HERMES_ENCRYPTION_KEY", "stable-test-key")

    async def get(table, key):
        return rows.get(key)
    async def save(table, row):
        rows[row["id"]] = row
    monkeypatch.setattr(service, "get_row", get)
    monkeypatch.setattr(service, "save_row", save)

    class Session:
        session_id = "session-private-reference"
        def toolkits(self, **kwargs):
            calls.append(("toolkits", kwargs))
            return Obj(items=[Obj(slug="instagram", name="Instagram", connection=None)])
        def authorize(self, toolkit, **kwargs):
            calls.append(("authorize", toolkit, kwargs))
            return Obj(redirect_url="https://connect.composio.dev/authorization")
        def search(self, **kwargs):
            calls.append(("search", kwargs))
            return Obj(success=True, session="private-search-session", memory="private-memory",
                tool_schemas={"INSTAGRAM_GET_PROFILE": Obj(tool_slug="INSTAGRAM_GET_PROFILE", toolkit="instagram",
                    description="Read profile", has_full_schema=True,
                    input_schema={"type": "object", "properties": {}})})
    class Sessions:
        def create(self, **kwargs):
            calls.append(("create", kwargs))
            return Session()
        def use(self, ref):
            calls.append(("use", ref))
            return Session()
    @contextmanager
    def sdk():
        yield Obj(sessions=Sessions())
    monkeypatch.setattr(service, "sdk", sdk)
    return rows, calls


def test_persistent_session_reused_and_secrets_not_returned(setup):
    rows, calls = setup
    async def scenario():
        await service.set_enabled("1", True)
        await service.connections("1")
        await service.connections("1")
        return await service.status("1")
    result = asyncio.run(scenario())
    assert len([c for c in calls if c[0] == "create"]) == 1
    policy = next(c[1] for c in calls if c[0] == "create")
    assert policy["sandbox"] == {"enable": False}
    assert policy["proxy_execute"] is False
    assert policy["manage_connections"] is False
    assert policy["toolkits"] == {"enable": ["instagram"]}
    assert policy["tags"] == {"enable": ["readOnlyHint"]}
    assert "session-private-reference" not in str(rows)
    assert "private-api-key" not in str(rows) + str(result)
    assert "session_id" not in result
    assert result["external_actions_enabled"] is False


def test_disabled_user_cannot_use_other_users_session(setup):
    async def scenario():
        await service.set_enabled("1", True)
        await service.session_id("1")
        await service.set_enabled("2", False)          # enabled by default; an explicit disable still blocks
        with pytest.raises(HTTPException) as error:
            await service.connections("2")
        assert error.value.status_code == 409
    asyncio.run(scenario())
    assert service.identity("1") != service.identity("2")


def test_unknown_application_is_never_authorized(setup):
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.connect("1", "arbitrary"))
    assert error.value.status_code == 422
    assert not setup[1]


def test_remote_error_is_sanitized_and_not_retried(setup):
    calls = []
    def fail():
        calls.append(True)
        raise RuntimeError("private-api-key session-secret https://secret")
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.remote(fail))
    assert error.value.detail == {"code": "COMPOSIO_CONNECTION_FAILED"}
    assert len(calls) == 1


def test_callback_does_not_mark_connection_successful(setup):
    async def scenario():
        await service.set_enabled("1", True)
        return await service.connect("1", "instagram")
    assert asyncio.run(scenario())["status"] == "AUTHORIZATION_REQUIRED"


@pytest.mark.parametrize('url,environment,allowed', [
    ('http://127.0.0.1:5187/hermes/settings', 'development', True),
    ('http://localhost:5187/hermes/settings', 'development', True),
    ('http://127.0.0.1:5187/hermes/settings', 'production', False),
    ('http://192.168.0.1/hermes/settings', 'development', False),
    ('http://localhost.attacker.test/hermes/settings', 'development', False),
    ('https://user:secret@example.com/hermes/settings', 'production', False),
    ('https://editor.example/hermes/settings', 'production', True),
])
def test_callback_security(setup, monkeypatch, url, environment, allowed):
    monkeypatch.setattr(service.settings, 'COMPOSIO_CALLBACK_URL', url)
    monkeypatch.setattr(service.settings, 'APP_ENV', environment)
    async def scenario():
        await service.set_enabled('1', True)
        if allowed:
            assert (await service.connect('1', 'instagram'))['status'] == 'AUTHORIZATION_REQUIRED'
        else:
            with pytest.raises(HTTPException) as error:
                await service.connect('1', 'instagram')
            assert error.value.status_code == 503
            assert not setup[1]
    asyncio.run(scenario())


def test_authenticated_routes_reject_client_identity_and_arbitrary_actions(setup):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/hermes/composio").status_code == 401
        app.dependency_overrides[current_user] = lambda: Obj(id=1)
        assert client.put("/api/hermes/composio", json={"enabled": True, "user_id": "2"}).status_code == 422
        assert client.post("/api/hermes/composio/execute", json={"tool": "DELETE"}).status_code == 404
        assert client.get("/api/hermes/composio").json()["external_actions_enabled"] is False


def test_changed_namespace_fails_closed(setup, monkeypatch):
    async def scenario():
        await service.set_enabled("1", True)
        await service.session_id("1")
        monkeypatch.setattr(service.settings, "COMPOSIO_INSTANCE_ID", "another-installation")
        with pytest.raises(HTTPException) as error:
            await service.session_id("1")
        assert error.value.status_code == 409
    asyncio.run(scenario())


def test_changed_toolkit_policy_builds_a_new_session_under_the_new_policy(setup, monkeypatch):
    _, calls = setup
    async def scenario():
        await service.set_enabled("1", True)
        await service.session_id("1")
        monkeypatch.setattr(service.settings, "COMPOSIO_TOOLKITS", "instagram,googledrive")
        await service.session_id("1")
        await service.session_id("1")          # now stable again
    asyncio.run(scenario())
    creates = [c[1] for c in calls if c[0] == "create"]
    assert len(creates) == 2
    assert creates[1]["toolkits"] == {"enable": ["googledrive", "instagram"]}
    assert creates[1]["tags"] == {"enable": ["readOnlyHint"]} and creates[1]["manage_connections"] is False


def test_context_discovery_is_scoped_bounded_and_does_not_forward_raw_state(setup):
    async def scenario():
        await service.set_enabled("1", True)
        return await service.discover("1", "instagram", "Read my profile")
    result = asyncio.run(scenario())
    assert result["tools"][0]["name"] == "INSTAGRAM_GET_PROFILE"
    assert result["tools"][0]["executable"] is False
    assert "private" not in str(result)
    assert ("search", {"query": "instagram: Read my profile"}) in setup[1]


def test_discovery_filters_other_apps_and_invalid_or_oversized_schemas():
    def item(slug, toolkit="instagram", schema=None):
        return Obj(tool_slug=slug, toolkit=toolkit, description="Read", has_full_schema=True,
                   input_schema=schema if schema is not None else {"type": "object"})
    tools = {"GMAIL_READ": item("GMAIL_READ", "gmail"),
             "INSTAGRAM_BAD_SCHEMA": item("INSTAGRAM_BAD_SCHEMA", schema={"type": "invented"}),
             "INSTAGRAM_LARGE_SCHEMA": item("INSTAGRAM_LARGE_SCHEMA", schema={"description": "x" * 6001})}
    tools.update({f"INSTAGRAM_GET_{n}": item(f"INSTAGRAM_GET_{n}") for n in range(20)})
    result = service.public_discovery(Obj(success=True, tool_schemas=tools), "instagram")
    assert len(result["tools"]) == 6
    assert all(tool["application"] == "instagram" for tool in result["tools"])
    assert not result["tools"][0]["schema_available"]
    assert not result["tools"][1]["schema_available"]


def test_discovery_failure_does_not_masquerade_as_no_matching_tools():
    with pytest.raises(HTTPException) as error:
        service.public_discovery(Obj(success=False, tool_schemas={}), "instagram")
    assert error.value.detail["code"] == "COMPOSIO_DISCOVERY_FAILED"


def test_discovery_route_does_not_accept_caller_supplied_session_or_user(setup):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        app.dependency_overrides[current_user] = lambda: Obj(id=1)
        body = {"application": "instagram", "query": "Read profile", "session_id": "another-user-session"}
        assert client.post("/api/hermes/composio/discover", json=body).status_code == 422
    assert not setup[1]


def test_rate_limit_is_explicit_and_not_retried():
    calls = []
    class RateLimited(Exception):
        status_code = 429
    def fail():
        calls.append(True)
        raise RateLimited("private-provider-response")
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.remote(fail))
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "30"
    assert calls == [True]


def test_composio_instagram_is_listed_as_a_read_only_account(setup, monkeypatch):
    from hermes.services import composio_account as account
    from hermes.config import settings as config
    account.forget("1")
    monkeypatch.setattr(config, "COMPOSIO_READ_TOOLS", "INSTAGRAM_GET_USER_INFO")

    async def fake_status(user_id):
        return {"configured": True, "enabled": True, "applications": ["instagram"]}

    async def fake_connections(user_id):
        return {"applications": [{"application": "instagram", "name": "Instagram", "connected": True, "status": "ACTIVE"}]}

    async def fake_execute(user_id, toolkit, slug, arguments, max_chars=40_000):
        return {"data": {"data": {"username": "someone", "followers_count": 1234, "id": "17841"}}}
    monkeypatch.setattr(account.sessions, "status", fake_status)
    monkeypatch.setattr(account.sessions, "connections", fake_connections)
    monkeypatch.setattr(account.read, "execute", fake_execute)
    row = asyncio.run(account.account("1"))
    assert row["id"] == account.VIRTUAL_ID and row["username"] == "someone" and row["followers"] == 1234 and row["source"] == "composio"
    account.forget("1")


def test_a_relay_url_is_used_only_when_it_is_https(monkeypatch):
    captured = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)
    import composio
    monkeypatch.setattr(composio, "Composio", Fake)
    monkeypatch.setattr(service.settings, "COMPOSIO_API_KEY", "k")
    monkeypatch.setattr(service.settings, "COMPOSIO_BASE_URL", "https://relay.example/api/composio/")
    monkeypatch.setattr(service.settings, "COMPOSIO_RELAY_SECRET", "s")
    with service.sdk():
        pass
    assert captured["base_url"] == "https://relay.example/api/composio" and captured["http_client"].headers["x-relay-secret"] == "s"
    monkeypatch.setattr(service.settings, "COMPOSIO_BASE_URL", "http://relay.example")
    with pytest.raises(HTTPException) as bad:
        with service.sdk():
            pass
    assert bad.value.status_code == 503

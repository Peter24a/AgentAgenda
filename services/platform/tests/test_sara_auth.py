"""Exercise SARA's browser and durable credential boundaries with no live Identity calls."""
import asyncio
import base64
import hashlib
import json
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.main import create_app
from app.registry import Registry, RegistryError
from app.security import digest


ORIGIN = "https://agenda-api.pedroibarra.dev"
ADMIN_ID = "7bc25534-2b60-4bcd-a80b-393c82ddd16e"
OTHER_ID = "f327584c-5632-4556-af65-c2a8872d073a"
SESSION_ID = "0473dc2d-fd19-439c-ae48-cdc8b6a1a003"
AUTH_PATH = "/control/v1/auth"


@pytest.fixture
def sara_platform(tmp_path):
    key = Fernet.generate_key()
    registry = Registry(str(tmp_path / "registry.sqlite3"), key)
    cfg = Settings(
        registry_path=registry.path,
        public_base_url=ORIGIN,
        web_root=str(tmp_path / "web"),
        identity_enabled=True,
        identity_api_url="https://identity.example.test",
        identity_portal_url="https://auth.ici-labs.com",
        identity_admin_ids=ADMIN_ID,
        admin_password_hash="legacy-password-must-never-be-checked",
    )
    state = {
        "requests": [], "generation": 0, "token_calls": 0, "refresh_calls": 0,
        "introspect_calls": 0, "logout_calls": 0, "introspect_status": 200,
        "token_status": 200, "refresh_status": 200, "logout_status": 200,
        "principal": {"id": ADMIN_ID, "name": "Administración SARA", "is_active": True},
        "device_id": None, "grant_override": {}, "on_token": None,
    }

    def grant():
        generation = state["generation"]
        return {
            "access_token": f"access-secret-{generation}-" + "a" * 40,
            "refresh_token": f"refresh-secret-{generation}-" + "r" * 40,
            "token_type": "bearer", "client_id": cfg.identity_client_id,
            "session_id": SESSION_ID, "device_id": state["device_id"],
            "expires_in": 3600, "refresh_expires_in": 86400,
            **state["grant_override"],
        }

    def identity(request):
        state["requests"].append(request)
        assert request.url.host == "identity.example.test"
        if request.url.path == "/oauth/token":
            state["token_calls"] += 1
            state["device_id"] = request.headers["x-device-id"]
            if state["on_token"]:
                state["on_token"](request)
            return httpx.Response(state["token_status"], json=grant())
        if request.url.path == "/auth/introspect":
            state["introspect_calls"] += 1
            return httpx.Response(state["introspect_status"], json=state["principal"])
        if request.url.path == "/auth/refresh":
            state["refresh_calls"] += 1
            assert json.loads(request.content)["refresh_token"] == grant()["refresh_token"]
            time.sleep(0.03)  # Overlap real callers while the refresh lock is held.
            state["generation"] += 1
            return httpx.Response(state["refresh_status"], json=grant())
        if request.url.path == "/auth/logout/refresh":
            state["logout_calls"] += 1
            assert "refresh_token" in json.loads(request.content)
            return httpx.Response(state["logout_status"], json={"ok": True})
        raise AssertionError(f"Unexpected Identity endpoint: {request.url.path}")

    transport = httpx.MockTransport(identity)
    app = create_app(cfg, registry, identity_transport=transport)
    yield SimpleNamespace(app=app, registry=registry, cfg=cfg, key=key, state=state, transport=transport, grant=grant)
    app.state.sara.client.close()


def browser(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)


async def begin(client):
    response = await client.get(AUTH_PATH + "/sara/start")
    assert response.status_code == 302
    query = {name: values[0] for name, values in parse_qs(urlsplit(response.headers["location"]).query).items()}
    return response, query, client.cookies.get("aa_sara_flow")


async def login(client):
    _, query, _ = await begin(client)
    response = await client.get(AUTH_PATH + "/sara/callback", params={"state": query["state"], "code": "synthetic-authorization-code"})
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    return client.cookies.get("aa_admin")


def expire_access(platform, token):
    with platform.registry.connect() as db:
        row = db.execute("SELECT value FROM sessions WHERE token_hash=?", (digest(token),)).fetchone()
        value = platform.registry.open(row["value"])
        value["access_expires_at"] = time.time() - 1
        db.execute("UPDATE sessions SET value=? WHERE token_hash=?", (platform.registry.seal(value), digest(token)))


async def test_authorization_pkce_is_bound_to_browser_and_state_and_not_exposed(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        response, query, flow_cookie = await begin(client)
        assert urlsplit(response.headers["location"]).netloc == "auth.ici-labs.com"
        assert query["response_type"] == "code" and query["client_id"] == p.cfg.identity_client_id
        assert query["redirect_uri"] == ORIGIN + AUTH_PATH + "/sara/callback"
        assert query["code_challenge_method"] == "S256"
        assert "code_verifier" not in query and "access_token" not in query
        assert "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
        with p.registry.connect() as db:
            row = db.execute("SELECT * FROM sara_flows").fetchone()
            payload = p.registry.open(row["payload"])
            assert row["state_hash"] == digest(query["state"])
            assert row["browser_hash"] == digest(flow_cookie)
            assert payload["verifier"] not in row["payload"]
        expected = base64.urlsafe_b64encode(hashlib.sha256(payload["verifier"].encode()).digest()).rstrip(b"=").decode()
        assert query["code_challenge"] == expected
        async with browser(p.app) as stranger:
            rejected = await stranger.get(AUTH_PATH + "/sara/callback", params={"state": query["state"], "code": "code"})
            assert rejected.headers["location"] == "/admin?auth_error=invalid_attempt"
        assert p.state["token_calls"] == 0
        callback = await client.get(AUTH_PATH + "/sara/callback", params={"state": query["state"], "code": "code"})
        assert callback.headers["location"] == "/admin"
        token_request = next(request for request in p.state["requests"] if request.url.path == "/oauth/token")
        posted = parse_qs(token_request.content.decode())
        assert posted["code_verifier"] == [payload["verifier"]]
        assert posted["redirect_uri"] == [query["redirect_uri"]]
        assert posted["client_id"] == [p.cfg.identity_client_id]
        assert token_request.headers["x-device-id"] == payload["device_id"]
        assert "SameSite=strict" in callback.headers["set-cookie"]


async def test_ambiguous_exchange_is_durably_consumed_before_outbound_request(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        _, query, cookie = await begin(client)

        def lose_response(request):
            with p.registry.connect() as db:
                flow = db.execute("SELECT * FROM sara_flows WHERE state_hash=?", (digest(query["state"]),)).fetchone()
                assert flow["status"] == "exchanging" and flow["payload"] is None
            raise httpx.ReadError("Synthetic unknown token outcome", request=request)

        p.state["on_token"] = lose_response
        params = {"state": query["state"], "code": "one-use-code"}
        first = await client.get(AUTH_PATH + "/sara/callback", params=params)
        assert first.headers["location"] == "/admin?auth_error=unavailable"
        client.cookies.set("aa_sara_flow", cookie, domain=urlsplit(ORIGIN).hostname, path=AUTH_PATH + "/sara")
        replay = await client.get(AUTH_PATH + "/sara/callback", params=params)
        assert replay.headers["location"] == "/admin?auth_error=invalid_attempt"
        assert p.state["token_calls"] == 1
        with p.registry.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


@pytest.mark.parametrize("change", [{"id": OTHER_ID, "email": "same-admin@example.test"}, {"is_active": False}])
async def test_only_explicit_active_uuid_grants_administration(sara_platform, change):
    p = sara_platform
    p.state["principal"].update({"email": "same-admin@example.test", **change})
    async with browser(p.app) as client:
        _, query, _ = await begin(client)
        result = await client.get(AUTH_PATH + "/sara/callback", params={"state": query["state"], "code": "code"})
        assert result.headers["location"] == "/admin?auth_error=access_denied"
        assert not client.cookies.get("aa_admin")
        assert p.state["logout_calls"] == 1
        assert (await client.get(AUTH_PATH + "/me")).status_code == 401


async def test_credentials_are_encrypted_and_audience_is_fixed_for_each_check(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
        me = await client.get(AUTH_PATH + "/me", headers={"X-Resource-Audience": "attacker-controlled"})
        assert me.status_code == 200 and set(me.json()) == {"username", "csrf_token"}
        assert me.json()["username"] == p.state["principal"]["name"]
        assert (await client.get("/control/v1/spaces")).status_code == 200
        grant = p.grant()
        for secret in (grant["access_token"], grant["refresh_token"], SESSION_ID, ADMIN_ID):
            assert secret not in me.text
        for request in p.state["requests"]:
            if request.url.path == "/auth/introspect":
                assert request.headers["x-resource-audience"] == "agentagenda-admin"
                assert request.headers["authorization"] == "Bearer " + grant["access_token"]
        with p.registry.connect() as db:
            row = db.execute("SELECT * FROM sessions").fetchone()
            assert row["token_hash"] == digest(token) and token != row["token_hash"]
            opened = p.registry.open(row["value"])
            assert opened["provider"] == "sara" and opened["refresh_token"] == grant["refresh_token"]
            assert grant["access_token"] not in row["value"] and grant["refresh_token"] not in row["value"]
        for path in (p.registry.path, p.registry.path + "-wal"):
            if Path(path).exists():
                persisted = Path(path).read_bytes()
                assert grant["access_token"].encode() not in persisted
                assert grant["refresh_token"].encode() not in persisted


async def test_sara_mode_rejects_local_password_and_legacy_admin_sessions(sara_platform):
    p = sara_platform
    legacy, _ = p.registry.create_session("admin", {"username": "legacy"}, 3600)
    async with browser(p.app) as client:
        cfg = (await client.get(AUTH_PATH + "/config")).json()
        assert cfg == {"provider": "sara", "login_url": AUTH_PATH + "/sara/start", "account_url": "https://auth.ici-labs.com/account"}
        result = await client.post(AUTH_PATH + "/login", json={"username": "admin", "password": "old-password"}, headers={"Origin": ORIGIN})
        assert result.status_code == 404
        client.cookies.set("aa_admin", legacy, domain=urlsplit(ORIGIN).hostname, path="/control")
        assert (await client.get(AUTH_PATH + "/me")).status_code == 401
        assert (await client.get("/control/v1/spaces")).status_code == 401
    assert p.state["introspect_calls"] == 0


@pytest.mark.parametrize("status,expected", [(401, 401), (403, 401), (503, 503)])
async def test_live_identity_revocation_and_outage_fail_closed(sara_platform, status, expected):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
        p.state["introspect_status"] = status
        result = await client.get(AUTH_PATH + "/me")
        assert result.status_code == expected
        if expected == 401:
            with pytest.raises(RegistryError):
                p.registry.get_session(token, "admin")
        else:
            p.state["introspect_status"] = 200
            assert (await client.get(AUTH_PATH + "/me")).status_code == 200


async def test_parallel_expired_requests_rotate_refresh_once_and_persist_new_token(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
        expire_access(p, token)
        replies = await asyncio.gather(*(client.get(AUTH_PATH + "/me") for _ in range(6)))
        assert all(reply.status_code == 200 for reply in replies)
        assert p.state["refresh_calls"] == 1 and p.state["generation"] == 1
        saved = p.registry.get_session(token, "admin")["value"]
        assert saved["refresh_token"] == p.grant()["refresh_token"]
        assert saved["identity_status"] == "active"


async def test_ambiguous_refresh_is_not_replayed_after_restart(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
        expire_access(p, token)
        p.state["refresh_status"] = 503
        assert (await client.get(AUTH_PATH + "/me")).status_code == 503
    reopened = Registry(p.registry.path, p.key)
    restarted = create_app(p.cfg, reopened, identity_transport=p.transport)
    async with browser(restarted) as client:
        client.cookies.set("aa_admin", token, domain=urlsplit(ORIGIN).hostname, path="/control")
        assert (await client.get(AUTH_PATH + "/me")).status_code == 401
        assert p.state["refresh_calls"] == 1
    restarted.state.sara.client.close()


async def test_logout_during_identity_outage_revokes_local_session_without_introspection(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
        csrf = (await client.get(AUTH_PATH + "/me")).json()["csrf_token"]
        checks = p.state["introspect_calls"]
        p.state.update(introspect_status=503, logout_status=503)
        response = await client.post(AUTH_PATH + "/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert response.json() == {"ok": True, "identity_revoked": False}
        assert p.state["introspect_calls"] == checks
        assert not client.cookies.get("aa_admin")
        with pytest.raises(RegistryError):
            p.registry.get_session(token, "admin")
        assert (await client.get(AUTH_PATH + "/me")).status_code == 401


async def test_persisted_sara_session_survives_restart_without_local_password(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        token = await login(client)
    cfg = p.cfg.model_copy(update={"admin_password_hash": "", "admin_password_file": ""})
    restarted = create_app(cfg, Registry(p.registry.path, p.key), identity_transport=p.transport)
    async with browser(restarted) as client:
        client.cookies.set("aa_admin", token, domain=urlsplit(ORIGIN).hostname, path="/control")
        response = await client.get(AUTH_PATH + "/me")
        assert response.status_code == 200 and response.json()["username"] == p.state["principal"]["name"]
    restarted.state.sara.client.close()


@pytest.mark.parametrize("changes", [
    {"identity_admin_ids": ""}, {"identity_admin_ids": "admin@example.test"},
    {"identity_api_url": ""}, {"identity_api_url": "http://identity.example.test"},
    {"identity_api_url": "https://identity.example.test/path"},
    {"identity_portal_url": "https://auth.ici-labs.com?client=other"},
    {"identity_client_id": ""}, {"identity_audience": ""},
])
def test_invalid_sara_configuration_cannot_fall_back_to_local_login(sara_platform, changes):
    p = sara_platform
    with pytest.raises(ValueError):
        create_app(p.cfg.model_copy(update=changes), p.registry, identity_transport=p.transport)


@pytest.mark.parametrize("bad_grant", [
    {"client_id": "another-client"}, {"session_id": "not-a-uuid"},
    {"refresh_token": "short"}, {"token_type": "Bearer"},
])
async def test_malformed_or_wrong_client_grant_cannot_create_session(sara_platform, bad_grant):
    p = sara_platform
    p.state["grant_override"] = bad_grant
    async with browser(p.app) as client:
        _, query, _ = await begin(client)
        response = await client.get(AUTH_PATH + "/sara/callback", params={"state": query["state"], "code": "code"})
        assert response.headers["location"] == "/admin?auth_error=unavailable"
        assert not client.cookies.get("aa_admin")
    with p.registry.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


async def test_cross_site_start_and_duplicate_callback_are_rejected(sara_platform):
    p = sara_platform
    async with browser(p.app) as client:
        assert (await client.get(AUTH_PATH + '/sara/start', headers={'Sec-Fetch-Site': 'cross-site'})).status_code == 403
        assert (await client.get(AUTH_PATH + '/sara/start', headers={'Origin': 'https://other.example'})).status_code == 403
        _, query, _ = await begin(client)
        duplicate = await client.get(AUTH_PATH + '/sara/callback', params=[('state', query['state']), ('state', query['state']), ('code', 'code')])
        assert duplicate.headers['location'] == '/admin?auth_error=invalid_attempt'
        assert p.state['token_calls'] == 0

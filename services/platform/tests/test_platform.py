import json
import asyncio
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.main import create_app
from app.registry import Registry
from app.security import password_hash

ORIGIN = "https://agenda-api.pedroibarra.dev"


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, payload):
        self.payload = payload

    async def __aiter__(self):
        yield self.payload


@pytest.fixture
def platform(tmp_path):
    key = Fernet.generate_key()
    registry = Registry(str(tmp_path / "registry.sqlite3"), key)
    personal = registry.create_space("Personal", "Pedro")
    walter = registry.create_space("Walter", "Walter Mata")
    for space, port in ((personal, 8001), (walter, 8101)):
        registry.configure_space(space["id"], f"http://backend-{port}", "default_user", f"secret-{port}-" + "z" * 40, legacy=port == 8001)
        registry.set_space_state(space["id"], "ready")
    state = {"enroll_calls": [], "requests": [], "fail_after_enroll": False, "receipts": {}}

    async def backend(request):
        state["requests"].append(request)
        host = request.url.host
        bearer = request.headers.get("authorization")
        if request.url.path == "/internal/enroll":
            body = json.loads(await request.aread())
            expected_secret = "secret-" + host.removeprefix("backend-") + "-" + "z" * 40
            assert request.headers["x-enrollment-key"] == expected_secret
            state["enroll_calls"].append(body)
            result = state["receipts"].setdefault(body["operation_id"], {"device_id": "new-device-" + host, "access_token": "access-" + host, "refresh_token": "refresh-" + host, "expires_in": 3600, "token_type": "bearer", "scopes": ["agenda:read", "agenda:write"]})
            if state["fail_after_enroll"]:
                state["fail_after_enroll"] = False
                raise httpx.ReadError("Synthetic lost enrollment response", request=request)
            return httpx.Response(200, json=result)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "private": "do not expose"})
        if request.url.path == "/v1/auth/me":
            if bearer != "Bearer access-" + host:
                return httpx.Response(401, json={"detail": "bad token"})
            return httpx.Response(200, json={"user_id": "default_user", "device_id": "new-device-" + host, "token_id": "token", "scopes": ["agenda:read"]})
        if request.url.path == "/v1/auth/refresh":
            body = json.loads(await request.aread())
            if body["refresh_token"] != "refresh-" + host:
                return httpx.Response(401, json={"detail": "bad refresh"})
            return httpx.Response(200, json={"access_token": "access-" + host, "refresh_token": "refresh-" + host, "expires_in": 3600, "scopes": []})
        if request.url.path == "/v1/devices":
            return httpx.Response(200, json={"devices": [{"id": "new-device-" + host, "device_name": "Test"}]})
        if request.url.path == "/v1/chat/stream":
            return httpx.Response(200, headers={"content-type": "text/event-stream", "x-enrollment-key": "hidden"}, stream=ByteStream(b"event: delta\ndata: test\n\n"))
        if request.url.path == "/v1/documents/file":
            return httpx.Response(206, headers={"content-type": "application/pdf", "content-disposition": 'attachment; filename="test.pdf"', "content-range": "bytes 0-3/4", "set-cookie": "backend-secret=bad"}, stream=ByteStream(b"PDF!"))
        if request.url.path == "/v1/redirect":
            return httpx.Response(302, headers={"Location": "https://walteragenda.pedroibarra.dev/private"})
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=ByteStream(json.dumps({"host": host}).encode()))

    (tmp_path / "key").write_bytes(key)
    cfg = Settings(registry_path=registry.path, key_file=str(tmp_path / "key"), public_base_url=ORIGIN, admin_username="pedro", admin_password_hash=password_hash("test-admin-password"), web_root=str(tmp_path / "web"))
    app = create_app(cfg, registry, httpx.MockTransport(backend))
    return app, registry, personal, walter, state


async def login(client):
    response = await client.post("/control/v1/auth/login", headers={"Origin": ORIGIN}, json={"username": "pedro", "password": "test-admin-password"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"], "Origin": ORIGIN}


async def activate(client, registry, space, platform="android", code=None, request_id=None):
    code = code or registry.create_invitation(space["id"], "enroll", 60)["code"]
    body = {"code": code, "device_name": "Test device", "platform": platform, "request_id": request_id or str(uuid.uuid4())}
    response = await client.post("/platform/v1/activate", json=body, headers={"Origin": ORIGIN} if platform == "web" else {})
    return response, body


async def test_native_activation_is_private_durable_and_idempotent(platform):
    app, registry, personal, _, state = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        first, body = await activate(client, registry, personal)
        assert first.status_code == 200
        second = await client.post("/platform/v1/activate", json=body)
        assert second.json() == first.json()
        assert len(state["enroll_calls"]) == 1
        assert first.json()["base_url"] == ORIGIN + "/s/" + personal["id"]
        changed = await client.post("/platform/v1/activate", json={**body, "request_id": str(uuid.uuid4())})
        assert changed.status_code == 409
        changed_device = await client.post("/platform/v1/activate", json={**body, "device_name": "Other"})
        assert changed_device.status_code == 409
        with registry.connect() as db:
            assert "access-backend" not in db.execute("SELECT result FROM invitations").fetchone()[0]
            assert "secret-8001" not in db.execute("SELECT enrollment_key FROM spaces WHERE id=?", (personal["id"],)).fetchone()[0]


async def test_lost_enrollment_response_recovers_same_backend_operation(platform):
    app, registry, personal, _, state = platform
    state["fail_after_enroll"] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        failed, body = await activate(client, registry, personal)
        assert failed.status_code == 503
        retry = await client.post("/platform/v1/activate", json=body)
        assert retry.status_code == 200
        assert len(state["enroll_calls"]) == 2
        assert state["enroll_calls"][0]["operation_id"] == state["enroll_calls"][1]["operation_id"]
        assert len(state["receipts"]) == 1


async def test_unknown_space_and_foreign_bearer_never_reach_personal_content(platform):
    app, registry, personal, walter, state = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer access-backend-8001"}
        unknown = await client.get("/s/" + str(uuid.uuid4()) + "/v1/agenda", headers=headers)
        assert unknown.status_code == 404
        assert not state["requests"]
        foreign = await client.get("/s/" + walter["id"] + "/v1/agenda", headers=headers)
        assert foreign.status_code == 401
        assert [r.url.path for r in state["requests"]] == ["/v1/auth/me"]
        state["requests"].clear()
        internal = await client.post("/s/" + personal["id"] + "/internal/enroll", headers=headers, json={})
        assert internal.status_code == 404
        assert not state["requests"]


async def test_owner_cookie_cannot_administer_or_access_other_space(platform):
    app, registry, personal, walter, _ = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        activation, _body = await activate(client, registry, personal, "web")
        assert activation.status_code == 200
        assert "access_token" not in activation.json()
        assert "refresh_token" not in activation.json()
        cookie = activation.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        session = await client.get("/platform/v1/session")
        assert session.status_code == 200
        assert session.json()["space_id"] == personal["id"]
        assert (await client.get("/control/v1/spaces")).status_code == 401
        assert (await client.get("/s/" + walter["id"] + "/v1/agenda")).status_code == 403
        assert (await client.post("/s/" + personal["id"] + "/v1/agenda", json={})).status_code == 403
        mutation = await client.post("/s/" + personal["id"] + "/v1/agenda", json={}, headers={"X-CSRF-Token": session.json()["csrf_token"], "Origin": ORIGIN})
        assert mutation.status_code == 200


async def test_admin_cannot_view_content_and_requires_csrf(platform):
    app, registry, personal, _, state = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        headers = await login(client)
        listing = await client.get("/control/v1/spaces")
        assert listing.status_code == 200
        assert "enrollment_key" not in listing.text and "backend_url" not in listing.text
        assert "user_id" not in listing.text
        assert (await client.get("/s/" + personal["id"] + "/v1/agenda")).status_code == 401
        assert not state["requests"]
        endpoint = "/control/v1/spaces/" + personal["id"] + "/activation"
        assert (await client.post(endpoint, json={"purpose": "reconnect"})).status_code == 403
        assert (await client.post(endpoint, json={}, headers={**headers, "Origin": "https://evil.example"})).status_code == 403
        valid = await client.post(endpoint, json={"purpose": "reconnect"}, headers=headers)
        assert valid.status_code == 200 and valid.json()["code"]


async def test_suspension_also_blocks_legacy_and_preserves_session_for_resume(platform):
    app, registry, personal, _, state = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await activate(client, registry, personal, "web"))[0].status_code == 200
        registry.set_space_state(personal["id"], "suspended")
        state["requests"].clear()
        for path in ("/v1/agenda", "/s/" + personal["id"] + "/v1/agenda", "/s/" + personal["id"] + "/health"):
            assert (await client.get(path, headers={"Authorization": "Bearer access-backend-8001"})).status_code == 423
        assert (await client.get("/platform/v1/session")).status_code == 423
        assert not state["requests"]
        registry.set_space_state(personal["id"], "ready")
        assert (await client.get("/platform/v1/session")).status_code == 200


async def test_sse_and_download_stream_and_secret_headers_are_stripped(platform):
    app, _, personal, _, state = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        root = "/s/" + personal["id"]
        headers = {"Authorization": "Bearer access-backend-8001", "X-Enrollment-Key": "malicious", "X-App-Key": "malicious", "Cookie": "aa_admin=malicious", "Range": "bytes=0-3"}
        sse = await client.get(root + "/v1/chat/stream", headers=headers)
        assert sse.status_code == 200
        assert sse.content == b"event: delta\ndata: test\n\n"
        assert sse.headers["x-accel-buffering"] == "no"
        assert "x-enrollment-key" not in sse.headers
        download = await client.get(root + "/v1/documents/file", headers=headers)
        assert download.status_code == 206 and download.content == b"PDF!"
        assert download.headers["content-range"] == "bytes 0-3/4"
        assert "set-cookie" not in download.headers
        outgoing = state["requests"][-1]
        assert outgoing.headers["range"] == "bytes=0-3"
        assert all(h not in outgoing.headers for h in ("x-enrollment-key", "x-app-key", "cookie"))
        assert (await client.get(root + "/v1/redirect", headers=headers)).status_code == 502


async def test_expired_codes_and_foreign_origin_web_activation_are_rejected(platform):
    app, registry, personal, _, state = platform
    code = registry.create_invitation(personal["id"], "enroll", -1)["code"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        response, body = await activate(client, registry, personal, code=code)
        assert response.status_code == 400
        foreign = await client.post("/platform/v1/activate", json={**body, "platform": "web"}, headers={"Origin": "https://evil.example"})
        assert foreign.status_code == 403
        absent = await client.post("/platform/v1/activate", json={**body, "platform": "web"})
        assert absent.status_code == 403
        assert not state["requests"]


async def test_refresh_accepts_expired_access_but_is_bound_to_backend(platform):
    app, _, personal, walter, _ = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer expired"}
        good = await client.post("/s/" + personal["id"] + "/v1/auth/refresh", headers=headers, json={"refresh_token": "refresh-backend-8001"})
        assert good.status_code == 200
        assert good.json()["access_token"] == "access-backend-8001"
        bad = await client.post("/s/" + walter["id"] + "/v1/auth/refresh", json={"refresh_token": "refresh-backend-8001"})
        assert bad.status_code == 401


async def wait_operation(registry, operation_id):
    for _ in range(100):
        operation = registry.get_operation(operation_id)
        if operation["state"] not in {"queued", "running"}:
            return operation
        await asyncio.sleep(0.02)
    raise AssertionError("Synthetic provisioning did not complete")


async def test_fixed_helper_lifecycle_and_recovery_of_queued_create(platform, tmp_path):
    original_app, registry, personal, _, _ = platform
    helper = tmp_path / "provision"
    helper.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n" + """import os, sys
from pathlib import Path
from app.registry import Registry
registry = Registry(os.environ['PLATFORM_REGISTRY_PATH'], Path(os.environ['PLATFORM_KEY_FILE']).read_bytes())
action, space_id = sys.argv[1:]
assert action in {'create','suspend','resume','close','reopen'}
if action == 'create':
    registry.configure_space(space_id, 'http://synthetic-new-backend', 'new-owner', 'new-secret-' + 'x' * 40)
""")
    helper.chmod(0o700)
    cfg = original_app.state.settings.model_copy(update={"provisioner": str(helper)})
    app = create_app(cfg, registry, original_app.state.client._transport)
    # An interrupted process leaves its atomic work item; restart adopts it rather than duplicating resources.
    queued_space, queued_operation = registry.create_managed_space("Before restart", "Synthetic")
    async with app.router.lifespan_context(app):
        recovered = await wait_operation(registry, queued_operation["id"])
        assert recovered["state"] == "succeeded"
        assert registry.get_space(queued_space["id"])["state"] == "ready"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            headers = await login(client)
            created = await client.post("/control/v1/spaces", json={"name": "New synthetic", "owner_name": "Owner"}, headers=headers)
            assert created.status_code == 202
            assert created.json()["state"] == "provisioning"
            assert (await wait_operation(registry, created.json()["operation_id"]))["state"] == "succeeded"
            assert registry.get_space(created.json()["id"])["state"] == "ready"
            suspended = await client.post("/control/v1/spaces/" + personal["id"] + "/suspend", headers=headers)
            assert suspended.status_code == 202
            assert registry.get_space(personal["id"])["state"] == "suspended"
            assert (await client.get("/v1/agenda", headers={"Authorization": "Bearer access-backend-8001"})).status_code == 423
            assert (await wait_operation(registry, suspended.json()["operation_id"]))["state"] == "succeeded"
            resumed = await client.post("/control/v1/spaces/" + personal["id"] + "/resume", headers=headers)
            assert resumed.status_code == 202
            assert (await wait_operation(registry, resumed.json()["operation_id"]))["state"] == "succeeded"
            assert (await client.get("/v1/agenda", headers={"Authorization": "Bearer access-backend-8001"})).status_code == 200


async def test_failed_helper_never_makes_an_unconfigured_space_ready(platform, tmp_path):
    original_app, registry, _, _, _ = platform
    helper = tmp_path / "fail-provision"
    helper.write_text("#!/bin/sh\nexit 2\n")
    helper.chmod(0o700)
    cfg = original_app.state.settings.model_copy(update={"provisioner": str(helper)})
    app = create_app(cfg, registry, original_app.state.client._transport)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            headers = await login(client)
            response = await client.post("/control/v1/spaces", json={"name": "Failure", "owner_name": "Owner"}, headers=headers)
            result = await wait_operation(registry, response.json()["operation_id"])
            assert result["state"] == "failed"
            assert registry.get_space(response.json()["id"])["state"] == "failed"
            assert (await client.get("/s/" + response.json()["id"] + "/health")).status_code == 423

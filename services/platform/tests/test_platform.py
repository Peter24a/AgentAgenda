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
            identity_suffix = host + "-" + body["operation_id"] if host == "backend-8400" else host
            result = state["receipts"].setdefault(body["operation_id"], {"device_id": "new-device-" + identity_suffix, "access_token": "access-" + identity_suffix, "refresh_token": "refresh-" + identity_suffix, "expires_in": 3600, "token_type": "bearer", "scopes": ["agenda:read", "agenda:write"]})
            if state["fail_after_enroll"]:
                state["fail_after_enroll"] = False
                raise httpx.ReadError("Synthetic lost enrollment response", request=request)
            return httpx.Response(200, json=result)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "private": "do not expose"})
        if request.url.path == "/v1/auth/me":
            if host == "backend-8400":
                matching = next((value for value in state["receipts"].values() if bearer == "Bearer " + value["access_token"] and host in value["access_token"]), None)
                if not matching:
                    return httpx.Response(401, json={"detail": "bad token"})
                return httpx.Response(200, json={"user_id": "default_user", "device_id": matching["device_id"], "token_id": "token", "scopes": ["agenda:read"]})
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
        if request.url.path == "/internal/metrics":
            return httpx.Response(200, json={"usage_bytes": 123, "quota_bytes": 5000, "health": "ready", "pending_ai_reports": 2, "report_details": "Synthetic private report", "message_id": "private-message"})
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


@pytest.fixture
def review_platform(platform):
    original, registry, personal, walter, state = platform
    review = registry.create_space("Google Play review", "Synthetic review account")
    registry.configure_space(review["id"], "http://backend-8400", "default_user", "secret-8400-" + "z" * 40)
    registry.set_space_state(review["id"], "ready")
    cfg = original.state.settings.model_copy(update={"review_space_id": review["id"]})
    app = create_app(cfg, registry, original.state.client._transport)
    credential = registry.create_review_credential(review["id"], cfg.review_space_id)
    return app, registry, personal, walter, review, credential, state


async def test_review_code_reusable_new_installs_and_idempotent_retry(review_platform):
    app, registry, personal, walter, review, credential, state = review_platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        first, body = await activate(client, registry, review, code=credential["code"])
        assert first.status_code == 200
        retry = await client.post("/platform/v1/activate", json=body)
        assert retry.json() == first.json()
        assert len(state["enroll_calls"]) == 1
        # Client-supplied space/device selection never expands review access.
        second = await client.post("/platform/v1/activate", json={**body, "request_id": str(uuid.uuid4()), "device_name": "Another reviewer", "space_id": personal["id"], "client_device_id": "some-other-device"})
        assert second.status_code == 200
        assert second.json()["space_id"] == review["id"]
        assert first.json()["device_id"] != second.json()["device_id"]
        assert first.json()["access_token"] != second.json()["access_token"]
        assert len({call["operation_id"] for call in state["enroll_calls"]}) == 2
        assert all(call["client_device_id"] is None for call in state["enroll_calls"])
        assert all(request.url.host == "backend-8400" for request in state["requests"])
        headers = {"Authorization": "Bearer " + first.json()["access_token"]}
        for space in (personal, walter):
            assert (await client.get("/s/" + space["id"] + "/v1/agenda", headers=headers)).status_code == 401
        assert (await client.get("/control/v1/spaces", headers=headers)).status_code == 401
    with registry.connect() as db:
        credential_row = db.execute("SELECT * FROM review_credentials").fetchone()
        assert credential["code"] not in credential_row["code_hash"]
        rows = db.execute("SELECT * FROM review_activations").fetchall()
        assert len(rows) == 2
        assert all("access-" not in row["result"] for row in rows)
        assert registry.open(rows[0]["result"])["access_token"] == first.json()["access_token"]


async def test_review_code_changed_fingerprint_cannot_replay(review_platform):
    app, registry, _, _, review, credential, state = review_platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        first, body = await activate(client, registry, review, code=credential["code"])
        assert first.status_code == 200
        for update in ({"device_name": "Different"}, {"platform": "ios"}, {"client_device_id": "another-id"}):
            assert (await client.post("/platform/v1/activate", json={**body, **update})).status_code == 409
        assert len(state["enroll_calls"]) == 1


async def test_review_code_lost_response_recovers_original_operation(review_platform):
    app, registry, _, _, review, credential, state = review_platform
    state["fail_after_enroll"] = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        first, body = await activate(client, registry, review, code=credential["code"])
        assert first.status_code == 503
        retry = await client.post("/platform/v1/activate", json=body)
        assert retry.status_code == 200
        assert len(state["enroll_calls"]) == 2
        assert len({call["operation_id"] for call in state["enroll_calls"]}) == 1
        assert len(state["receipts"]) == 1


async def test_concurrent_review_retry_enrolls_once(review_platform):
    app, registry, _, _, review, credential, state = review_platform
    body = {"code": credential["code"], "device_name": "Same retry", "platform": "android", "request_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        replies = await asyncio.gather(*(client.post("/platform/v1/activate", json=body) for _ in range(4)))
        assert all(reply.status_code == 200 for reply in replies)
        assert all(reply.json() == replies[0].json() for reply in replies)
        assert len(state["enroll_calls"]) == 1
    with registry.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM review_activations").fetchone()[0] == 1


@pytest.mark.parametrize("interruption,expected_status", [("revoke", 400), ("suspend", 423)])
async def test_review_revocation_or_suspension_during_enrollment_cannot_emit_credentials(review_platform, interruption, expected_status):
    original, registry, _, _, review, credential, _ = review_platform
    underlying = original.state.client._transport.handler

    async def interrupted_backend(request):
        result = await underlying(request)
        if request.url.path == "/internal/enroll":
            if interruption == "revoke":
                registry.revoke_review_credential(credential["credential_id"])
            else:
                registry.set_space_state(review["id"], "suspended")
        return result

    app = create_app(original.state.settings, registry, httpx.MockTransport(interrupted_backend))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        result, _ = await activate(client, registry, review, code=credential["code"])
        assert result.status_code == expected_status
        assert "access_token" not in result.text and "refresh_token" not in result.text
    with registry.connect() as db:
        assert db.execute("SELECT result FROM review_activations").fetchone()[0] is None


async def test_revoked_review_code_blocks_both_retries_and_new_installs(review_platform):
    app, registry, _, _, review, credential, state = review_platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        first, body = await activate(client, registry, review, code=credential["code"])
        assert first.status_code == 200
        registry.revoke_review_credential(credential["credential_id"])
        requests_before = len(state["requests"])
        for request_id in (body["request_id"], str(uuid.uuid4())):
            result = await client.post("/platform/v1/activate", json={**body, "request_id": request_id})
            assert result.status_code == 400
        assert len(state["requests"]) == requests_before


@pytest.mark.parametrize("state_name", ["suspended", "closed", "failed", "provisioning"])
async def test_unavailable_review_space_rejects_reusable_code(review_platform, state_name):
    app, registry, _, _, review, credential, state = review_platform
    registry.set_space_state(review["id"], state_name)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        response, _ = await activate(client, registry, review, code=credential["code"])
        assert response.status_code == 423
        assert not state["requests"]


@pytest.mark.parametrize("allowlist", ["disabled", "different", "legacy"])
async def test_review_code_allowlist_and_nonlegacy_guard(review_platform, allowlist):
    original, registry, personal, _, review, credential, state = review_platform
    cfg = original.state.settings
    if allowlist != "legacy":
        cfg = cfg.model_copy(update={"review_space_id": "" if allowlist == "disabled" else personal["id"]})
    else:
        with registry.connect() as db:
            db.execute("UPDATE spaces SET legacy=0 WHERE id=?", (personal["id"],))
            db.execute("UPDATE spaces SET legacy=1 WHERE id=?", (review["id"],))
    app = create_app(cfg, registry, original.state.client._transport)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        response, _ = await activate(client, registry, review, code=credential["code"])
        assert response.status_code == 400
        assert not state["requests"]


async def test_review_creation_requires_ready_explicitly_allowlisted_nonlegacy_space(platform):
    _, registry, personal, walter, _ = platform
    from app.registry import RegistryError
    for target, allowed in ((walter["id"], ""), (walter["id"], personal["id"]), (personal["id"], personal["id"])):
        with pytest.raises(RegistryError):
            registry.create_review_credential(target, allowed)
    registry.set_space_state(walter["id"], "suspended")
    with pytest.raises(RegistryError):
        registry.create_review_credential(walter["id"], walter["id"])
    with registry.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM review_credentials").fetchone()[0] == 0


async def test_review_rotation_and_ordinary_single_use_invitation_remain_separate(review_platform):
    app, registry, personal, _, review, old, _ = review_platform
    ordinary = registry.create_invitation(personal["id"], "enroll", 60)
    new = registry.create_review_credential(review["id"], app.state.settings.review_space_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await activate(client, registry, review, code=old["code"]))[0].status_code == 400
        assert (await activate(client, registry, review, code=new["code"]))[0].status_code == 200
        first, body = await activate(client, registry, personal, code=ordinary["code"])
        assert first.status_code == 200
        assert (await client.post("/platform/v1/activate", json={**body, "request_id": str(uuid.uuid4())})).status_code == 409


async def test_review_web_activation_preserves_origin_cookie_csrf_boundaries(review_platform):
    app, registry, _, _, review, credential, state = review_platform
    body = {"code": credential["code"], "device_name": "Reviewer browser", "platform": "web", "request_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.post("/platform/v1/activate", json=body)).status_code == 403
        assert (await client.post("/platform/v1/activate", json=body, headers={"Origin": "https://evil.example"})).status_code == 403
        assert not state["requests"]
        response = await client.post("/platform/v1/activate", json=body, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert "access_token" not in response.text and "refresh_token" not in response.text
        assert "HttpOnly" in response.headers["set-cookie"]
        assert (await client.get("/platform/v1/session")).json()["space_id"] == review["id"]
        assert (await client.post("/s/" + review["id"] + "/v1/agenda", json={})).status_code == 403


async def test_public_support_policy_and_authenticated_report_metadata(platform, tmp_path):
    app, registry, personal, _, state = platform
    web_root = Path(app.state.settings.web_root)
    web_root.mkdir()
    (web_root / "support.html").write_text("<html><body>AgentAgenda support</body></html>")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        policy = await client.get("/privacidad")
        assert policy.status_code == 302
        assert policy.headers["location"] == "https://privacy.ici-labs.com/agentagenda/"
        support = await client.get("/soporte")
        assert support.status_code == 200 and "AgentAgenda support" in support.text
        detail_path = "/control/v1/spaces/" + personal["id"]
        assert (await client.get(detail_path)).status_code == 401
        await login(client)
        detail = await client.get(detail_path)
        assert detail.status_code == 200
        assert detail.json()["pending_ai_reports"] == 2
        assert detail.json()["usage_bytes"] == 123
        assert "report_details" not in detail.text and "private-message" not in detail.text
        assert state["requests"][-1].url.path == "/internal/metrics"
        assert "x-enrollment-key" in state["requests"][-1].headers


def test_review_cli_exports_private_file_and_revokes_without_printing_code(review_platform, tmp_path, monkeypatch, capsys):
    from app import cli
    app, registry, _, _, review, _, _ = review_platform
    monkeypatch.setattr(cli, "Settings", lambda: app.state.settings)
    output = tmp_path / "review-code.json"
    monkeypatch.setattr(sys, "argv", ["cli", "create-review-code", review["id"], "--output", str(output)])
    cli.main()
    exported = json.loads(output.read_text())
    stdout = capsys.readouterr().out
    assert exported["space_id"] == review["id"] and exported["expires_at"] is None
    assert exported["code"] not in stdout
    assert output.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(sys, "argv", ["cli", "revoke-review-code", exported["credential_id"]])
    cli.main()
    assert json.loads(capsys.readouterr().out)["revoked"] is True
    from app.registry import RegistryError
    with pytest.raises(RegistryError):
        registry.reserve_review_activation(exported["code"], str(uuid.uuid4()), "fingerprint", review["id"])


def test_review_allowlist_requires_uuid():
    with pytest.raises(ValueError):
        Settings(review_space_id="not-a-space-id")

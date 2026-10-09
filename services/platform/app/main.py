import asyncio
import hmac
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .registry import Registry, RegistryError
from .security import RateLimiter, digest, verify_password

log = logging.getLogger("agentagenda.platform")
ADMIN_COOKIE = "aa_admin"
OWNER_COOKIE = "aa_owner"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
REQUEST_HEADERS = {
    "authorization", "accept", "content-type", "if-match", "if-none-match", "range",
    "last-event-id", "x-request-id", "x-idempotency-key", "origin",
    "mcp-protocol-version", "mcp-session-id",
}
RESPONSE_HEADERS = {
    "content-type", "content-disposition", "content-length", "content-range",
    "accept-ranges", "etag", "last-modified", "retry-after", "www-authenticate",
    "mcp-session-id", "mcp-protocol-version", "content-encoding",
}


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class NewSpace(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    owner_name: str = Field(min_length=1, max_length=128)
    quota_bytes: int | None = Field(default=None, ge=1048576, le=1099511627776)


class Invitation(BaseModel):
    purpose: Literal["enroll", "reconnect"] = "enroll"
    replace_device_id: str | None = Field(default=None, max_length=128)


class Activate(BaseModel):
    code: str = Field(min_length=16, max_length=256)
    device_name: str = Field(min_length=1, max_length=128)
    platform: Literal["android", "ios", "web", "cli"] = "android"
    client_device_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, min_length=16, max_length=128)


def create_app(settings: Settings | None = None, registry: Registry | None = None, transport=None) -> FastAPI:
    cfg = settings or Settings()
    origin = cfg.validated_origin()
    reg = registry or Registry(cfg.registry_path, cfg.encryption_key())
    admin_hash = cfg.password_hash()
    secure_cookie = origin.startswith("https://")
    client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10, read=300), follow_redirects=False, transport=transport, trust_env=False)
    pending_tasks: set[asyncio.Task] = set()
    activation_locks: dict[str, asyncio.Lock] = {}
    session_locks: dict[str, asyncio.Lock] = {}
    login_limit, activation_limit = RateLimiter(10, 300), RateLimiter(30, 300)

    async def run_operation(operation_id: str):
        operation = reg.get_operation(operation_id)
        space_id, action = operation["space_id"], operation["action"]
        reg.set_operation_state(operation_id, "running")
        process = None
        operation_log = None
        try:
            if not cfg.provisioner or not Path(cfg.provisioner).is_file():
                raise RuntimeError("Provisioner not configured")
            # The only privileged process is a fixed, preinstalled helper with constrained UUID arguments.
            uuid.UUID(space_id)
            log_dir = Path(reg.path).parent / "operations"
            log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            log_dir.chmod(0o700)
            log_fd = os.open(log_dir / (operation_id + ".log"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            operation_log = os.fdopen(log_fd, "ab")
            process = await asyncio.create_subprocess_exec(
                cfg.provisioner, action, space_id,
                stdout=operation_log, stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PLATFORM_REGISTRY_PATH": cfg.registry_path, "PLATFORM_KEY_FILE": cfg.key_file},
            )
            returncode = await asyncio.wait_for(process.wait(), cfg.operation_timeout_seconds)
            if returncode:
                raise RuntimeError("Provisioner failed")
            configured = reg.get_space(space_id, include_secret=True)
            new_state = {"create": "ready", "resume": "ready", "reopen": "ready", "suspend": "suspended", "close": "closed"}[action]
            if new_state == "ready" and not all(configured[f] for f in ("backend_url", "user_id", "enrollment_key")):
                raise RuntimeError("Provisioner did not configure target")
            reg.set_space_state(space_id, new_state)
            reg.set_operation_state(operation_id, "succeeded")
        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.terminate()
                await process.wait()
            reg.set_operation_state(operation_id, "queued")
            raise
        except Exception:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            if action == "create":
                reg.set_space_state(space_id, "failed")
            reg.set_operation_state(operation_id, "failed", "La operación no se completó. Revisar el registro privado del servidor y reintentar.")
            log.warning("Platform operation failed: %s %s", operation_id, action)
        finally:
            if operation_log:
                operation_log.close()

    def queue_operation(operation_id: str):
        task = asyncio.create_task(run_operation(operation_id))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    @asynccontextmanager
    async def lifespan(_app):
        for operation in reg.list_operations(pending=True):
            queue_operation(operation["id"])
        yield
        for task in list(pending_tasks):
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        await client.aclose()

    app = FastAPI(title="AgentAgenda Platform", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in cfg.trusted_hosts.split(",")])
    app.state.registry, app.state.settings = reg, cfg
    app.state.client = client

    @app.exception_handler(RegistryError)
    async def registry_error(_request, exc: RegistryError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    @app.middleware("http")
    async def response_security(request: Request, call_next):
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > cfg.max_request_bytes or int(length) < 0:
                    return JSONResponse({"detail": "Archivo demasiado grande"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Longitud inválida"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        if secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def check_origin(request: Request, required: bool = False):
        supplied = request.headers.get("origin")
        if supplied and supplied != origin:
            raise HTTPException(403, "Origen no autorizado")
        if required and not supplied:
            # Same-origin fetch sends Origin on mutations; no blind cookie-only actions.
            raise HTTPException(403, "Se requiere origen de la aplicación")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Origen no autorizado")

    def check_csrf(request: Request, session: dict):
        check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied.encode(), session["csrf"].encode()):
            raise HTTPException(403, "Sesión de formulario inválida")

    def admin(request: Request):
        session = reg.get_session(request.cookies.get(ADMIN_COOKIE), "admin")
        if request.method not in SAFE_METHODS:
            check_csrf(request, session)
        return session

    def available(space_id: str):
        space = reg.get_space(space_id, include_secret=True)
        if space["state"] != "ready":
            raise RegistryError(423, "Espacio suspendido, cerrado o en preparación")
        if not space["backend_url"] or not space["user_id"]:
            raise RegistryError(503, "Espacio no disponible")
        return space

    async def backend_json(space, method: str, path: str, *, token: str | None = None, json_body=None, headers=None):
        outgoing = dict(headers or {})
        if token:
            outgoing["Authorization"] = "Bearer " + token
        try:
            response = await client.request(method, space["backend_url"] + path, headers=outgoing, json=json_body)
        except httpx.HTTPError:
            raise HTTPException(503, "El espacio no está disponible; intenta de nuevo")
        if response.is_redirect:
            raise HTTPException(502, "Respuesta de espacio inválida")
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                raise HTTPException(response.status_code, "Sesión no autorizada")
            raise HTTPException(503, "El espacio no está disponible; intenta de nuevo")
        try:
            result = response.json()
        except ValueError:
            raise HTTPException(502, "Respuesta de espacio inválida")
        return result

    async def validate_identity(space, token: str):
        identity = await backend_json(space, "GET", "/v1/auth/me", token=token)
        if not isinstance(identity, dict) or identity.get("user_id") != space["user_id"] or not identity.get("device_id"):
            raise HTTPException(403, "La sesión no pertenece al espacio")
        return identity

    async def owner(request: Request, space_id: str | None = None):
        session = reg.get_session(request.cookies.get(OWNER_COOKIE), "owner")
        if space_id and session["space_id"] != space_id:
            raise HTTPException(403, "La sesión no pertenece al espacio")
        space = available(session["space_id"])
        if request.method not in SAFE_METHODS:
            check_csrf(request, session)
        lock = session_locks.setdefault(session["token_hash"], asyncio.Lock())
        async with lock:
            session = reg.get_session(request.cookies.get(OWNER_COOKIE), "owner")
            value = session["value"]
            if value.get("access_expires_at", 0) < time.time() + 60:
                refreshed = await backend_json(space, "POST", "/v1/auth/refresh", json_body={"refresh_token": value["refresh_token"]})
                value.update(access_token=refreshed["access_token"], refresh_token=refreshed["refresh_token"], access_expires_at=time.time() + refreshed["expires_in"])
                reg.update_session(session["token_hash"], value)
            await validate_identity(space, value["access_token"])
        return session, space

    def owner_metadata(session, space):
        return {"space_id": space["id"], "space_name": space["name"], "base_url": origin + "/s/" + space["id"], "device_id": session["value"]["device_id"], "device_name": session["value"].get("device_name"), "csrf_token": session["csrf"], "expires_at": session["expires_at"]}

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "agentagenda-platform"}

    @app.post("/control/v1/auth/login")
    async def login(body: Login, request: Request, response: Response):
        check_origin(request)
        peer = request.client.host if request.client else "unknown"
        if not login_limit.allow(peer):
            raise HTTPException(429, "Demasiados intentos; espera unos minutos", headers={"Retry-After": "300"})
        password_ok = await asyncio.to_thread(verify_password, body.password, admin_hash)
        if not hmac.compare_digest(body.username.encode(), cfg.admin_username.encode()) or not password_ok:
            raise HTTPException(401, "Credenciales inválidas")
        reg.delete_session(request.cookies.get(ADMIN_COOKIE))
        token, csrf = reg.create_session("admin", {"username": cfg.admin_username}, cfg.session_seconds)
        response.set_cookie(ADMIN_COOKIE, token, httponly=True, secure=secure_cookie, samesite="strict", path="/control", max_age=cfg.session_seconds)
        return {"username": cfg.admin_username, "csrf_token": csrf}

    @app.get("/control/v1/auth/me")
    async def admin_me(request: Request):
        session = admin(request)
        return {"username": session["value"]["username"], "csrf_token": session["csrf"]}

    @app.post("/control/v1/auth/logout")
    async def admin_logout(request: Request, response: Response):
        admin(request)
        reg.delete_session(request.cookies.get(ADMIN_COOKIE))
        response.delete_cookie(ADMIN_COOKIE, path="/control")
        return {"ok": True}

    @app.get("/control/v1/spaces")
    async def list_spaces(request: Request):
        admin(request)
        return {"spaces": reg.list_spaces()}

    @app.post("/control/v1/spaces", status_code=202)
    async def new_space(body: NewSpace, request: Request):
        admin(request)
        if not cfg.provisioner:
            raise HTTPException(503, "El aprovisionamiento no está configurado")
        name, owner_name = body.name.strip(), body.owner_name.strip()
        if not name or not owner_name:
            raise HTTPException(422, "Indica el nombre y propietario")
        space, operation = reg.create_managed_space(name, owner_name, body.quota_bytes)
        queue_operation(operation["id"])
        return {**space, "operation_id": operation["id"]}

    @app.get("/control/v1/spaces/{space_id}")
    async def space_detail(space_id: str, request: Request):
        admin(request)
        metadata = reg.get_space(space_id)
        metadata["health"] = metadata["state"]
        metadata["usage_bytes"] = None
        metadata["pending_ai_reports"] = None
        if metadata["state"] == "ready":
            space = reg.get_space(space_id, include_secret=True)
            try:
                metrics = await backend_json(space, "GET", "/internal/metrics", headers={"X-Enrollment-Key": space["enrollment_key"]})
                usage = metrics.get("usage_bytes")
                if isinstance(usage, int) and usage >= 0:
                    metadata["usage_bytes"] = usage
                metadata["health"] = "ready" if metrics.get("health") == "ready" else "unavailable"
                effective_quota = metrics.get("quota_bytes")
                metadata["effective_quota_bytes"] = effective_quota if isinstance(effective_quota, int) and effective_quota > 0 else None
                pending_reports = metrics.get("pending_ai_reports")
                if isinstance(pending_reports, int) and not isinstance(pending_reports, bool) and pending_reports >= 0:
                    metadata["pending_ai_reports"] = pending_reports
            except HTTPException:
                metadata["health"] = "unavailable"
        return metadata

    @app.post("/control/v1/spaces/{space_id}/activation")
    async def invitation(space_id: str, body: Invitation, request: Request):
        admin(request)
        if body.replace_device_id and body.purpose != "reconnect":
            raise HTTPException(422, "El dispositivo anterior sólo aplica a reconexión")
        return reg.create_invitation(space_id, body.purpose, cfg.invitation_seconds, body.replace_device_id)

    @app.post("/control/v1/spaces/{space_id}/{action}", status_code=202)
    async def space_action(space_id: str, action: str, request: Request):
        admin(request)
        allowed = {"suspend": {"ready", "suspended"}, "resume": {"suspended"}, "close": {"ready", "suspended", "closed"}, "reopen": {"closed"}, "retry": {"failed"}}
        if action not in allowed:
            raise HTTPException(404, "Acción no encontrada")
        space = reg.get_space(space_id)
        if space["state"] not in allowed[action]:
            raise HTTPException(409, "La acción no corresponde al estado actual")
        operation = reg.create_operation(space_id, "create" if action == "retry" else action)
        if action in {"suspend", "close"}:
            reg.set_space_state(space_id, "suspended" if action == "suspend" else "closed")
        elif action == "retry":
            reg.set_space_state(space_id, "provisioning")
        queue_operation(operation["id"])
        return {**reg.get_space(space_id), "operation_id": operation["id"]}

    @app.get("/control/v1/operations")
    async def operations(request: Request):
        admin(request)
        return {"operations": reg.list_operations()}

    @app.get("/control/v1/operations/{operation_id}")
    async def operation_detail(operation_id: str, request: Request):
        admin(request)
        return reg.get_operation(operation_id)

    @app.post("/platform/v1/activate")
    async def activate(body: Activate, request: Request, response: Response):
        check_origin(request, required=body.platform == "web")
        peer = request.client.host if request.client else "unknown"
        if not activation_limit.allow(peer):
            raise HTTPException(429, "Demasiados intentos; espera unos minutos", headers={"Retry-After": "300"})
        nonce = body.request_id or str(uuid.uuid4())
        fingerprint = digest(json.dumps({"device_name": body.device_name, "platform": body.platform, "client_device_id": body.client_device_id}, sort_keys=True))
        invite = reg.reserve_review_activation(body.code.strip(), nonce, fingerprint, cfg.review_space_id)
        is_review = invite is not None
        if not is_review:
            invite = reg.reserve_invitation(body.code.strip(), nonce, fingerprint)
        space = available(invite["space_id"])
        operation_id = invite["operation_id"]
        lock = activation_locks.setdefault(operation_id, asyncio.Lock())
        async with lock:
            # Re-read the receipt after locking so simultaneous retries never enroll twice.
            invite = (reg.reserve_review_activation(body.code.strip(), nonce, fingerprint, cfg.review_space_id)
                      if is_review else reg.reserve_invitation(body.code.strip(), nonce, fingerprint))
            result = invite["result"]
            if not result:
                result = await backend_json(space, "POST", "/internal/enroll", headers={"X-Enrollment-Key": space["enrollment_key"]}, json_body={"operation_id": operation_id, "user_id": space["user_id"], "device_name": body.device_name, "platform": body.platform, "client_device_id": None if is_review else body.client_device_id, "replace_device_id": invite["replace_device_id"]})
                if not isinstance(result, dict) or not all(k in result for k in ("device_id", "access_token", "refresh_token", "expires_in", "scopes")):
                    raise HTTPException(502, "Respuesta de activación inválida")
                identity = await validate_identity(space, result["access_token"])
                if identity["device_id"] != result["device_id"]:
                    raise HTTPException(502, "Identidad de activación inválida")
                result["access_expires_at"] = time.time() + result["expires_in"]
                if is_review:
                    reg.finish_review_activation(invite["credential_id"], nonce, result, cfg.review_space_id)
                else:
                    reg.finish_invitation(invite["code_hash"], result)
        available(space["id"])
        if is_review:
            # Revocation/state changes while upstream enrollment awaited must block the response too.
            reg.reserve_review_activation(body.code.strip(), nonce, fingerprint, cfg.review_space_id)
        metadata = {"space_id": space["id"], "space_name": space["name"], "base_url": origin + "/s/" + space["id"]}
        if body.platform == "web":
            # Passwords/tokens never enter browser localStorage or administrative responses.
            reg.delete_session(request.cookies.get(OWNER_COOKIE))
            token, _csrf = reg.create_session("owner", {**result, "device_name": body.device_name}, cfg.session_seconds, space["id"])
            response.set_cookie(OWNER_COOKIE, token, httponly=True, secure=secure_cookie, samesite="strict", path="/", max_age=cfg.session_seconds)
            return owner_metadata(reg.get_session(token, "owner"), space)
        return {**metadata, **{k: v for k, v in result.items() if k != "access_expires_at"}}

    @app.get("/platform/v1/session")
    async def owner_session(request: Request):
        session, space = await owner(request)
        return owner_metadata(session, space)

    @app.post("/platform/v1/logout")
    async def owner_logout(request: Request, response: Response):
        session = reg.get_session(request.cookies.get(OWNER_COOKIE), "owner")
        check_csrf(request, session)
        reg.delete_session(request.cookies.get(OWNER_COOKIE))
        response.delete_cookie(OWNER_COOKIE, path="/")
        return {"ok": True}

    @app.post("/platform/v1/activation")
    async def owner_invitation(request: Request):
        _session, space = await owner(request)
        return reg.create_invitation(space["id"], "enroll", cfg.invitation_seconds)

    @app.get("/platform/v1/devices")
    async def owner_devices(request: Request):
        session, space = await owner(request)
        result = await backend_json(space, "GET", "/v1/devices", token=session["value"]["access_token"])
        return {"devices": result if isinstance(result, list) else result.get("devices", [])}

    @app.post("/platform/v1/devices/{device_id}/revoke")
    async def owner_revoke(device_id: str, request: Request):
        session, space = await owner(request)
        result = await backend_json(space, "POST", "/v1/auth/revoke", token=session["value"]["access_token"], json_body={"device_id": device_id})
        if device_id == session["value"]["device_id"]:
            reg.delete_session(request.cookies.get(OWNER_COOKIE))
        return result

    async def gateway(space: dict, path: str, request: Request):
        # v1 is the complete public allowlist; internal enrollment cannot be reached here.
        if path == "health":
            if request.method not in {"GET", "HEAD"}:
                raise HTTPException(405, "Método no permitido")
            await backend_json(space, "GET", "/health")
            return JSONResponse({"status": "ok", "space_id": space["id"]})
        if not path.startswith("v1/") or any(p in {".", "..", ""} for p in path.split("/")):
            raise HTTPException(404, "Ruta no encontrada")
        if path == "v1/auth/pair":
            raise HTTPException(404, "Usa la activación de la plataforma")
        headers = {k: v for k, v in request.headers.items() if k.lower() in REQUEST_HEADERS}
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            if path != "v1/auth/refresh":
                await validate_identity(space, authorization[7:].strip())
        elif request.cookies.get(OWNER_COOKIE):
            session, _space = await owner(request, space["id"])
            if path == "v1/auth/refresh":
                raise HTTPException(404, "La sesión web se renueva automáticamente")
            headers["authorization"] = "Bearer " + session["value"]["access_token"]
        elif path != "v1/auth/refresh":
            raise HTTPException(401, "Activa tu espacio para continuar", headers={"WWW-Authenticate": "Bearer"})
        else:
            # The backend itself validates the refresh token against this fixed tenant database.
            headers.pop("authorization", None)
        # Identity validation is asynchronous; recheck state before beginning any content operation.
        available(space["id"])
        async def body_stream():
            count = 0
            async for chunk in request.stream():
                count += len(chunk)
                if count > cfg.max_request_bytes:
                    raise HTTPException(413, "Archivo demasiado grande")
                yield chunk
        url = space["backend_url"] + "/" + path
        if request.url.query:
            url += "?" + request.url.query
        outgoing = client.build_request(request.method, url, headers=headers, content=body_stream())
        try:
            upstream = await client.send(outgoing, stream=True)
        except httpx.HTTPError:
            raise HTTPException(503, "El espacio no está disponible; intenta de nuevo")
        if upstream.is_redirect:
            await upstream.aclose()
            raise HTTPException(502, "El espacio intentó una redirección no permitida")
        response_headers = {k: v for k, v in upstream.headers.items() if k.lower() in RESPONSE_HEADERS}
        if upstream.headers.get("content-type", "").startswith("text/event-stream"):
            response_headers["X-Accel-Buffering"] = "no"
        async def response_stream():
            # Mock/ASGI transports may already have a body; network transports stay truly streamed.
            if upstream.is_stream_consumed:
                yield upstream.content
            else:
                async for chunk in upstream.aiter_raw():
                    if reg.get_space(space["id"])["state"] != "ready":
                        break
                    yield chunk
        return StreamingResponse(response_stream(), status_code=upstream.status_code, headers=response_headers, background=BackgroundTask(upstream.aclose))

    @app.api_route("/s/{space_id}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def space_gateway(space_id: str, path: str, request: Request):
        return await gateway(available(space_id), path, request)

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def legacy_gateway(path: str, request: Request):
        space = reg.legacy_space()
        return await gateway(available(space["id"]), "v1/" + path, request)

    @app.get("/download/agentagenda.apk")
    async def download_apk():
        path = Path(cfg.apk_path)
        if not path.is_file():
            raise HTTPException(404, "La descarga todavía no está disponible")
        return FileResponse(path, filename="AgentAgenda.apk", media_type="application/vnd.android.package-archive")

    web_root = Path(cfg.web_root)

    @app.get("/privacidad")
    async def privacy_policy():
        return RedirectResponse("https://privacy.ici-labs.com/agentagenda/", status_code=302)

    @app.get("/soporte")
    async def public_support():
        path = web_root / "support.html"
        if not path.is_file():
            raise HTTPException(503, "La página de soporte todavía no está disponible")
        return FileResponse(path, media_type="text/html")

    if (web_root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

    @app.get("/")
    @app.get("/admin")
    @app.get("/activar")
    @app.get("/app")
    async def frontend():
        if not (web_root / "index.html").is_file():
            raise HTTPException(503, "La página todavía no está disponible")
        return FileResponse(web_root / "index.html", media_type="text/html")

    return app

"""Private durable registry. Customer content stays exclusively in its existing backend."""
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from .security import digest


class RegistryError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


class Registry:
    def __init__(self, path: str, key: bytes):
        self.path = path
        self.cipher = Fernet(key)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS spaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_name TEXT NOT NULL,
                    state TEXT NOT NULL, quota_bytes INTEGER, backend_url TEXT,
                    user_id TEXT, enrollment_key TEXT, legacy INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_legacy_space ON spaces(legacy) WHERE legacy=1;
                CREATE TABLE IF NOT EXISTS invitations (
                    code_hash TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id),
                    purpose TEXT NOT NULL, replace_device_id TEXT, expires_at REAL NOT NULL,
                    operation_id TEXT UNIQUE, request_id TEXT, fingerprint TEXT,
                    result TEXT, completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, space_id TEXT,
                    value TEXT NOT NULL, csrf TEXT NOT NULL, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id),
                    action TEXT NOT NULL, state TEXT NOT NULL, error TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_credentials (
                    id TEXT PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL,
                    space_id TEXT NOT NULL REFERENCES spaces(id),
                    created_at REAL NOT NULL, revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS review_activations (
                    credential_id TEXT NOT NULL REFERENCES review_credentials(id),
                    request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    operation_id TEXT UNIQUE NOT NULL, result TEXT,
                    created_at REAL NOT NULL, completed_at REAL,
                    PRIMARY KEY (credential_id, request_id)
                );
            """)
        Path(path).chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=20000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seal(self, value) -> str:
        return self.cipher.encrypt(json.dumps(value).encode()).decode()

    def open(self, value: str):
        return json.loads(self.cipher.decrypt(value.encode()))

    def get_space(self, space_id: str, include_secret: bool = False):
        with self.connect() as db:
            row = db.execute("SELECT * FROM spaces WHERE id=?", (space_id,)).fetchone()
        if row is None:
            raise RegistryError(404, "Espacio no encontrado")
        space = dict(row)
        if include_secret:
            if space["enrollment_key"]:
                space["enrollment_key"] = self.open(space["enrollment_key"])
        else:
            for field in ("backend_url", "user_id", "enrollment_key", "legacy"):
                space.pop(field, None)
        return space

    def list_spaces(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM spaces ORDER BY created_at")]
        return [self.get_space(i) for i in ids]

    def create_space(self, name: str, owner_name: str, quota_bytes: int | None = None, space_id: str | None = None):
        space_id = str(uuid.UUID(space_id)) if space_id else str(uuid.uuid4())
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO spaces(id,name,owner_name,state,quota_bytes,created_at,updated_at) VALUES(?,?,?,'provisioning',?,?,?)", (space_id, name, owner_name, quota_bytes, now, now))
        return self.get_space(space_id)

    def create_managed_space(self, name: str, owner_name: str, quota_bytes: int | None = None):
        """Persist the resource and its work item together, including across power loss."""
        space_id, operation_id, now = str(uuid.uuid4()), str(uuid.uuid4()), time.time()
        with self.connect() as db:
            db.execute("INSERT INTO spaces(id,name,owner_name,state,quota_bytes,created_at,updated_at) VALUES(?,?,?,'provisioning',?,?,?)", (space_id, name, owner_name, quota_bytes, now, now))
            db.execute("INSERT INTO operations VALUES(?,?,?,'queued',NULL,?,?)", (operation_id, space_id, "create", now, now))
        return self.get_space(space_id), self.get_operation(operation_id)

    def configure_space(self, space_id: str, backend_url: str, user_id: str, enrollment_key: str, legacy: bool = False):
        target = urlsplit(backend_url)
        if target.scheme not in {"http", "https"} or not target.hostname or target.username or target.password or target.path not in {"", "/"} or target.query or target.fragment:
            raise ValueError("Backend must be a fixed HTTP origin")
        if not user_id or len(enrollment_key) < 32:
            raise ValueError("Owner identity and a strong enrollment key are required")
        with self.connect() as db:
            changed = db.execute("UPDATE spaces SET backend_url=?,user_id=?,enrollment_key=?,legacy=?,updated_at=? WHERE id=?", (backend_url.rstrip("/"), user_id, self.seal(enrollment_key), int(legacy), time.time(), space_id)).rowcount
            if not changed:
                raise RegistryError(404, "Espacio no encontrado")

    def set_space_state(self, space_id: str, state: str):
        if state not in {"ready", "provisioning", "failed", "suspended", "closed"}:
            raise ValueError("Invalid state")
        with self.connect() as db:
            db.execute("UPDATE spaces SET state=?,updated_at=? WHERE id=?", (state, time.time(), space_id))
            if state == "closed":
                db.execute("DELETE FROM sessions WHERE space_id=?", (space_id,))

    def legacy_space(self):
        with self.connect() as db:
            row = db.execute("SELECT id FROM spaces WHERE legacy=1").fetchone()
        if not row:
            raise RegistryError(404, "Compatibilidad personal no configurada")
        return self.get_space(row[0], include_secret=True)

    def create_invitation(self, space_id: str, purpose: str, ttl: int, replace_device_id: str | None = None):
        space = self.get_space(space_id, include_secret=True)
        if space["state"] != "ready" or not space["backend_url"] or not space["enrollment_key"]:
            raise RegistryError(423, "Espacio no disponible")
        code = secrets.token_urlsafe(24)
        expiry = time.time() + ttl
        with self.connect() as db:
            # A replacement invitation invalidates unclaimed codes only; reserved operations remain retryable.
            db.execute("DELETE FROM invitations WHERE space_id=? AND operation_id IS NULL", (space_id,))
            db.execute("INSERT INTO invitations(code_hash,space_id,purpose,replace_device_id,expires_at) VALUES(?,?,?,?,?)", (digest(code), space_id, purpose, replace_device_id, expiry))
        return {"code": code, "expires_at": expiry, "purpose": purpose}

    def reserve_invitation(self, code: str, request_id: str, fingerprint: str):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM invitations WHERE code_hash=?", (digest(code),)).fetchone()
            if not row:
                raise RegistryError(400, "Código inválido o vencido")
            invite = dict(row)
            if invite["operation_id"]:
                if invite["request_id"] != request_id or invite["fingerprint"] != fingerprint:
                    raise RegistryError(409, "Código ya utilizado")
                if now > invite["expires_at"] + 86400:
                    raise RegistryError(400, "Código inválido o vencido")
            else:
                if now > invite["expires_at"]:
                    raise RegistryError(400, "Código inválido o vencido")
                invite.update(operation_id=str(uuid.uuid4()), request_id=request_id, fingerprint=fingerprint)
                db.execute("UPDATE invitations SET operation_id=?,request_id=?,fingerprint=? WHERE code_hash=?", (invite["operation_id"], request_id, fingerprint, invite["code_hash"]))
            if invite["result"]:
                invite["result"] = self.open(invite["result"])
        return invite

    def finish_invitation(self, code_hash: str, result: dict):
        with self.connect() as db:
            db.execute("UPDATE invitations SET result=?,completed_at=? WHERE code_hash=?", (self.seal(result), time.time(), code_hash))

    def _review_target(self, db, space_id: str, allowed_space_id: str):
        if not allowed_space_id or space_id != allowed_space_id:
            raise RegistryError(400, "Código inválido o vencido")
        row = db.execute("SELECT * FROM spaces WHERE id=?", (space_id,)).fetchone()
        if not row or row["legacy"]:
            raise RegistryError(400, "Código inválido o vencido")
        if row["state"] != "ready":
            raise RegistryError(423, "Espacio suspendido, cerrado o en preparación")
        if not row["backend_url"] or not row["user_id"] or not row["enrollment_key"]:
            raise RegistryError(503, "Espacio no disponible")

    def create_review_credential(self, space_id: str, allowed_space_id: str):
        """Operator-only reusable credential for one explicitly allowlisted demo space."""
        credential_id, code, now = str(uuid.uuid4()), "review_" + secrets.token_urlsafe(24), time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._review_target(db, space_id, allowed_space_id)
            db.execute("UPDATE review_credentials SET revoked_at=? WHERE space_id=? AND revoked_at IS NULL", (now, space_id))
            db.execute("INSERT INTO review_credentials(id,code_hash,space_id,created_at) VALUES(?,?,?,?)", (credential_id, digest(code), space_id, now))
        return {"credential_id": credential_id, "code": code, "space_id": space_id, "expires_at": None}

    def revoke_review_credential(self, credential_id: str):
        with self.connect() as db:
            changed = db.execute("UPDATE review_credentials SET revoked_at=COALESCE(revoked_at,?) WHERE id=?", (time.time(), credential_id)).rowcount
            if not changed:
                raise RegistryError(404, "Credencial de revisión no encontrada")
        return {"credential_id": credential_id, "revoked": True}

    def reserve_review_activation(self, code: str, request_id: str, fingerprint: str, allowed_space_id: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            credential = db.execute("SELECT * FROM review_credentials WHERE code_hash=?", (digest(code),)).fetchone()
            if not credential:
                return None
            if credential["revoked_at"] is not None:
                raise RegistryError(400, "Código inválido o vencido")
            self._review_target(db, credential["space_id"], allowed_space_id)
            activation = db.execute("SELECT * FROM review_activations WHERE credential_id=? AND request_id=?", (credential["id"], request_id)).fetchone()
            if activation:
                activation = dict(activation)
                if activation["fingerprint"] != fingerprint:
                    raise RegistryError(409, "La solicitud ya está vinculada a otro dispositivo")
            else:
                activation = {"credential_id": credential["id"], "request_id": request_id, "fingerprint": fingerprint,
                              "operation_id": str(uuid.uuid4()), "result": None}
                db.execute("INSERT INTO review_activations(credential_id,request_id,fingerprint,operation_id,created_at) VALUES(?,?,?,?,?)", (credential["id"], request_id, fingerprint, activation["operation_id"], time.time()))
            activation.update(space_id=credential["space_id"], replace_device_id=None)
            if activation["result"]:
                activation["result"] = self.open(activation["result"])
            return activation

    def finish_review_activation(self, credential_id: str, request_id: str, result: dict, allowed_space_id: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            credential = db.execute("SELECT * FROM review_credentials WHERE id=?", (credential_id,)).fetchone()
            if not credential or credential["revoked_at"] is not None:
                raise RegistryError(400, "Código inválido o vencido")
            self._review_target(db, credential["space_id"], allowed_space_id)
            db.execute("UPDATE review_activations SET result=?,completed_at=? WHERE credential_id=? AND request_id=?", (self.seal(result), time.time(), credential_id, request_id))

    def create_session(self, kind: str, value: dict, ttl: int, space_id: str | None = None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            db.execute("INSERT INTO sessions(token_hash,kind,space_id,value,csrf,expires_at) VALUES(?,?,?,?,?,?)", (digest(token), kind, space_id, self.seal(value), csrf, time.time() + ttl))
        return token, csrf

    def get_session(self, token: str | None, kind: str):
        if not token:
            raise RegistryError(401, "Inicia sesión")
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE token_hash=? AND kind=? AND expires_at>?", (digest(token), kind, time.time())).fetchone()
        if not row:
            raise RegistryError(401, "Sesión vencida")
        record = dict(row)
        record["value"] = self.open(record["value"])
        return record

    def update_session(self, token_hash: str, value: dict):
        with self.connect() as db:
            db.execute("UPDATE sessions SET value=? WHERE token_hash=?", (self.seal(value), token_hash))

    def delete_session(self, token: str | None):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def create_operation(self, space_id: str, action: str):
        now = time.time()
        operation_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM operations WHERE space_id=? AND state IN ('queued','running')", (space_id,)).fetchone():
                raise RegistryError(409, "El espacio tiene una operación en curso")
            db.execute("INSERT INTO operations VALUES(?,?,?,'queued',NULL,?,?)", (operation_id, space_id, action, now, now))
        return self.get_operation(operation_id)

    def get_operation(self, operation_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if not row:
            raise RegistryError(404, "Operación no encontrada")
        return dict(row)

    def list_operations(self, pending: bool = False):
        with self.connect() as db:
            query = "SELECT * FROM operations" + (" WHERE state IN ('queued','running')" if pending else "") + " ORDER BY created_at DESC LIMIT 100"
            return [dict(row) for row in db.execute(query)]

    def set_operation_state(self, operation_id: str, state: str, error: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE operations SET state=?,error=?,updated_at=? WHERE id=?", (state, error, time.time(), operation_id))

"""SARA Authorization Code + PKCE BFF for explicitly authorized administrators.

Credentials stay encrypted in the existing registry. A host-local lock serializes
refresh, callbacks and logout across threads/processes; no central signing keys.
"""
import base64
import fcntl
import hashlib
import hmac
import os
import secrets
import time
import uuid
from contextlib import contextmanager
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

from .registry import RegistryError
from .security import digest


class IdentityUnavailable(Exception):
    pass


class IdentityRejected(Exception):
    pass


class Grant(BaseModel):
    access_token: str = Field(min_length=1, max_length=16384)
    refresh_token: str = Field(min_length=40, max_length=256)
    token_type: Literal['bearer']
    client_id: str
    session_id: uuid.UUID
    device_id: str = Field(min_length=1, max_length=256)
    expires_in: int = Field(gt=0, le=31536000)
    refresh_expires_in: int = Field(gt=0, le=31536000)


class SaraAuth:
    def __init__(self, cfg, registry, transport=None):
        self.cfg, self.reg = cfg, registry
        self.allowed_ids = cfg.admin_identity_ids()
        self.client = httpx.Client(timeout=8, follow_redirects=False, trust_env=False, transport=transport)
        self.callback_url = cfg.validated_origin() + '/control/v1/auth/sara/callback'

    @contextmanager
    def locked(self):
        fd = os.open(self.reg.path + '.sara.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise IdentityUnavailable
                    time.sleep(0.01)
            with self.reg.connect() as db:
                yield db
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def call(self, method, path, **kwargs):
        try:
            response = self.client.request(method, self.cfg.identity_api_url.rstrip('/') + path, **kwargs)
        except httpx.HTTPError:
            raise IdentityUnavailable from None
        if response.status_code in {400, 401, 403}:
            raise IdentityRejected
        if not 200 <= response.status_code < 300:
            raise IdentityUnavailable
        return response

    def grant(self, response):
        try:
            grant = Grant.model_validate(response.json())
            if grant.client_id != self.cfg.identity_client_id:
                raise ValueError('Unexpected client')
            value = grant.model_dump(mode='json')
            value['access_expires_at'] = time.time() + grant.expires_in
            value['refresh_expires_at'] = time.time() + grant.refresh_expires_in
            return value
        except (ValueError, ValidationError):
            raise IdentityUnavailable from None

    def principal(self, grant):
        response = self.call('GET', '/auth/introspect', headers={
            'Authorization': 'Bearer ' + grant['access_token'],
            'X-Resource-Audience': self.cfg.identity_audience,
        })
        try:
            value = response.json()
            subject = str(uuid.UUID(value['id']))
            if subject not in self.allowed_ids or value.get('is_active') is not True:
                raise IdentityRejected
            return {'central_user_id': subject, 'username': str(value.get('name') or 'Administrador')[:128]}
        except (ValueError, KeyError, TypeError):
            raise IdentityUnavailable from None

    @staticmethod
    def session(db, token):
        if not token or len(token) > 256:
            return None
        return db.execute("SELECT * FROM sessions WHERE token_hash=? AND kind='admin' AND expires_at>?", (digest(token), time.time())).fetchone()

    def start(self, old_session, old_browser, device_id):
        with self.locked() as db:
            db.execute("DELETE FROM sessions WHERE kind='admin' AND expires_at<?", (time.time(),))
            old = self.session(db, old_session)
            if old:
                value = self.reg.open(old['value'])
                if value.get('provider') == 'sara' and value.get('identity_status') == 'active':
                    raise RegistryError(409, 'Cierra la sesión administrativa antes de cambiar de cuenta')
                db.execute('DELETE FROM sessions WHERE token_hash=?', (old['token_hash'],))
            db.execute('DELETE FROM sara_flows WHERE expires_at<?', (time.time(),))
            if old_browser:
                db.execute("UPDATE sara_flows SET status='cancelled',payload=NULL WHERE browser_hash=?", (digest(old_browser),))
            state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            try:
                device_id = str(uuid.UUID(device_id))
            except (ValueError, TypeError, AttributeError):
                device_id = str(uuid.uuid4())
            payload = self.reg.seal({'verifier': verifier, 'device_id': device_id})
            db.execute("INSERT INTO sara_flows VALUES(?,?,?,?,'pending',NULL)", (digest(state), digest(browser), payload, time.time() + 600))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        url = self.cfg.identity_portal_url.rstrip('/') + '/authorize?' + urlencode({
            'response_type': 'code', 'client_id': self.cfg.identity_client_id, 'redirect_uri': self.callback_url,
            'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        })
        return url, browser, device_id

    def callback(self, state, browser, code):
        with self.locked() as db:
            flow = db.execute('SELECT * FROM sara_flows WHERE state_hash=?', (digest(state),)).fetchone()
            if (not flow or flow['status'] != 'pending' or flow['expires_at'] <= time.time()
                    or not browser or not hmac.compare_digest(flow['browser_hash'], digest(browser))):
                raise RegistryError(400, 'Intento de acceso inválido o vencido')
            payload = self.reg.open(flow['payload'])
            # Consumption survives a crash or an ambiguous token response. Never blindly retry a code.
            db.execute("UPDATE sara_flows SET status='exchanging',payload=NULL WHERE state_hash=?", (digest(state),))
            db.commit()
            grant = self.grant(self.call('POST', '/oauth/token', data={
                'grant_type': 'authorization_code', 'client_id': self.cfg.identity_client_id,
                'redirect_uri': self.callback_url, 'code': code, 'code_verifier': payload['verifier'],
            }, headers={'X-Device-ID': payload['device_id'], 'X-Device-Name': 'AgentAgenda Admin'}))
            try:
                principal = self.principal(grant)
            except (IdentityRejected, IdentityUnavailable):
                try:
                    self.call('POST', '/auth/logout/refresh', json={'refresh_token': grant['refresh_token']})
                except (IdentityRejected, IdentityUnavailable):
                    pass
                raise
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            expires = min(time.time() + self.cfg.session_seconds, grant['refresh_expires_at'])
            value = {**grant, **principal, 'provider': 'sara', 'identity_status': 'active'}
            db.execute("INSERT INTO sessions VALUES(?,'admin',NULL,?,?,?)", (digest(token), self.reg.seal(value), csrf, expires))
            db.execute("UPDATE sara_flows SET status='consumed',session_hash=? WHERE state_hash=?", (digest(token), digest(state)))
            return token, max(1, int(expires - time.time()))

    def authenticate(self, token):
        with self.locked() as db:
            row = self.session(db, token)
            if not row:
                raise RegistryError(401, 'Inicia sesión con SARA ID')
            value = self.reg.open(row['value'])
            if value.get('provider') != 'sara':
                raise RegistryError(401, 'Inicia sesión con SARA ID')
            if value.get('identity_status') != 'active':
                raise RegistryError(401, 'Vuelve a iniciar sesión con SARA ID')
            try:
                if value['access_expires_at'] <= time.time() + 30:
                    value['identity_status'] = 'refreshing'
                    db.execute('UPDATE sessions SET value=? WHERE token_hash=?', (self.reg.seal(value), row['token_hash']))
                    db.commit()
                    grant = self.grant(self.call('POST', '/auth/refresh', json={'refresh_token': value['refresh_token']}))
                    if grant['session_id'] != value['session_id'] or grant['device_id'] != value['device_id']:
                        raise IdentityRejected
                    value.update(grant, identity_status='active')
                    db.execute('UPDATE sessions SET value=?,expires_at=min(expires_at,?) WHERE token_hash=?',
                               (self.reg.seal(value), grant['refresh_expires_at'], row['token_hash']))
                    db.commit()
                principal = self.principal(value)
                if principal['central_user_id'] != value['central_user_id']:
                    raise IdentityRejected
            except IdentityRejected:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (row['token_hash'],))
                db.commit()
                raise RegistryError(401, 'Sesión SARA revocada o sin acceso administrativo') from None
            # Read again after renewal; no other process can logout until this lock is released.
            latest = self.session(db, token)
            if not latest:
                raise RegistryError(401, 'Sesión vencida')
            session = dict(latest)
            session['value'] = {**value, **principal}
            return session

    def logout(self, token, browser):
        with self.locked() as db:
            row = self.session(db, token)
            targets = {row['token_hash']} if row else set()
            if browser:
                targets.update(flow[0] for flow in db.execute('SELECT session_hash FROM sara_flows WHERE browser_hash=? AND session_hash IS NOT NULL', (digest(browser),)))
                db.execute("UPDATE sara_flows SET status='cancelled',payload=NULL WHERE browser_hash=?", (digest(browser),))
            revoked = True
            for target in targets:
                session = db.execute('SELECT value FROM sessions WHERE token_hash=?', (target,)).fetchone()
                if not session:
                    continue
                value = self.reg.open(session['value'])
                db.execute('DELETE FROM sessions WHERE token_hash=?', (target,))
                db.commit()  # A network failure must never leave local authorization valid.
                if value.get('provider') == 'sara':
                    try:
                        self.call('POST', '/auth/logout/refresh', json={'refresh_token': value['refresh_token']})
                    except (IdentityRejected, IdentityUnavailable):
                        revoked = False
            return revoked

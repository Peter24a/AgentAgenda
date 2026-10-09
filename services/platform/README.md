# AgentAgenda control plane and gateway

The self-hosted FastAPI service provides metadata-only administration, activation and owner web sessions on one public hostname. Each registered space retains its own backend, database, worker and document storage. `/v1/*` is explicitly bound to the imported personal space; unknown space IDs never use this binding. Suspended/closed states block both routes. The gateway validates bearer identity against the selected backend and forwards no enrollment, app-secret or admin-cookie headers. `/privacidad` redirects to the public privacy policy; `/soporte` serves the public `support.html` file without login.

## Bootstrap

Install `requirements.txt` into a separate venv. Run commands from this directory:

```sh
python -m app.cli init-key --output /private/platform.key
python -m app.cli hash-password --output /private/admin-password.hash
```

Set `PLATFORM_KEY_FILE`, `PLATFORM_REGISTRY_PATH`, `PLATFORM_ADMIN_PASSWORD_FILE`, `PLATFORM_ADMIN_USERNAME=pedro`, `PLATFORM_PUBLIC_BASE_URL=https://agenda-api.pedroibarra.dev`, `PLATFORM_WEB_ROOT` (the deployed `apps/web/public` folder) and `PLATFORM_APK_PATH`. `PLATFORM_TRUSTED_HOSTS` must contain the actual public hostname. Keep the Fernet key and password hash outside Git with restrictive file permissions. The service refuses to start without them. Back up the registry and encryption key separately: losing the key prevents decrypting invitations, owner sessions and enrollment secrets.

Import preserved resources through the operator CLI. Enrollment keys must match each backend's separately configured internal enrollment key. The owner identity is the existing data owner, such as `default_user`, and must never be supplied by an app or browser.

```sh
python -m app.cli import-space --space-id UUID --name Personal --owner-name Pedro \
  --backend-url http://127.0.0.1:8201 --user-id default_user \
  --enrollment-key-file /private/personal-enrollment.key --legacy
python -m app.cli import-space --space-id UUID --name Walter --owner-name 'Walter Mata' \
  --backend-url http://127.0.0.1:8202 --user-id default_user \
  --enrollment-key-file /private/walter-enrollment.key
python -m app.cli create-invite UUID --purpose reconnect
uvicorn app.server:app --host 127.0.0.1 --port 8080 --workers 1 --no-proxy-headers
```

`PLATFORM_PROVISIONER` names one fixed installed executable accepting only `action UUID`. The application never accepts container names, shell fragments, targets or executable paths from public input. The helper can use `app.registry.Registry(path,key)` to configure the fixed backend target. Operations become ready only when the helper exits successfully and a target is registered. Incomplete operations resume after service restart; the helper must be idempotent. Suspend/close block entry immediately, including legacy API requests, while the helper stops backend workers. No permanent deletion endpoint is exposed.

## Frontend and API

Admin login sets `aa_admin`, scoped to `/control`, HttpOnly/Secure/SameSite=Strict. Login/me return `csrf_token`; every admin mutation requires `X-CSRF-Token`. Owner activation with `platform=web` requires the public Origin, stores backend tokens encrypted server-side and sets the separate `aa_owner` cookie. Owner session response contains metadata and a CSRF token, with no backend credentials. Owner cookie mutations require the token and reject foreign origins. Login and activation are rate limited; run one process. Native activation returns device credentials for secure device storage, with base URL `/s/UUID`. Both clients should persist a random `request_id` before activation so lost-response retries recover the same encrypted result. A different nonce or changed device metadata cannot replay a consumed invitation.

Owner web sessions renew backend tokens server-side and validate current identity before content access. `/platform/v1/devices` lists the owner's devices; `/platform/v1/activation` issues a code to add another device. Administrative APIs provide only names, states, quotas, the count of pending AI reports and operation records; they contain no agenda, conversations, report details, documents, browser owner cookies or backend tokens.

The gateway streams SSE and documents without buffering full responses or following redirects. Relative document URLs must be resolved against the current `/s/UUID` base by clients. Health only exposes readiness. Uploaded bodies are limited by `PLATFORM_MAX_REQUEST_BYTES` (100 MiB default); the provisioner supplies `STORAGE_QUOTA_BYTES` to the dedicated backend, which accounts for stored documents, active upload reservations and orphan partial files. Space detail reports actual usage and the effective quota through a protected metrics endpoint. Existing stored content is not re-encrypted by this registry: encrypted block storage and encrypted backups are deployment responsibilities.

Provisioner stdout/stderr is retained privately in an `operations` directory beside the registry, with directory mode 0700 and log mode 0600. Administrative responses contain only a generic failure message and operation ID. No helper logs are exposed through HTTP.

Cookie sessions last one day by default (`PLATFORM_SESSION_SECONDS`); invitations last one day (`PLATFORM_INVITATION_SECONDS`). The registry retains consumed activation receipts for retry for up to one day after invitation expiry. Treat codes as credentials and deliver them through a trusted channel. The operator CLI emits invitations only on explicit execution.

## Google Play review access

Create a separate space containing only synthetic demonstration data. Configure its exact UUID in `PLATFORM_REVIEW_SPACE_ID`; leave this setting empty to disable reusable review access. A review credential can be created only for that allowlisted space when it is ready and is not the legacy personal space. Never configure a customer space as the review space.

```sh
python -m app.cli create-review-code REVIEW_UUID --output /private/google-play-review-code.json
python -m app.cli revoke-review-code CREDENTIAL_UUID
```

The first command writes a new mode-0600 JSON file with `code`, `credential_id`, `space_id` and `expires_at: null`. It prints only metadata and the private export path. Creating a replacement revokes prior review credentials for that space. There is no HTTP endpoint for creating or revoking review credentials.

The code stays valid until revoked, allowing repeated reviewer installs through the ordinary activation screen. Every new `request_id` enrolls a fresh device only in the review backend. A repeated nonce returns the same encrypted activation receipt; changed device metadata returns 409. Client-supplied space IDs cannot select a different target, and client-supplied device IDs cannot overwrite an existing reviewer device. Origin checks, web HttpOnly sessions, CSRF, rate limits and space lifecycle checks remain in effect. Ordinary invitations keep their expiry and single-use behavior.

Revocation blocks both new activations and cached activation retries. It does not revoke device credentials already issued; revoke those devices normally or suspend the entire demonstration space when review access should stop. Previously returned credentials use the regular token refresh lifecycle. Start a new activation request for a new installation rather than reusing an old successful installation's request ID. Review credential hashes and encrypted activation receipts are part of the normal SQLite registry backup; keep the raw exported code private.

## Checks

```sh
python -m pytest tests -q
```

Tests use isolated sqlite registries and synthetic backend transports. They verify owner/admin separation, unknown spaces, explicit legacy suspension, enrollment retries/replay, tenant bearer validation, secret stripping, SSE/file forwarding and CSRF.

The deployed gateway listens on private port 8001, preserving the existing Cloudflare origin. The imported backends moved to 8201 and 8202; new backends receive persisted loopback ports from 8400 onward. See the Spanish [operations runbook](../../docs/MULTITENANCY_OPERATIONS.md) for deployed service paths, encrypted storage, backups and recovery.

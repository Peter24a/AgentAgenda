from pathlib import Path
from urllib.parse import urlsplit
import uuid

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATFORM_", env_file=".env", extra="ignore")
    registry_path: str = "/data/platform.sqlite3"
    key_file: str = "/run/secrets/platform_key"
    public_base_url: str = "https://agenda-api.pedroibarra.dev"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_password_file: str = ""
    provisioner: str = ""
    web_root: str = "/web"
    apk_path: str = "/downloads/agentagenda.apk"
    invitation_seconds: int = 86400
    session_seconds: int = 86400
    operation_timeout_seconds: int = 900
    max_request_bytes: int = 104857600
    trusted_hosts: str = "agenda-api.pedroibarra.dev,localhost,127.0.0.1,testserver"
    review_space_id: str = ""
    identity_enabled: bool = False
    identity_api_url: str = ""
    identity_portal_url: str = "https://auth.ici-labs.com"
    identity_client_id: str = "agentagenda-admin-web"
    identity_audience: str = "agentagenda-admin"
    identity_admin_ids: str = ""

    def admin_identity_ids(self) -> set[str]:
        ids = {str(uuid.UUID(value.strip())) for value in self.identity_admin_ids.split(",") if value.strip()}
        if self.identity_enabled:
            if not ids:
                raise ValueError("Configure explicit central UUIDs in PLATFORM_IDENTITY_ADMIN_IDS")
            for url in (self.identity_api_url, self.identity_portal_url, self.public_base_url):
                parsed = urlsplit(url)
                if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                        or parsed.path not in {"", "/"} or parsed.scheme not in {"http", "https"}
                        or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})):
                    raise ValueError("Identity endpoints require HTTPS or loopback HTTP origins")
            if not self.identity_client_id or not self.identity_audience:
                raise ValueError("Identity client and audience are required")
        return ids

    @field_validator("review_space_id")
    @classmethod
    def canonical_review_space(cls, value: str) -> str:
        return str(uuid.UUID(value)) if value else ""

    def validated_origin(self) -> str:
        parsed = urlsplit(self.public_base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise ValueError("PLATFORM_PUBLIC_BASE_URL must be an absolute origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid public origin")
        return self.public_base_url.rstrip("/")

    def encryption_key(self) -> bytes:
        path = Path(self.key_file)
        if not path.is_file():
            raise ValueError("PLATFORM_KEY_FILE is required; generate and back it up before starting")
        return path.read_bytes().strip()

    def password_hash(self) -> str:
        if self.admin_password_file:
            return Path(self.admin_password_file).read_text().strip()
        if self.admin_password_hash:
            return self.admin_password_hash
        raise ValueError("Configure PLATFORM_ADMIN_PASSWORD_FILE or PLATFORM_ADMIN_PASSWORD_HASH")

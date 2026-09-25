import os
from pydantic_settings import BaseSettings
from pydantic import SecretStr

class Settings(BaseSettings):
    app_name: str = "AgentAgenda Backend"
    environment: str = os.getenv("ENV", "production")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8001"))
    
    # Database (PostgreSQL canónico; asyncpg)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://agentagenda:agentagendapass@localhost:5432/agentagenda"
    )
    # Legacy SQLite path for backwards compatibility
    db_path: str = os.getenv("DB_PATH", "agent_agenda.db")

    # Almacenamiento privado de documentos originales
    storage_path: str = os.getenv("STORAGE_PATH", "./storage")
    max_upload_size_bytes: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(100 * 1024 * 1024)))  # 100 MB

    # LLM server config (llama-server local)
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://127.0.0.1:8080/v1")
    llm_api_key: SecretStr = SecretStr(os.getenv("LLM_API_KEY", ""))
    llm_health_url: str = os.getenv("LLM_HEALTH_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "qwen-local")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT", "90.0"))

    # Motor de OCR multimodal (GLM-OCR vía LLM Gateway en GPU)
    ocr_model: str = os.getenv("OCR_MODEL", "glm-ocr")
    ocr_timeout_seconds: float = float(os.getenv("OCR_TIMEOUT", "60.0"))
    ocr_enabled: bool = os.getenv("OCR_ENABLED", "true").lower() in ("true", "1", "yes")

    # Zonas horarias y temporalidad canónica
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "America/Mexico_City")
    
    # Seguridad, emparejamiento y tokens
    secret_key: str = os.getenv("SECRET_KEY", "agent-agenda-dev-secret-key-must-change-in-prod-123456789")
    token_expire_days: int = int(os.getenv("TOKEN_EXPIRE_DAYS", "30"))
    pairing_challenge_ttl_minutes: int = int(os.getenv("PAIRING_CHALLENGE_TTL_MINUTES", "10"))
    
    # Fallback seguro para uso personal (Opción A vs Opción B)
    # Permite acceso directo transparente solo desde red local / privada sin exponer a internet público
    allow_anonymous_fallback: bool = os.getenv("ALLOW_ANONYMOUS_FALLBACK", "false").lower() in ("true", "1", "yes")
    fallback_require_private_network: bool = os.getenv("FALLBACK_REQUIRE_PRIVATE_NETWORK", "true").lower() in ("true", "1", "yes")
    trusted_fallback_networks: str = os.getenv("TRUSTED_FALLBACK_NETWORKS", "private,loopback")
    mcp_allowed_origins: str = ""

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

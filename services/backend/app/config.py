import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AgentAgenda Backend"
    environment: str = os.getenv("ENV", "production")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8001"))
    
    # LLM server config (llama-server local)
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://127.0.0.1:8080/v1")
    llm_model: str = os.getenv("LLM_MODEL", "qwen-local")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT", "60.0"))
    
    # Database
    db_path: str = os.getenv("DB_PATH", "agent_agenda.db")
    
    # Timezone
    default_timezone: str = "America/Mexico_City"

    class Config:
        env_file = ".env"

settings = Settings()

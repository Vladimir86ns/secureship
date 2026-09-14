from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_base_url: str
    ollama_model: str = "qwen3:8b"
    frontend_origin: str = "http://localhost:5173"

    session_cookie_name: str = "secureship_session"
    session_cookie_secure: bool = False

    verification_code_ttl_seconds: int = 300
    verification_resend_cooldown_seconds: int = 30
    verification_max_attempts: int = 5

    tool_call_max_rounds: int = 4

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()

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

    # Admin login (Epic E) — Auth0, used ONLY for /admin/*. Never part of the chat identity flow.
    auth0_domain: str  # bare tenant domain, no https:// (e.g. my-tenant.us.auth0.com)
    auth0_audience: str  # the Auth0 API identifier
    auth0_admin_client_id: str  # the admin SPA; access tokens issued to any other client are refused

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()

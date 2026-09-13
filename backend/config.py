from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_base_url: str
    ollama_model: str = "qwen3:8b"
    frontend_origin: str = "http://localhost:5173"


settings = Settings()

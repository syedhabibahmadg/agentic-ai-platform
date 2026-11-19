from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Agentic AI Platform"
    app_env: str = "development"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 15
    refresh_days: int = 14
    groq_api_key: str = ""
    groq_models: str = "llama-3.3-70b-versatile"
    groq_tool_models: str = "llama-3.3-70b-versatile"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    upload_limit: int = 10 * 1024 * 1024
    context_messages: int = Field(default=20, ge=2, le=100)
    graph_recursion_limit: int = Field(default=20, ge=12)
    brave_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    reset_sender: str = ""
    public_app_url: str = "http://localhost:8080"

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def production_settings(self):
        if self.secure_cookies and (
            self.jwt_secret_key.startswith("replace-") or
            "*" in self.cors_origins or
            not self.public_app_url.startswith("https://")
        ):
            raise ValueError("Production requires a signing secret, exact CORS origins, and an HTTPS public URL")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()

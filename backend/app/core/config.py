from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://odin:odin@localhost:5432/odin"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    ai_mode: Literal["auto", "mock", "anthropic"] = "auto"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ai_timeout_seconds: float = Field(default=15, gt=0, le=60)
    analysis_lease_seconds: int = Field(default=60, ge=10, le=300)

    @model_validator(mode="after")
    def validate_configuration(self):
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        if self.analysis_lease_seconds <= self.ai_timeout_seconds + 5:
            raise ValueError("Analysis lease must exceed the AI timeout by at least 5 seconds")
        if self.ai_mode == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic mode")
        return self

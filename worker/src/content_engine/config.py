from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: SecretStr = Field(min_length=1)
    assemblyai_api_key: SecretStr = Field(min_length=1)
    claude_model_generate: str = "claude-sonnet-5-5"
    claude_model_validate: str = "claude-haiku-5-5"

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]

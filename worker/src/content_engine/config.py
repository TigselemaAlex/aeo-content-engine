"""Worker settings, read only from environment variables and `.env` files (docs/06 §9)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker configuration taken from the environment.

    Each field is read from the environment variable with the same name in
    uppercase (`anthropic_api_key` from `ANTHROPIC_API_KEY`). Values come from,
    highest priority first: the process environment, `.env` in the working
    directory (an optional `worker/.env`) and `../.env` (the single `.env` at the
    monorepo root). Both paths are relative to the working directory, so the
    worker must run from `worker/` (docs/06 §9, docs/00 "Archivo `.env`").
    Other variables in those files, such as the web's `SUPABASE_*`, are ignored.
    Every variable is listed in `.env.example` at the root.

    Attributes:
        anthropic_api_key: Claude API key (`ANTHROPIC_API_KEY`). Required, not
            empty. Lives only in the worker (docs/01 §9).
        assemblyai_api_key: AssemblyAI API key for transcription
            (`ASSEMBLYAI_API_KEY`). Required, not empty.
        claude_model_generate: Claude model id used to generate pieces
            (`CLAUDE_MODEL_GENERATE`). Defaults to `claude-sonnet-5-5`, Sonnet
            5.5 (docs/00, decision "IA de texto").
        claude_model_validate: Claude model id used to validate pieces
            (`CLAUDE_MODEL_VALIDATE`). Defaults to `claude-haiku-5-5`, Haiku 5.5
            (docs/00, decision "IA de texto").

    Raises:
        pydantic.ValidationError: When built, if an API key is missing or empty.
            The error lists every bad field.
    """

    anthropic_api_key: SecretStr = Field(min_length=1)
    assemblyai_api_key: SecretStr = Field(min_length=1)
    claude_model_generate: str = "claude-sonnet-5-5"
    claude_model_validate: str = "claude-haiku-5-5"

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return the worker settings, reading the environment only once.

    The first call builds `Settings` from the environment and `.env` files; later
    calls return that same object, so a change to `.env` needs a restart. A call
    that fails is not cached: the next one reads the environment again. The CLI
    calls it through `load_settings` in `main.py`, which turns the error into a
    "Missing or empty setting" message and exit code 1.

    Returns:
        The shared `Settings` object.

    Raises:
        pydantic.ValidationError: If `ANTHROPIC_API_KEY` or `ASSEMBLYAI_API_KEY`
            is missing or empty. It is let through on purpose so the caller can
            name the missing variables.

    Example:
        Run from `worker/` with `ANTHROPIC_API_KEY=` left empty in `../.env`,
        it raises `ValidationError` for `anthropic_api_key`. With both keys set
        and no `CLAUDE_MODEL_GENERATE`, `get_settings().claude_model_generate`
        is `"claude-sonnet-5-5"`.
    """
    return Settings()  # pyright: ignore[reportCallIssue]

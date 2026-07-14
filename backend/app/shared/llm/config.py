"""LLM provider settings, kept separate from app/core/config.py (which is the
existing auth-layer config and is not modified by this scaffold). Follows the
same pydantic-settings pattern as app/core/config.py for consistency.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-5", alias="ANTHROPIC_MODEL")
    fallback_llm_api_key: str = Field(default="", alias="FALLBACK_LLM_API_KEY")
    fallback_llm_model: str = Field(default="", alias="FALLBACK_LLM_MODEL")
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()

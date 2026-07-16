"""LLM provider settings, kept separate from app/core/config.py (which is the
existing auth-layer config and is not modified by this scaffold). Follows the
same pydantic-settings pattern as app/core/config.py for consistency.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    primary_llm_api_key: str = Field(default="", alias="PRIMARY_LLM_API_KEY")
    primary_llm_model: str = Field(default="gpt-4o", alias="PRIMARY_LLM_MODEL")
    primary_llm_base_url: str = Field(
        default="https://api.openai.com/v1", alias="PRIMARY_LLM_BASE_URL"
    )
    embedding_model: str = Field(
        default="text-embedding-3-large", alias="EMBEDDING_MODEL"
    )
    embedding_dimensions: int = Field(default=1536, alias="EMBEDDING_DIMENSIONS")
    fallback_llm_api_key: str = Field(default="", alias="FALLBACK_LLM_API_KEY")
    fallback_llm_model: str = Field(default="", alias="FALLBACK_LLM_MODEL")
    fallback_llm_base_url: str = Field(
        default="https://api.groq.com/openai/v1", alias="FALLBACK_LLM_BASE_URL"
    )
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_llm_settings() -> LLMSettings:
    return LLMSettings()

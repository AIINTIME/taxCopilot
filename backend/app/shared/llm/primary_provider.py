"""OpenAI implementation of LLMProvider — the primary text-generation provider.

This is the ONLY file in the codebase allowed to import the OpenAI SDK for
text generation. Do not import `openai` anywhere else for generation purposes.
Embeddings have their own isolated provider: shared/embeddings/openai_embedding_provider.py.
"""

import time

from openai import AsyncOpenAI

from app.core.request_timing import record_elapsed
from app.shared.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.shared.llm.config import get_llm_settings


class PrimaryLLMProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_llm_settings()
        self._model = settings.primary_llm_model
        self._client = AsyncOpenAI(
            api_key=settings.primary_llm_api_key,
            base_url=settings.primary_llm_base_url,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,  # hardcoded — never left to the caller
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        latency_ms = (time.monotonic() - start) * 1000
        # This call already times itself, so attribute the figure it produced
        # rather than wrapping a second measurement around the same await.
        record_elapsed("openai-chat", latency_ms)
        return LLMResponse(
            text=response.choices[0].message.content or "",
            model_version=response.model,
            provider_name="openai",
            latency_ms=latency_ms,
        )

"""Secondary LLM provider — same LLMProvider interface as PrimaryLLMProvider,
so router.py can fall back to it without any calling code changing.

Groq (FALLBACK_LLM_API_KEY / FALLBACK_LLM_MODEL in .env), via an
OpenAI-compatible endpoint -- Groq's API speaks the OpenAI chat-completions
protocol, so this reuses the `openai` SDK client rather than adding a new
one, pointed at FALLBACK_LLM_BASE_URL. Same "only this file imports this
provider's client" isolation as PrimaryLLMProvider, just sharing the SDK
package since the wire protocol is the same.

Per .env's own comment ("optional, leave blank to disable"), an unset
FALLBACK_LLM_API_KEY raises a clear error immediately rather than attempting
a request that would fail with a confusing auth error.
"""

import time

from openai import AsyncOpenAI

from app.core.request_timing import record_elapsed
from app.shared.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.shared.llm.config import get_llm_settings


class FallbackProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_llm_settings()
        self._model = settings.fallback_llm_model
        self._api_key = settings.fallback_llm_api_key
        self._client = (
            AsyncOpenAI(api_key=self._api_key, base_url=settings.fallback_llm_base_url)
            if self._api_key
            else None
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        if self._client is None:
            raise RuntimeError(
                "No fallback LLM configured (FALLBACK_LLM_API_KEY is blank) -- "
                "the primary provider failed and there is no secondary to try"
            )

        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,  # hardcoded — never left to the caller
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        latency_ms = (time.monotonic() - start) * 1000
        # Named distinctly from the primary: a request that fell back is worth
        # seeing in the log rather than reading as an ordinary slow chat call.
        record_elapsed("openai-chat-fallback", latency_ms)
        return LLMResponse(
            text=response.choices[0].message.content or "",
            model_version=response.model,
            provider_name="groq",
            latency_ms=latency_ms,
        )

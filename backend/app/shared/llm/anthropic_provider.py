"""Claude implementation of LLMProvider -- the PRIMARY provider.

This is the ONLY file in the entire codebase allowed to import the Anthropic
SDK directly. No other module (including services/rag/llm_client.py) may
import `anthropic` -- everything goes through shared/llm/router.py.
"""

from anthropic import AsyncAnthropic

from app.shared.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.shared.llm.config import get_llm_settings


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_llm_settings()
        self._model = settings.anthropic_model
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        # Temperature is hardcoded to 0 here regardless of the argument passed
        # in -- this rule must never depend on the caller remembering it.
        raise NotImplementedError(
            "TODO: call self._client.messages.create(model=self._model, "
            "system=system_prompt, messages=[...], temperature=0, ...) and "
            "map the response into LLMResponse(provider_name='anthropic')"
        )

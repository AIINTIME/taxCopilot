"""Provider router: tries the primary (Claude) provider, retries the fallback
provider on failure/timeout, and logs (for the audit trail) which provider
actually served each response.

This is the only shared/llm/ module that services/rag/llm_client.py is
allowed to import from.
"""

import logging

from app.shared.llm.anthropic_provider import AnthropicProvider
from app.shared.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.shared.llm.fallback_provider import FallbackProvider

logger = logging.getLogger(__name__)


class RoutedLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self._primary: LLMProvider = AnthropicProvider()
        self._fallback: LLMProvider = FallbackProvider()

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        try:
            response = await self._primary.generate(system_prompt, messages, temperature)
            logger.info("llm_router served_by=%s", response.provider_name)
            return response
        except Exception:
            logger.exception("llm_router primary_failed falling_back_to=fallback")

        response = await self._fallback.generate(system_prompt, messages, temperature)
        logger.info("llm_router served_by=%s", response.provider_name)
        return response


_provider: RoutedLLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = RoutedLLMProvider()
    return _provider

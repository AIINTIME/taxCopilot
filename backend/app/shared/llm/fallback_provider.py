"""Secondary LLM provider -- same LLMProvider interface as AnthropicProvider,
so router.py can fall back to it without any calling code changing.

Stub for now: no SDK is imported yet because the secondary provider hasn't
been chosen. When it is, only this file should import that provider's SDK
(mirroring the rule that anthropic_provider.py is the only file allowed to
import the Anthropic SDK).
"""

from app.shared.llm.base import LLMMessage, LLMProvider, LLMResponse


class FallbackProvider(LLMProvider):
    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise NotImplementedError(
            "TODO: implement the secondary LLM provider once chosen. Must "
            "hardcode temperature=0 on the underlying call, same as "
            "AnthropicProvider."
        )

"""Provider-agnostic LLM call for narrative generation. This is the ONLY file
under services/ allowed to import from shared/llm/, and it must only import
router.get_llm_provider() / base types -- never a specific provider module.
"""

from app.shared.llm.base import LLMMessage, LLMResponse
from app.shared.llm.router import get_llm_provider


async def generate_narrative(
    system_prompt: str, messages: list[LLMMessage]
) -> LLMResponse:
    return await get_llm_provider().generate(system_prompt, messages, temperature=0)

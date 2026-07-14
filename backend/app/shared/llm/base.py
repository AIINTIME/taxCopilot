"""Abstract LLMProvider interface. Every concrete provider (Claude, fallback)
implements this exact interface so callers (services/rag/llm_client.py, via
router.py) never need to know which provider actually served a request.

Temperature=0 is a hard requirement on every call and must be enforced inside
each provider's generate() implementation, not left to the caller to pass
correctly.
"""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    model_version: str
    provider_name: str
    latency_ms: float


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a response. Implementations must force temperature=0 on the
        underlying SDK call regardless of the value passed in here.
        """
        raise NotImplementedError

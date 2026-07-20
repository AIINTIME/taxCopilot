"""OpenAI Embeddings provider.

This is the ONLY file in the codebase allowed to import the OpenAI SDK for
embedding calls. Text-generation calls live in shared/llm/primary_provider.py
— both import the openai package, but both are confined to the shared/ boundary.
No file outside shared/ may import openai directly.
"""

from openai import AsyncOpenAI

from app.core.request_timing import record_span
from app.shared.llm.config import get_llm_settings


class OpenAIEmbeddingProvider:
    def __init__(self) -> None:
        settings = get_llm_settings()
        self._client = AsyncOpenAI(api_key=settings.primary_llm_api_key)
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with record_span("openai-embed"):
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=self._dimensions,
            )
        return [item.embedding for item in response.data]


_provider: OpenAIEmbeddingProvider | None = None


def get_embedding_provider() -> OpenAIEmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIEmbeddingProvider()
    return _provider

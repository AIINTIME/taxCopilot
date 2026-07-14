"""Text embedding via the configured embedding provider.
Delegates to shared/embeddings/ — no SDK imported here.
"""

from app.shared.embeddings.openai_embedding_provider import get_embedding_provider


async def embed_texts(texts: list[str]) -> list[list[float]]:
    return await get_embedding_provider().embed(texts)

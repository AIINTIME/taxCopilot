"""Pinecone vector store client.

This is the ONLY file in the codebase allowed to import the pinecone SDK.
Callers receive plain list[dict] results — no Pinecone SDK types leak out.

Namespaces:
  "statutory-kg"  — permanent statutory knowledge (the only namespace written
                    by this task; managed by statutory_kg_upsert.py)
  "user-docs"     — session-scoped user uploads (separate task, never mixed
                    with statutory-kg)
"""

from pinecone import Pinecone

from app.core.config import get_settings


class PineconeVectorClient:
    def __init__(self) -> None:
        s = get_settings()
        pc = Pinecone(api_key=s.pinecone_api_key)
        self._index = pc.Index(s.pinecone_index)

    def upsert(self, namespace: str, vectors: list[dict]) -> None:
        """Upsert vectors into a namespace.

        vectors: list of {"id": str, "values": list[float], "metadata": dict}
        """
        self._index.upsert(vectors=vectors, namespace=namespace)

    def query(
        self,
        namespace: str,
        vector: list[float],
        top_k: int,
        filter: dict | None = None,
    ) -> list[dict]:
        """Query by vector similarity. Returns plain dicts with id/score/metadata."""
        result = self._index.query(
            namespace=namespace,
            vector=vector,
            top_k=top_k,
            filter=filter or {},
            include_metadata=True,
        )
        return [
            {"id": m.id, "score": m.score, "metadata": m.metadata or {}}
            for m in result.matches
        ]


_client: PineconeVectorClient | None = None


def get_pinecone_client() -> PineconeVectorClient:
    global _client
    if _client is None:
        _client = PineconeVectorClient()
    return _client

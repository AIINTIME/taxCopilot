"""Session-scoped retriever for user-uploaded documents (26AS, sale deeds,
etc.). Deliberately separate from the permanent knowledge-graph retriever --
session documents must never be mixed into the statutory KG namespace.
"""

from app.services.rag.retriever.hybrid_retriever import RetrievedChunk


async def retrieve_session_documents(
    session_id: str, query: str, top_k: int = 10
) -> list[RetrievedChunk]:
    raise NotImplementedError(
        "TODO: retrieve from a session-scoped namespace keyed by session_id, "
        "never joined with the permanent KnowledgeGraphProvision namespace"
    )

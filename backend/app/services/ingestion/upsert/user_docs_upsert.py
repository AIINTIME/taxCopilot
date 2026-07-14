"""Upserts a parsed user document into the session-scoped namespace.
Explicitly never mixed with the permanent KnowledgeGraphProvision namespace
-- see services/rag/external_research/session_documents.py.
"""


async def upsert_session_document(session_id: str, filename: str, content: str) -> str:
    raise NotImplementedError(
        "TODO: store `content` in a session-scoped namespace keyed by "
        "session_id and return the new document's id"
    )

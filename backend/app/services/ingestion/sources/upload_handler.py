"""Handles user document uploads (26AS, sale deeds, etc.) destined for the
session-scoped namespace -- see services/rag/external_research/session_documents.py
and services/ingestion/upsert/user_docs_upsert.py.
"""


async def handle_upload(session_id: str, filename: str, content: bytes) -> str:
    raise NotImplementedError(
        "TODO: validate, store, and hand off `content` for parsing/embedding/"
        "upsert into the session-scoped namespace for session_id"
    )

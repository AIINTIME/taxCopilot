"""POST /api/v1/{domain}/query -- the single entrypoint into the AI/RAG +
computation architecture. Reuses the existing auth dependency
(app.api.auth.get_current_user) for request attribution; delegates all actual
work to the LangGraph query graph in orchestration/.
"""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.orchestration.graphs.query_graph import run_query_graph
from app.shared.schemas.citation import Citation

router = APIRouter(prefix="/api/v1", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    as_of_date: date | None = None
    session_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    computation_trace: dict | None = None
    gate_status: str
    as_of_date: date
    audit_log_id: str


@router.post("/{domain}/query", response_model=QueryResponse)
async def query(domain: str, payload: QueryRequest, user=Depends(get_current_user)):
    return await run_query_graph(domain=domain, request=payload, user_id=user.id)

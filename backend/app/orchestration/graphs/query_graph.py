"""The actual LangGraph implementation wiring the full query flow:

    intent classify -> temporal resolve
        -> [document attached + rule known (explicit request, or inferred
            from the query text)] -> document_extraction -> computation
        -> [computation_request given] -> computation
        -> [free-text query, rule inferred] -> computation
        -> [retrieval-intent, or no rule known] -> retrieval -> narrate -> evidence_gate
    computation -> [computed] -> ground_truth_check -> computation_citations -> assemble_response -> audit_log
    computation -> [rule not inferred at all] -> computation_fallback -> retrieval
    computation -> [rule known but fields missing] -> assemble_response -> audit_log
    evidence_gate -> assemble_response -> audit_log

A document attached to a retrieval-intent query (or one with no computation
rule identified, e.g. Notices) is not discarded -- retrieval prepends it as
an extra citable context chunk ahead of narration, so general/explanatory
questions about an attached document are answered grounded in it, through
the same evidence-gate verification already used for the statutory
knowledge base (see _uploaded_document_chunk).

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.nodes.computation_citations import resolve_computation_citations
from app.orchestration.state import QueryGraphState
from app.services.computation.computation_trace import ComputationTrace
from app.services.computation.engine import MissingComputationInputError, compute
from app.services.query.input_extractor import clarification_questions
from app.services.query.intent_classifier_types import Intent
from app.services.query.llm_query_understanding import (
    QueryUnderstandingError,
    classify_and_extract,
    extract_personal_regime_fields_from_document,
)
from app.services.query.temporal_resolver import resolve_as_of
from app.services.rag.document_lookup import resolve_document_names
from app.services.rag.evidence_gate import (
    INSUFFICIENT_SOURCES_MESSAGE,
    extract_citations,
    strip_unverified_claims,
    verify_citations,
)
from app.services.rag.extraction.document_extraction import (
    extract_fields_for_rule,
    verified_fields_to_computation_inputs,
)
from app.services.rag.ground_truth_gate import (
    derive_ground_truth_keywords,
    verify_computation_ground_truth,
)
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts import CITATION_MANDATE, SYSTEM_PROMPT_TEMPLATE, build_context_block
from app.services.rag.retriever.graph_store import lookup_rate_rule
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk, hybrid_search
from app.shared.llm.base import LLMMessage

logger = logging.getLogger(__name__)


def _known_rule_name(state: QueryGraphState) -> str | None:
    """The rule to act on, using the same precedence _computation_node
    already applies: an explicit computation_request wins, otherwise fall
    back to whatever classify_intent inferred from the query text (may be
    None -- the LLM was not confident enough to name one)."""
    computation_request = state.get("computation_request")
    if computation_request is not None:
        return computation_request["rule_name"]
    return state.get("rule_name")


async def _classify_intent_node(state: QueryGraphState) -> dict:
    # The LLM is the sole classifier: one call decides intent, identifies the
    # computation rule (if any), and -- for personal_regime_comparison --
    # extracts evidence-verified, re-parsed field values (see
    # llm_query_understanding.py for why extracted numbers are never taken on
    # the LLM's own word even though routing is). There is no deterministic
    # fallback here by design -- a failure is re-raised as
    # QueryUnderstandingError and propagates out of run_query_graph; the API
    # layer (services/query/routes.py) turns that into a clear, retry-able
    # error rather than silently degrading to a weaker classifier.
    try:
        understanding = await classify_and_extract(state["query"])
    except Exception as exc:
        logger.exception("[FLOW] classify_intent: LLM query understanding FAILED")
        raise QueryUnderstandingError(
            "Could not understand the query -- the classification LLM call failed"
        ) from exc

    logger.info(
        "[FLOW] classify_intent: query=%r -> intent=%s rule_name=%s",
        state["query"], understanding.intent.value, understanding.rule_name,
    )
    result: dict[str, Any] = {
        "intent": understanding.intent,
        "rule_name": understanding.rule_name,
    }
    if understanding.extracted is not None:
        result["parsed_query_inputs"] = understanding.extracted.to_rule_inputs()
        result["parsed_query_missing_fields"] = list(understanding.extracted.missing)
        result["assumptions"] = list(understanding.extracted.assumptions)
    return result


async def _resolve_temporal_node(state: QueryGraphState) -> dict:
    as_of = resolve_as_of(state["query"], state.get("explicit_as_of_date"))
    logger.info(
        "[FLOW] resolve_temporal: as_of_date=%s regime=%s capital_gains_period=%s",
        as_of.as_of_date, as_of.regime.value, as_of.capital_gains_period.value,
    )
    return {"as_of": as_of}


async def _document_extraction_node(state: QueryGraphState) -> dict:
    # _route_after_temporal only sends a query here once a rule is already
    # known (explicit computation_request, or classify_intent inferred one
    # from the query text) -- see _known_rule_name for the shared precedence.
    rule_name = _known_rule_name(state)
    document_text = state["uploaded_document_text"]

    logger.info(
        "[FLOW] document_extraction: rule_name=%s -- calling OpenAI LLM to "
        "extract fields from uploaded document", rule_name,
    )

    if rule_name == "personal_regime_comparison":
        # Reuses the same evidence-span + re-derived-amount extraction
        # llm_query_understanding.py's classify_and_extract already uses for
        # the query-text path, pointed at the document instead -- one
        # number-provenance guarantee, not two.
        extracted_inputs = await extract_personal_regime_fields_from_document(document_text)
        inputs = extracted_inputs.to_rule_inputs()
        missing = list(extracted_inputs.missing)
        assumptions = list(state.get("assumptions") or []) + list(extracted_inputs.assumptions)
    else:
        extracted = await extract_fields_for_rule(rule_name, document_text)
        inputs, missing = verified_fields_to_computation_inputs(rule_name, extracted)
        assumptions = list(state.get("assumptions") or [])

    logger.info(
        "[FLOW] document_extraction: verified_fields=%s missing_fields=%s",
        list(inputs), missing,
    )

    result: dict[str, Any] = {
        "extracted_inputs": inputs,
        "extraction_missing_fields": missing,
        "assumptions": assumptions,
    }
    # Only auto-build a computation_request when every required field was
    # verified, and only if the caller didn't already supply one explicitly.
    if not missing and state.get("computation_request") is None:
        result["computation_request"] = {
            "rule_name": rule_name,
            "inputs": inputs,
        }
    return result


async def _computation_node(state: QueryGraphState) -> dict:
    # Bound here, not just in the personal_regime_comparison branch below --
    # a computation_request built by _document_extraction_node for
    # personal_regime_comparison reaches the `if computation_request is not
    # None` branch, which never touched this variable before, and the
    # `if rule_name == "personal_regime_comparison": result["assumptions"]`
    # line further down needs it regardless of which branch ran.
    assumptions = list(state.get("assumptions") or [])
    computation_request = state.get("computation_request")
    if computation_request is not None:
        rule_name = computation_request["rule_name"]
        inputs = computation_request["inputs"]
        logger.info(
            "[FLOW] computation: explicit computation_request rule_name=%s inputs=%s",
            rule_name, inputs,
        )
    else:
        # classify_intent's LLM call always ran and succeeded by the time this
        # node is reached -- a failure there raises QueryUnderstandingError and
        # aborts the graph before _computation_node ever executes (see
        # _classify_intent_node). So state["rule_name"] is always present here;
        # None is a legitimate value meaning the LLM could not confidently
        # identify a computation rule for this query.
        rule_name = state["rule_name"]
        if rule_name is None:
            logger.info(
                "[FLOW] computation: no rule_name inferred from query -- falling back to retrieval"
            )
            return {
                "computation_result": {
                    "status": "missing_data",
                    "missing_fields": [
                        "which computation you want -- mention MAT, AMT, regime "
                        "comparison, depreciation, or capital gains explicitly"
                    ],
                }
            }

        if rule_name == "personal_regime_comparison":
            # Unlike the other inferred rules (which expect the caller to
            # supply `computation_inputs` directly), personal-tax queries are
            # parsed straight out of the query text by classify_intent's LLM
            # call -- there is no form/UI asking for gross_income/deductions
            # the way an explicit computation_request would. See
            # llm_query_understanding.py for the evidence-span verification
            # and re-parsing that makes these numbers trustworthy.
            inputs = state.get("parsed_query_inputs") or {}
            missing = state.get("parsed_query_missing_fields") or []
            logger.info(
                "[FLOW] computation: personal_regime_comparison using LLM-parsed "
                "inputs=%s missing=%s",
                inputs, missing,
            )

            if missing:
                questions = clarification_questions(missing)
                return {
                    "computation_result": {
                        "status": "missing_data",
                        "rule_name": rule_name,
                        "missing_fields": missing,
                        "clarification": "\n".join(
                            ["I need one more detail before I can compute this:", *questions]
                        ),
                    },
                    "assumptions": assumptions,
                }
        else:
            inputs = state.get("computation_inputs") or {}
            assumptions = []
        logger.info(
            "[FLOW] computation: rule_name=%s inferred from query text, inputs=%s",
            rule_name, inputs,
        )

    try:
        trace = compute(rule_name, inputs, state["as_of"])
    except MissingComputationInputError as exc:
        logger.warning(
            "[FLOW] computation: missing required fields for rule_name=%s missing=%s",
            rule_name, exc.missing_fields,
        )
        return {
            "computation_result": {
                "status": "missing_data",
                "rule_name": rule_name,
                "missing_fields": exc.missing_fields,
            }
        }
    except ValueError as exc:
        # A rule function's own domain-specific rejection (e.g.
        # capital_gains.compute_capital_gains raising when CII indexation
        # figures are needed but not among CapitalGainsInput's declared
        # fields, so document extraction/computation_inputs can never
        # supply them) -- an honest "here's what's missing and why", never
        # an unhandled 500, same as MissingComputationInputError above.
        logger.warning(
            "[FLOW] computation: rule_name=%s rejected its inputs: %s", rule_name, exc,
        )
        return {
            "computation_result": {
                "status": "missing_data",
                "rule_name": rule_name,
                "missing_fields": [],
                "clarification": str(exc),
            }
        }

    logger.info("[FLOW] computation: result outputs=%s", trace.outputs)
    result: dict[str, Any] = {
        "computation_result": {"status": "computed", "trace": trace.model_dump(mode="json")}
    }
    if rule_name == "personal_regime_comparison":
        result["assumptions"] = assumptions
    return result


async def _ground_truth_check_node(state: QueryGraphState) -> dict:
    trace = ComputationTrace.model_validate(state["computation_result"]["trace"])
    keywords = derive_ground_truth_keywords(trace.rule_name, trace.outputs)
    logger.info("[FLOW] ground_truth_check: derived keywords=%s", keywords)

    # The ground-truth check is a cross-check, not a dependency the response
    # can't exist without -- the computation result is already final and
    # correct on its own. A Neo4j/vector-store outage should degrade to "no
    # ground truth available" (same as an empty/unpopulated store), never
    # take down a response the engine already computed correctly.
    try:
        logger.info("[FLOW] ground_truth_check: hitting Neo4j (graph_store.lookup_rate_rule)")
        graph_rules = await lookup_rate_rule(keywords) if keywords else []
        logger.info("[FLOW] ground_truth_check: Neo4j returned %d matching rule(s)", len(graph_rules))
    except Exception:
        logger.exception("[FLOW] ground_truth_check: Neo4j lookup FAILED, degrading to no rules")
        graph_rules = []

    try:
        logger.info("[FLOW] ground_truth_check: hitting Pinecone/Neo4j (hybrid_search)")
        chunks = await hybrid_search(state["query"], state["as_of"])
        logger.info("[FLOW] ground_truth_check: hybrid_search returned %d chunk(s)", len(chunks))
    except Exception:
        logger.exception("[FLOW] ground_truth_check: hybrid_search FAILED, degrading to no chunks")
        chunks = []

    check = verify_computation_ground_truth(trace, chunks, graph_rules)
    logger.info(
        "[FLOW] ground_truth_check: verified=%s mismatches=%d",
        check.verified, len(check.mismatches),
    )

    return {
        "graph_rules": graph_rules,
        "retrieved_chunks": [c.model_dump() for c in chunks],
        "ground_truth_check": check.model_dump(),
    }


# Keeps the synthetic chunk's content bounded so one large attachment can't
# blow the narration prompt's context budget. No internal chunking/semantic
# search over the user's own document in this pass -- the whole (capped)
# text becomes a single citable context block, which is fine for a typical
# single-document attachment.
_MAX_UPLOADED_DOCUMENT_CHARS = 6000


def _uploaded_document_chunk(document_text: str) -> dict:
    """A synthetic RetrievedChunk-shaped dict for the user's own uploaded
    document, so it flows through the exact same numbered [N] citation and
    evidence-gate verification machinery already used for statutory KG
    chunks -- clearly labeled (section_reference) as distinct from the
    statutory knowledge base rather than conflated with it."""
    return {
        "chunk_id": "uploaded-document",
        "source_id": "uploaded-document",
        "document_id": None,
        "content": document_text[:_MAX_UPLOADED_DOCUMENT_CHARS],
        "section_reference": "Your uploaded document",
        "score": 1.0,
    }


async def _retrieval_node(state: QueryGraphState) -> dict:
    logger.info("[FLOW] retrieval: hitting Pinecone/Neo4j (hybrid_search)")
    chunks = await hybrid_search(state["query"], state["as_of"])
    logger.info("[FLOW] retrieval: hybrid_search returned %d chunk(s)", len(chunks))

    chunk_dicts = [c.model_dump() for c in chunks]
    uploaded_text = state.get("uploaded_document_text")
    if uploaded_text:
        logger.info("[FLOW] retrieval: prepending uploaded document as citable context")
        chunk_dicts = [_uploaded_document_chunk(uploaded_text), *chunk_dicts]

    return {"retrieved_chunks": chunk_dicts}


async def _clear_computation_fallback_node(state: QueryGraphState) -> dict:
    # Graph state is cumulative -- without this, a query that fell through
    # from computation to retrieval would still carry the earlier
    # "missing_data" computation_result, and assemble_response (which checks
    # computation_result first, unconditionally) would return the static
    # dead-end message instead of the real RAG answer this fallback exists
    # to produce.
    return {"computation_result": None}


async def _narrate_node(state: QueryGraphState) -> dict:
    context = build_context_block(state["retrieved_chunks"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context) + "\n\n" + CITATION_MANDATE

    logger.info(
        "[FLOW] narrate: hitting OpenAI LLM (services.rag.llm_client.generate_narrative) "
        "with %d chunk(s) of context", len(state["retrieved_chunks"]),
    )
    response = await generate_narrative(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=state["query"])],
    )
    logger.info(
        "[FLOW] narrate: LLM response received, provider=%s model=%s",
        response.provider_name, response.model_version,
    )
    return {"llm_response": response.model_dump()}


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    raw_text = llm_response.get("text", "")
    retrieved_chunks = [RetrievedChunk(**c) for c in state.get("retrieved_chunks", [])]

    if raw_text.strip() == INSUFFICIENT_SOURCES_MESSAGE:
        logger.info("[FLOW] evidence_gate: LLM reported insufficient sources")
        return {
            "gated_citations": [],
            "gate_status": "VERIFIED",
            "llm_response": {**llm_response, "text": raw_text},
        }

    extracted = extract_citations(raw_text, retrieved_chunks)
    gated_citations, gate_status = verify_citations(extracted, retrieved_chunks)
    gated_citations = await resolve_document_names(gated_citations)
    final_text = strip_unverified_claims(raw_text, gated_citations)
    logger.info(
        "[FLOW] evidence_gate: %d citation(s) proposed, gate_status=%s",
        len(extracted), gate_status,
    )

    return {
        "gated_citations": gated_citations,
        "gate_status": gate_status,
        "llm_response": {**llm_response, "text": final_text},
    }


def _route_after_temporal(state: QueryGraphState) -> str:
    # Only force structured-field extraction once a rule is actually known
    # (explicit computation_request, or classify_intent inferred one from
    # the query text) -- otherwise a general/explanatory question about an
    # attached document (or a Notices query, which has no computation rules
    # at all) would be wrongly forced through capital-gains-shaped field
    # extraction. Those fall through to retrieval below instead, where
    # _retrieval_node injects the document as citable narration context.
    if state.get("uploaded_document_text") and _known_rule_name(state) is not None:
        logger.info(
            "[FLOW] route_after_temporal: document attached + rule_name=%s known "
            "-> document_extraction -> computation", _known_rule_name(state),
        )
        return "document_extraction"
    if state.get("computation_request") is not None:
        logger.info("[FLOW] route_after_temporal: computation_request given -> computation")
        return "computation"
    if state["intent"] == Intent.COMPUTATION:
        logger.info(
            "[FLOW] route_after_temporal: intent=COMPUTATION -> computation "
            "(rule_name will be inferred from the query text)"
        )
        return "computation"
    # TODO: Intent.BOTH should traverse both branches; for now it is routed
    # through retrieval, same as Intent.RETRIEVAL, pending a fan-out design.
    logger.info("[FLOW] route_after_temporal: -> retrieval -> narrate -> evidence_gate")
    return "retrieval"


def _route_after_computation(state: QueryGraphState) -> str:
    """A query that reaches the computation node but doesn't match one of the
    known rule names (classify_intent's LLM call returned rule_name=None)
    isn't actually a dead end -- it just means routing guessed COMPUTATION for
    a query the deterministic engine has no rule for. Fall through to a real
    RAG search
    instead of stranding the user with a static "mention MAT/AMT/..."
    message; that message is only appropriate once we've also failed to find
    anything relevant in the vector DB.

    A query where the rule WAS identified but specific numeric inputs are
    missing (MissingComputationInputError, or an explicit computation_request
    that's simply incomplete) is a genuinely different, actionable case --
    the system knows exactly what's needed, it just needs numbers a human
    must supply -- so that one goes straight to assemble_response rather than
    being treated as a routing miss.

    A rule that DID compute successfully still needs the ground-truth
    cross-check against the statutory graph before the response is final."""
    result = state.get("computation_result") or {}
    if result.get("status") == "missing_data" and "rule_name" not in result:
        return "computation_fallback"
    if result.get("status") == "computed":
        return "ground_truth_check"
    return "assemble_response"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("document_extraction", _document_extraction_node)
    graph.add_node("computation", _computation_node)
    graph.add_node("computation_fallback", _clear_computation_fallback_node)
    graph.add_node("ground_truth_check", _ground_truth_check_node)
    graph.add_node("computation_citations", resolve_computation_citations)
    graph.add_node("retrieval", _retrieval_node)
    graph.add_node("narrate", _narrate_node)
    graph.add_node("evidence_gate", _evidence_gate_node)
    graph.add_node("assemble_response", assemble_response)
    graph.add_node("audit_log", write_audit_log)

    graph.add_edge(START, "classify_intent")
    graph.add_edge("classify_intent", "resolve_temporal")
    graph.add_conditional_edges(
        "resolve_temporal",
        _route_after_temporal,
        {
            "document_extraction": "document_extraction",
            "computation": "computation",
            "retrieval": "retrieval",
        },
    )
    graph.add_edge("document_extraction", "computation")
    graph.add_conditional_edges(
        "computation",
        _route_after_computation,
        {
            "computation_fallback": "computation_fallback",
            "ground_truth_check": "ground_truth_check",
            "assemble_response": "assemble_response",
        },
    )
    graph.add_edge("computation_fallback", "retrieval")
    graph.add_edge("ground_truth_check", "computation_citations")
    graph.add_edge("computation_citations", "assemble_response")
    graph.add_edge("retrieval", "narrate")
    graph.add_edge("narrate", "evidence_gate")
    graph.add_edge("evidence_gate", "assemble_response")
    graph.add_edge("assemble_response", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()


# Built once at import time -- building/compiling the graph only wires node
# names and edges together, it does not invoke any node body, so a bad
# runtime path only ever surfaces when a query actually runs.
_compiled_graph = build_query_graph()


async def run_query_graph(domain: str, request: Any, user_id: str) -> dict:
    computation_request = getattr(request, "computation_request", None)
    if computation_request is not None and hasattr(computation_request, "model_dump"):
        computation_request = computation_request.model_dump()

    logger.info(
        "[FLOW] run_query_graph: ENTRY domain=%s query=%r has_computation_request=%s has_uploaded_document=%s",
        domain, request.query, computation_request is not None,
        bool(getattr(request, "uploaded_document_text", None)),
    )

    initial_state: QueryGraphState = {
        "query": request.query,
        "domain": domain,
        "user_id": user_id,
        "session_id": getattr(request, "session_id", None),
        "explicit_as_of_date": getattr(request, "as_of_date", None),
        "computation_request": computation_request,
        "uploaded_document_text": getattr(request, "uploaded_document_text", None),
        "computation_inputs": getattr(request, "computation_inputs", None),
    }
    final_state = await _compiled_graph.ainvoke(initial_state)
    logger.info(
        "[FLOW] run_query_graph: EXIT gate_status=%s audit_log_id=%s",
        final_state["final_response"].get("gate_status"),
        final_state["final_response"].get("audit_log_id"),
    )
    return final_state["final_response"]

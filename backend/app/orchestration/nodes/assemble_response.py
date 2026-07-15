"""Merges the computation trace (if any) + gated narrative + verified
citations into the final response object returned to the API layer.

The division of labour this enforces: the LLM explains and labels, the
computation engine supplies every number. Where both ran, the narrative is
prose and `computation_trace` is truth -- assemble_response never lets a
narrated figure overwrite a computed one, because they are not merged at all.
"""

from app.orchestration.state import QueryGraphState


def _fallback_answer(state: QueryGraphState) -> str:
    """Answer text when no LLM narration ran (pure computation, or clarification)."""
    if state.get("clarification"):
        return state["clarification"]

    outputs = (state.get("computation_trace") or {}).get("outputs") or {}
    if not outputs:
        return "No answer could be produced for this query."

    recommended = outputs.get("recommended_regime")
    new_tax = outputs.get("new_regime_tax")
    old_tax = outputs.get("old_regime_tax")

    if recommended is None or new_tax is None or old_tax is None:
        return "Computation completed. See the computation trace for details."

    payable = min(new_tax, old_tax) if recommended == "either" else (
        new_tax if recommended == "new" else old_tax
    )

    lines = [
        f"Estimated tax payable: Rs {payable:,.0f}"
        + (
            " (identical under both regimes)"
            if recommended == "either"
            else f" under the {recommended} regime"
        ),
        f"Old regime: Rs {old_tax:,.0f}    New regime: Rs {new_tax:,.0f}",
    ]

    breakeven = outputs.get("breakeven_deductions")
    if breakeven:
        lines.append(
            f"The old regime only becomes better above roughly "
            f"Rs {breakeven:,.0f} of total deductions."
        )

    lines.extend(outputs.get("deciding_factors") or [])

    for assumption in state.get("assumptions") or []:
        lines.append(f"Assumption: {assumption}")

    return "\n".join(lines)


async def assemble_response(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    answer = llm_response.get("answer") or _fallback_answer(state)

    return {
        "final_response": {
            "answer": answer,
            "citations": state.get("gated_citations") or [],
            "computation_trace": state.get("computation_trace"),
            # Sections the trace cited that the rule graph could not resolve.
            # Kept visible: a computation is VERIFIED because its numbers come
            # from pure functions, not because anything was cited, and the
            # reader deserves to know which claims currently lack a source.
            "uncited_sections": state.get("uncited_sections") or [],
            "assumptions": state.get("assumptions") or [],
            "clarification_needed": bool(state.get("clarification")),
            "gate_status": state.get("gate_status") or "VERIFIED",
            "as_of_date": state["as_of"].as_of_date,
        }
    }

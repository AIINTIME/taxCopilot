"""Merges the computation trace (if any) + gated narrative + verified
citations into the final response object returned to the API layer.

The division of labour this enforces: the LLM explains and labels, the
computation engine supplies every number. Where both ran, the narrative is
prose and `computation_trace` is truth -- assemble_response never lets a
narrated figure overwrite a computed one, because they are not merged at all.
"""

from app.orchestration.state import QueryGraphState
from app.services.rag.text_summary import extractive_summary


def _gate_status_for_computation(ground_truth_check: dict | None) -> str:
    if ground_truth_check is None:
        return "VERIFIED"
    if ground_truth_check.get("mismatches"):
        return "FLAGGED"
    if ground_truth_check.get("verified"):
        return "VERIFIED"
    # No graph rule matched this asset class yet (e.g. not ingested) -- a
    # distinct state from either "confirmed correct" or "confirmed wrong".
    return "PARTIAL"


def _personal_regime_answer(outputs: dict, assumptions: list[str]) -> str:
    """Human-readable narrative for personal_regime_comparison's outputs.

    Its key:value pairs (old_regime_tax, new_regime_tax, breakeven_deductions,
    deciding_factors, ...) read badly through the generic joiner every other
    rule uses below, so this rule gets a dedicated renderer.
    """
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

    for assumption in assumptions:
        lines.append(f"Assumption: {assumption}")

    return "\n".join(lines)


async def assemble_response(state: QueryGraphState) -> dict:
    as_of_date = state["as_of"].as_of_date
    computation_result = state.get("computation_result")

    if computation_result is not None:
        if computation_result.get("status") == "missing_data":
            clarification = computation_result.get("clarification")
            if clarification:
                answer = clarification
            else:
                missing = ", ".join(computation_result.get("missing_fields", []))
                answer = (
                    f"This computation requires figures that weren't provided: {missing}. "
                    "Please supply these values — no assumption or default has been used "
                    "for a missing figure."
                )
            final_response = {
                "answer": answer,
                "citations": [],
                "computation_trace": None,
                "ground_truth_check": None,
                "uncited_sections": [],
                "assumptions": state.get("assumptions") or [],
                "clarification_needed": bool(clarification),
                "gate_status": "FLAGGED",
                "as_of_date": as_of_date,
            }
        else:
            trace = computation_result["trace"]
            ground_truth_check = state.get("ground_truth_check")
            outputs = trace.get("outputs", {})
            assumptions = state.get("assumptions") or []

            if trace.get("rule_name") == "personal_regime_comparison":
                answer = _personal_regime_answer(outputs, assumptions)
            else:
                answer = "; ".join(f"{key}: {value}" for key, value in outputs.items())

            final_response = {
                "answer": answer,
                "citations": state.get("gated_citations") or [],
                "computation_trace": trace,
                "ground_truth_check": ground_truth_check,
                "uncited_sections": state.get("uncited_sections") or [],
                "assumptions": assumptions,
                "clarification_needed": False,
                "gate_status": _gate_status_for_computation(ground_truth_check),
                "as_of_date": as_of_date,
            }
    else:
        llm_response = state.get("llm_response") or {}
        final_response = {
            "answer": llm_response.get("text", ""),
            "citations": state.get("gated_citations", []),
            "computation_trace": None,
            "ground_truth_check": None,
            "uncited_sections": [],
            "assumptions": [],
            "clarification_needed": False,
            "gate_status": state.get("gate_status", "FLAGGED"),
            "as_of_date": as_of_date,
        }

    final_response["summary"] = extractive_summary(final_response["answer"])
    return {"final_response": final_response}

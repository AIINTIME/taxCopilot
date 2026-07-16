"""Merges the computation trace (if any) + gated narrative + verified
citations into the final response object returned to the API layer.
"""

from app.orchestration.state import QueryGraphState
from app.services.rag.text_summary import extractive_summary


async def assemble_response(state: QueryGraphState) -> dict:
    as_of_date = state["as_of"].as_of_date
    computation_result = state.get("computation_result")

    if computation_result is not None:
        if computation_result.get("status") == "missing_data":
            missing = ", ".join(computation_result.get("missing_fields", []))
            final_response = {
                "answer": (
                    f"This computation requires figures that weren't provided: {missing}. "
                    "Please supply these values — no assumption or default has been used "
                    "for a missing figure."
                ),
                "citations": [],
                "computation_trace": None,
                "gate_status": "FLAGGED",
                "as_of_date": as_of_date,
            }
        else:
            trace = computation_result["trace"]
            final_response = {
                "answer": f"Computed via {trace['rule_name']} — see the computation trace for full detail.",
                "citations": [],
                "computation_trace": trace,
                "gate_status": "VERIFIED",
                "as_of_date": as_of_date,
            }
    else:
        llm_response = state.get("llm_response") or {}
        final_response = {
            "answer": llm_response.get("text", ""),
            "citations": state.get("gated_citations", []),
            "computation_trace": None,
            "gate_status": state.get("gate_status", "FLAGGED"),
            "as_of_date": as_of_date,
        }

    final_response["summary"] = extractive_summary(final_response["answer"])
    return {"final_response": final_response}

"""Merges the computation trace (if any) + gated narrative + verified
citations into the final response object returned to the API layer.
"""

import re

from app.orchestration.state import QueryGraphState

# The narration prompt (services/rag/prompts/narration_prompts.py) asks the
# LLM to append a machine-readable "CITATIONS: [...]" block after its answer
# -- that block is for _evidence_gate_node to parse, not for the end user to
# see, so it's stripped from the displayed answer here rather than left
# leaking into the response text.
_CITATIONS_BLOCK_PATTERN = re.compile(r"\s*CITATIONS:\s*\[.*\]\s*$", re.DOTALL)


def _strip_citations_block(text: str) -> str:
    return _CITATIONS_BLOCK_PATTERN.sub("", text).strip()


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


async def assemble_response(state: QueryGraphState) -> dict:
    computation_result = state.get("computation_result")
    llm_response = state.get("llm_response")
    ground_truth_check = state.get("ground_truth_check")

    if computation_result is not None:
        outputs = computation_result.get("outputs", {})
        answer = "; ".join(f"{key}: {value}" for key, value in outputs.items())
        gate_status = _gate_status_for_computation(ground_truth_check)
    else:
        answer = _strip_citations_block((llm_response or {}).get("text", ""))
        gate_status = state.get("gate_status", "VERIFIED")

    final_response = {
        "answer": answer,
        "citations": state.get("gated_citations", []),
        "computation_trace": computation_result,
        "ground_truth_check": ground_truth_check,
        "gate_status": gate_status,
        "as_of_date": state["as_of"].as_of_date,
    }
    return {"final_response": final_response}

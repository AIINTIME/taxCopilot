"""Merges the computation trace (if any) + gated narrative + verified
citations into the final response object returned to the API layer.
"""

from app.orchestration.state import QueryGraphState


async def assemble_response(state: QueryGraphState) -> dict:
    raise NotImplementedError(
        "TODO: build state['final_response'] from state['computation_result'], "
        "state['llm_response'], state['gated_citations'], and state['gate_status']"
    )

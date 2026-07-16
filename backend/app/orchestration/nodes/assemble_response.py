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


def _not_seeded_answer(assessment_year: str) -> str:
    """The RatesNotSeededError contract, at the response layer: say the year is
    not available rather than answering from an adjacent one. A rate that is
    quietly a year out is worse than a refusal, because it looks right.
    """
    return (
        f"Rates for AY {assessment_year} are not available. Only the assessment "
        "years seeded into the rate tables from the Income Tax Department's "
        "published rates can be answered, and this one is not among them."
    )


def _rate_card_answer(card: dict) -> str:
    if not card.get("available"):
        return _not_seeded_answer(card["assessment_year"])

    lines = [f"Income tax slab rates for AY {card['assessment_year']}:"]
    for regime in card["regimes"]:
        lines.append(f"\n{regime['regime'].title()} regime ({regime['slab_section']}):")
        lines.extend(f"  {band['range']}: {band['rate']}" for band in regime["bands"])
        lines.append(
            f"  Standard deduction: Rs {regime['standard_deduction']:,.0f}. "
            f"Sec 87A rebate: up to Rs {regime['rebate_87a_max']:,.0f} where total "
            f"income does not exceed Rs {regime['rebate_87a_income_limit']:,.0f}. "
            f"Cess: {regime['cess_rate']:.0%}."
        )
        lines.append(f"  Source: {regime['source_reference']}")
    return "\n".join(lines)


def _deduction_card_answer(card: dict) -> str:
    if not card.get("available"):
        return _not_seeded_answer(card["assessment_year"])

    lines = [f"For AY {card['assessment_year']}:"]
    for entry in card["entries"]:
        line = f"  {entry['item']}: {entry['limit']}"
        if entry.get("note"):
            line += f" — {entry['note']}"
        lines.append(line)
        if entry.get("source_reference"):
            lines.append(f"    Source: {entry['source_reference']}")
    return "\n".join(lines)


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
    rate_card = state.get("rate_card")
    deduction_card = state.get("deduction_card")
    scope_decline = state.get("scope_decline")

    if scope_decline is not None:
        # A refusal asserts no tax fact, so there is nothing to verify and
        # nothing to flag -- VERIFIED with no citations, as a clarification is.
        # Saying "consult a professional to review this" about a sentence that
        # declines to answer would be noise.
        final_response = {
            "answer": scope_decline["answer"],
            "citations": [],
            "computation_trace": None,
            "ground_truth_check": None,
            "uncited_sections": [],
            "assumptions": [],
            "clarification_needed": False,
            "gate_status": "VERIFIED",
            "as_of_date": as_of_date,
        }
        final_response["summary"] = extractive_summary(final_response["answer"])
        return {"final_response": final_response}

    if rate_card is not None or deduction_card is not None:
        answer = (
            _rate_card_answer(rate_card)
            if rate_card is not None
            else _deduction_card_answer(deduction_card)
        )
        # VERIFIED with no citations, for the same reason a computation is: the
        # figures come from slab_tables via pure functions and never pass
        # through an LLM, so there is nothing hallucinated for the gate to
        # catch. Citations are provenance, not correctness.
        final_response = {
            "answer": answer,
            "citations": [],
            "computation_trace": None,
            "ground_truth_check": None,
            "uncited_sections": [],
            "assumptions": [],
            "clarification_needed": False,
            "gate_status": "VERIFIED",
            "as_of_date": as_of_date,
            "rate_card": rate_card,
            "deduction_card": deduction_card,
        }
        final_response["summary"] = extractive_summary(answer)
        return {"final_response": final_response}

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
                # A request for input asserts no tax fact, so there is nothing to
                # verify and nothing to flag -- vacuously VERIFIED, exactly as a
                # clarifying question is.
                #
                # This was FLAGGED, which the client renders as "Review required
                # / 30% confidence / citations could not be verified against the
                # retrieved sources and were removed". Every clause of that is
                # false here: no citation was offered, nothing was retrieved, and
                # the gate never ran. It dressed a dead end up as a failed
                # verification and told the user to consult a professional about
                # an answer that does not exist.
                "gate_status": "VERIFIED",
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
        assumptions = state.get("assumptions") or []
        answer = llm_response.get("text", "")
        # Retrieval degraded with no computation to fall back on. Say so:
        # returning "" here would be a 200 carrying a blank answer, which reads
        # as "no comment" rather than "the explanation could not be generated".
        if not answer.strip():
            answer = (
                "The explanation could not be generated for this question — the "
                "language model call did not complete. Please try again."
            )
        final_response = {
            "answer": answer,
            "citations": state.get("gated_citations", []),
            "computation_trace": None,
            "ground_truth_check": None,
            "uncited_sections": [],
            "assumptions": assumptions,
            "clarification_needed": False,
            "gate_status": state.get("gate_status", "FLAGGED"),
            "as_of_date": as_of_date,
        }

    final_response["summary"] = extractive_summary(final_response["answer"])
    return {"final_response": final_response}

"""LLM-based rule extraction and evidence-span verification.

propose_rule_from_chunk — asks the LLM to extract a structured tax rate rule
    from a statutory text chunk. Returns None for commentary-only chunks or
    when the LLM cannot find an explicit rule.

verify_evidence_span — mandatory case-insensitive verbatim substring check.
    Returns False for None/empty spans. No Neo4j write happens without this
    returning True.
"""

import json

from app.services.rag.llm_client import generate_narrative
from app.shared.llm.base import LLMMessage

EXTRACTION_SYSTEM_PROMPT = """You are a statutory tax rule extractor.

Given a chunk of statutory text, extract the tax rate rule it defines — if any.
Respond with ONLY a valid JSON object. No markdown fences, no explanation, no preamble.

Schema (all fields nullable except status):
{
  "status": "RULE_FOUND" | "NO_RULE",
  "section_number": string | null,
  "asset_class": string | null,
  "rate": string | null,
  "indexation": string | null,
  "condition_text": string | null,
  "effective_from": string | null,
  "selector": string | null,
  "evidence_span": string | null
}

Rules you must follow:
- Return {"status": "NO_RULE"} for preambles, definitions, or commentary that contain no explicit tax rate.
- Return null for every field you cannot find explicitly stated in the provided text.
- Do NOT infer, estimate, round, or paraphrase — only extract verbatim facts.
- evidence_span MUST be copied verbatim as a substring from the input text.
- If you cannot find a verbatim substring to support a field you extracted, set both that field and evidence_span to null.
"""


async def propose_rule_from_chunk(chunk_text: str, chunk_id: str) -> dict | None:
    response = await generate_narrative(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=chunk_text)],
    )

    try:
        data = json.loads(response.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None

    if not isinstance(data, dict) or data.get("status") != "RULE_FOUND":
        return None

    return data


def verify_evidence_span(evidence_span: str | None, chunk_text: str) -> bool:
    if not evidence_span or not evidence_span.strip():
        return False
    return evidence_span.lower() in chunk_text.lower()

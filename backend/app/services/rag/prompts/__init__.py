"""System prompts and citation-mandate templates. The LLM's only job is to
read retrieved legal context, write narrative text, and tag every claim with
a citation -- it must never answer from training-data knowledge outside the
retrieved content.

The prohibition on emitting figures (see narration.py) is a SAFETY CONTROL, not
a style preference. The corpus contains both the current Sec 87A threshold
(12,00,000) and the superseded one (7,00,000) in the same document, with no
metadata distinguishing them, and the Evidence Gate cannot tell them apart --
it verifies provenance, not currency. A model free to quote figures from chunks
will eventually quote the stale one WITH A PASSING CITATION. Numbers therefore
come from computation/rules/personal/slab_tables.py and the dated rule graph,
and the model narrates them.
"""

from app.services.rag.prompts.narration import (
    CITATION_MANDATE,
    SYSTEM_PROMPT_TEMPLATE,
    build_narration_messages,
    parse_narration,
)

__all__ = [
    "CITATION_MANDATE",
    "SYSTEM_PROMPT_TEMPLATE",
    "build_narration_messages",
    "parse_narration",
]

"""System prompts and citation-mandate templates. The LLM's only job is to
read retrieved legal context, write narrative text, and tag every claim with
a citation -- it must never answer from training-data knowledge outside the
retrieved content.
"""

# TODO: write the real system prompt. Must instruct the model to answer only
# from the provided retrieved chunks and to tag every factual claim with a
# citation in a structured, parseable format.
SYSTEM_PROMPT_TEMPLATE = ""

# TODO: write the real citation-mandate instructions appended to every prompt.
CITATION_MANDATE = ""

"""Derives a short summary from an already-gated answer. Purely extractive --
picks leading sentences of text that has already been through the evidence
gate, rather than generating new prose -- so it introduces no new,
unverified claims and needs no separate citation check.
"""

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MAX_SUMMARY_CHARS = 240


def extractive_summary(text: str, max_chars: int = _MAX_SUMMARY_CHARS) -> str:
    text = text.strip()
    if not text:
        return text

    sentences = _SENTENCE_SPLIT.split(text)
    summary = sentences[0]
    for sentence in sentences[1:]:
        if len(summary) >= max_chars:
            break
        summary = f"{summary} {sentence}"

    if len(summary) > max_chars:
        summary = summary[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ") + "…"

    return summary

"""Enforces the "no estimated figures" rule: every numeric input into the
rules engine must be an actual, sourced figure -- never an LLM guess or an
interpolated estimate. Pure, zero I/O.
"""

from typing import Any, Mapping


def _find_estimated_paths(value: Any, path: str) -> list[str]:
    if isinstance(value, Mapping):
        offenders: list[str] = []
        if value.get("is_estimated"):
            offenders.append(path or "<root>")
        for key, sub_value in value.items():
            offenders.extend(_find_estimated_paths(sub_value, f"{path}.{key}" if path else str(key)))
        return offenders
    if isinstance(value, (list, tuple)):
        offenders = []
        for index, item in enumerate(value):
            offenders.extend(_find_estimated_paths(item, f"{path}[{index}]"))
        return offenders
    return []


def validate_no_estimates(inputs: Mapping[str, Any]) -> None:
    """Reject any input flagged as estimated rather than sourced.

    Walks `inputs` (and any nested mapping/list values) looking for an
    `is_estimated` marker truthy at any level -- e.g. a field the caller
    submitted as `{"value": 123, "is_estimated": True}` because it came from
    an unconfirmed LLM extraction or a user's rough guess rather than a
    verified source. Raises with every offending path so the caller can see
    exactly which figures need to be sourced before this rule can run.
    """
    offenders = _find_estimated_paths(inputs, "")
    if offenders:
        raise ValueError(
            "Inputs contain estimated (non-sourced) figures, which the "
            f"computation engine never accepts: {', '.join(offenders)}"
        )

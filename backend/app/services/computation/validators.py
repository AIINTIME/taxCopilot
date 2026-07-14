"""Enforces the "no estimated figures" rule: every numeric input into the
rules engine must be an actual, sourced figure -- never an LLM guess or an
interpolated estimate. Pure, zero I/O.
"""

from typing import Any, Mapping


def validate_no_estimates(inputs: Mapping[str, Any]) -> None:
    raise NotImplementedError(
        "TODO: reject any input flagged/tagged as estimated rather than "
        "sourced (e.g. an 'is_estimated' marker on the caller's data)"
    )

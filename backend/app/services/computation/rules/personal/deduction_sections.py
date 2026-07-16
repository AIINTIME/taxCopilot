"""Canonical deduction section vocabulary: field name -> label, and field name
-> the pattern that recognises it in text. Pure data, zero I/O.

Single source of truth for three consumers that previously each carried their
own copy: personal/deductions.py (labelling trace steps), analysis/reconciler.py
(labelling discrepancies) and analysis/itr_extractor.py (reading forms), plus
query/input_extractor.py (reading prose). Field names match DeductionInputs.

WORD BOUNDARIES ARE MANDATORY. Section numbers nest -- "80CCD(2)" contains
"80C", and "80CCC" does too -- so `"80c" in text` matches an NPS line and an 80C
line alike. That is not hypothetical: substring matching caused a single 50,000
NPS claim to be recorded as BOTH an 80C claim and an NPS claim, which under the
new regime then reported a lawful return as having claimed a disallowed
deduction. `\\b` after "80c" fails against the "c" of "ccd", which is exactly the
discrimination required.
"""

import re

# Field name on DeductionInputs -> the statutory label shown to users.
SECTION_LABELS: dict[str, str] = {
    "section_80c": "Sec 80C",
    "section_80d": "Sec 80D",
    "section_80g": "Sec 80G",
    "section_80tta": "Sec 80TTA",
    "home_loan_interest_24b": "Sec 24(b)",
    "hra_exemption": "Sec 10(13A)",
    "employer_nps_80ccd2": "Sec 80CCD(2)",
}

# Field name -> pattern recognising a mention, in a form line or in prose.
# Ordered longest-first where numbers nest, so a scan that stops at the first
# match cannot take the shorter one.
SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "employer_nps_80ccd2": re.compile(r"\b80\s*-?\s*ccd\s*\(\s*2\s*\)", re.IGNORECASE),
    "section_80tta": re.compile(r"\b80\s*-?\s*tta\b", re.IGNORECASE),
    "section_80c": re.compile(r"\b80\s*-?\s*c\b", re.IGNORECASE),
    "section_80d": re.compile(r"\b80\s*-?\s*d\b", re.IGNORECASE),
    "section_80g": re.compile(r"\b80\s*-?\s*g\b", re.IGNORECASE),
    "home_loan_interest_24b": re.compile(
        r"\b24\s*\(\s*b\s*\)|interest\s+on\s+(?:housing|home)\s+loan|home\s+loan\s+interest",
        re.IGNORECASE,
    ),
    "hra_exemption": re.compile(
        r"\bhra\b|house\s+rent\s+allowance|\b10\s*\(\s*13\s*a\s*\)", re.IGNORECASE
    ),
}

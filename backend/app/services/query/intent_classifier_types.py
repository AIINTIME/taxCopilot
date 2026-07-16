"""The Intent enum, split into its own module so both intent_classifier.py
and intent_examples.py can depend on it without a circular import (the
classifier needs the labeled examples, and the examples need the enum).
"""

from enum import Enum


class Intent(str, Enum):
    COMPUTATION = "computation"
    RETRIEVAL = "retrieval"
    BOTH = "both"

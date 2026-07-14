"""Content-hash idempotency check: has a source's content actually changed
since the last ingestion run? Trivial and deterministic, implemented for real
(not a stub) -- there's no business logic to defer here.
"""

import hashlib


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def has_changed(new_hash: str, existing_hash: str | None) -> bool:
    return existing_hash is None or new_hash != existing_hash

"""Fetches statutory documents from allow-listed government sources only."""

from app.services.rag.external_research.allowlist import is_allowed


async def fetch_source(url: str) -> bytes:
    if not is_allowed(url):
        raise ValueError(f"URL is not on the statutory-source allowlist: {url}")
    raise NotImplementedError("TODO: fetch `url` and return the raw document bytes")

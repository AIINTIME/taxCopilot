"""Allow-listed domains for external statutory research. Only these sources
may be scraped/fetched -- see services/ingestion/sources/gov_scraper.py.
"""

from urllib.parse import urlparse

ALLOWED_DOMAINS = {
    "incometax.gov.in",
    "cbic-gst.gov.in",
    "egazette.gov.in",
    "mca.gov.in",
}


def is_allowed(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ALLOWED_DOMAINS or any(
        host.endswith(f".{domain}") for domain in ALLOWED_DOMAINS
    )

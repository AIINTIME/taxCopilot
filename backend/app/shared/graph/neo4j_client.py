"""Neo4j graph database client.

This is the ONLY file in the codebase allowed to import the neo4j SDK.
Raw sessions and drivers never leave this module -- callers receive plain
list[dict] results.

TLS TRUST COMES FROM certifi, NOT THE OS STORE -- deliberate, and load-bearing
on Windows. A `neo4j+s://` URI makes the driver build its own SSL context from
the operating system's trust store. On Windows that store is populated lazily by
Windows Update, so a fresh machine can hold as few as ~28 roots and be missing
`SSL.com Root Certification Authority RSA` -- the CA that signs Neo4j Aura's
certificate. The connection then dies with:

    SSLCertVerificationError: self-signed certificate in certificate chain

which reads like the server is misconfigured, or the password is wrong, or a
proxy is intercepting TLS. It is none of those: measured on 2026-07-16, the
default context loaded 28 roots and FAILED, while certifi's 118 roots VERIFIED
the identical chain. The certificate was genuine throughout.

Passing an explicit certifi-backed context makes the app independent of each
machine's certificate store rather than requiring every developer to install a
root CA. Note this KEEPS full verification -- it is not `neo4j+ssc://`, which
would "fix" the error by switching the check off.
"""

import ssl

import certifi
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings


# A `+s` URI tells the driver to configure TLS itself, and it then REJECTS an
# ssl_context argument outright. So to supply our own trust store the scheme has
# to be rewritten to its plain form and encryption reintroduced via the context.
# Security is unchanged: create_default_context() verifies hostname and chain
# exactly as `+s` would -- only the source of the root CAs differs.
_ENCRYPTED_SCHEMES: dict[str, str] = {
    "neo4j+s://": "neo4j://",
    "bolt+s://": "bolt://",
}


def _driver_target(uri: str) -> tuple[str, dict]:
    """Return (uri, extra_driver_kwargs) with certifi trust where applicable.

    `+ssc` schemes are left untouched: they explicitly mean "encrypt but do not
    verify", and silently upgrading that to full verification would override a
    deliberate choice. Plain bolt:///neo4j:// (local, unencrypted) also pass
    through unchanged.
    """
    for encrypted, plain in _ENCRYPTED_SCHEMES.items():
        if uri.startswith(encrypted):
            return plain + uri[len(encrypted):], {
                "ssl_context": ssl.create_default_context(cafile=certifi.where())
            }
    return uri, {}


class Neo4jClient:
    def __init__(self) -> None:
        s = get_settings()
        uri, tls_kwargs = _driver_target(s.neo4j_uri)
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            uri, auth=(s.neo4j_user, s.neo4j_password), **tls_kwargs
        )

    async def run_write(self, query: str, **params) -> list[dict]:
        async def _write(tx):
            result = await tx.run(query, **params)
            return await result.data()

        async with self._driver.session() as session:
            return await session.execute_write(_write)

    async def run_read(self, query: str, **params) -> list[dict]:
        async def _read(tx):
            result = await tx.run(query, **params)
            return await result.data()

        async with self._driver.session() as session:
            return await session.execute_read(_read)

    async def close(self) -> None:
        await self._driver.close()


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client

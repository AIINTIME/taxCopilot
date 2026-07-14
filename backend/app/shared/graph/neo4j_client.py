"""Neo4j graph database client.

This is the ONLY file in the codebase allowed to import the neo4j SDK.
Raw sessions and drivers never leave this module — callers receive plain
list[dict] results.
"""

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings


class Neo4jClient:
    def __init__(self) -> None:
        s = get_settings()
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
        )

    async def run_write(self, query: str, **params) -> list[dict]:
        async with self._driver.session() as session:
            return await session.execute_write(
                lambda tx: tx.run(query, **params).data()
            )

    async def run_read(self, query: str, **params) -> list[dict]:
        async with self._driver.session() as session:
            return await session.execute_read(
                lambda tx: tx.run(query, **params).data()
            )

    async def close(self) -> None:
        await self._driver.close()


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client

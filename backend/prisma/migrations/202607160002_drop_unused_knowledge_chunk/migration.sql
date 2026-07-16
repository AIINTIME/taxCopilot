-- KnowledgeChunk was added in 202607160001 based on a wrong assumption that
-- the statutory vector store was pgvector-via-Postgres. It's actually
-- Pinecone (shared/vector/pinecone_client.py, "statutory-kg" namespace,
-- already populated) -- this table was never used and is empty. Dropping it
-- rather than leaving unused schema/dead code around.
DROP TABLE IF EXISTS "KnowledgeChunk";

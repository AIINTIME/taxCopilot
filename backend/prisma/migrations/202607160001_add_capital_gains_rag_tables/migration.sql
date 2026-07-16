-- Enable pgvector for KnowledgeChunk.embedding similarity search
-- (services/rag/retriever/vector_store.py)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE "UserQueryDocument" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "extractedText" TEXT NOT NULL,
    "status" "DocumentStatus" NOT NULL DEFAULT 'PROCESSING',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "UserQueryDocument_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "UserQueryDocument_userId_idx" ON "UserQueryDocument"("userId");

ALTER TABLE "UserQueryDocument" ADD CONSTRAINT "UserQueryDocument_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TABLE "KnowledgeChunk" (
    "id" TEXT NOT NULL,
    "provisionId" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "sectionReference" TEXT,
    "embedding" vector(1536),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "KnowledgeChunk_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "KnowledgeChunk_provisionId_idx" ON "KnowledgeChunk"("provisionId");

ALTER TABLE "KnowledgeChunk" ADD CONSTRAINT "KnowledgeChunk_provisionId_fkey"
    FOREIGN KEY ("provisionId") REFERENCES "KnowledgeGraphProvision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- No ANN index (ivfflat/hnsw) yet -- the table is empty until the ingestion
-- pipeline (out of scope here) populates it; a sequential scan over the
-- cosine-distance operator is fine at this size. Add one once populated.

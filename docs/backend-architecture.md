---
title: "TaxCopilot Backend — Folder Structure & Architecture Guide"
---

# TaxCopilot Backend — Folder Structure & Architecture Guide

This document explains the `backend/app/` folder structure, what belongs in each
folder, and how it maps to the two pipelines shown in the architecture diagram:
the **query pipeline** (a user asks a tax question) and the **ingestion
pipeline** (statutory sources and user documents get parsed, embedded, and
made retrievable). It is meant as an onboarding map for anyone adding code to
this backend — "I need to add X, which folder does it go in?"

---

## 1. The two pipelines, in one paragraph each

**Query pipeline** — **fully implemented and verified end-to-end** as of this
writing. A user's question comes in at `POST /api/v1/{domain}/query` (e.g.
`POST /api/v1/corporate-tax/query`). A deterministic intent classifier (no
LLM, keyword/pattern-based) decides whether the query needs the
**computation engine**, the **retrieval pipeline**, or both. Computation
queries take structured figures supplied directly on the request
(`computation_inputs` — see note below) and run them through pure Python
rule functions (MAT, AMT, regime comparison, depreciation, capital gains),
producing an exact, auditable `computation_trace` in `Decimal` arithmetic;
if a required figure is missing, the response says exactly what's missing
rather than guessing. Retrieval queries go through a hybrid retriever that
fans out to **Pinecone** (semantic vector search over the `statutory-kg`
namespace) and **Neo4j** (structured/"vectorless" lookups over the rule
graph ingestion already populates), fused with Reciprocal Rank Fusion. The
fused chunks are handed to the configured LLM provider — **the only LLM
touchpoint in the entire system**, currently OpenAI via
`shared/llm/primary_provider.py` (not Anthropic/Claude — see the `shared/llm/`
section below) — to draft a narrative with `[chunk:<id>]` citation tags, and
every citation is then run through an **Evidence Gate** that verifies it
against what was actually retrieved (chunk exists + excerpt is actually
supported by that chunk's content). Unverifiable claims are stripped and
replaced with an explicit "sources not in the Knowledge Graph" fallback
sentence, never silently dropped; `gate_status` becomes `VERIFIED` /
`PARTIAL` / `FLAGGED` accordingly. Response Assembly merges the gated
narrative (or the computation trace), and verified citations into one JSON
response, and an insert-only `AuditLog` row is written before the response
goes back to the user.

**Note on `computation_inputs`**: nothing in this codebase yet parses a
user's uploaded P&L/balance sheet into structured numeric fields (that's a
distinct, not-yet-built feature — reliable table extraction from arbitrary
financial statements). Until it exists, `QueryRequest.computation_inputs` is
how a caller (a frontend form, for now) supplies the figures a computation
needs directly.

**Ingestion pipeline** — runs independently (on a schedule, or triggered by a
user upload). External statutory sources are scraped/pulled and user
documents (P&L, GSTR, balance sheets) are uploaded, both get parsed and
chunked, a content-hash check skips re-ingesting anything unchanged, changed
content gets embedded, and the result is upserted into one of two namespaces
that are **never mixed**: the permanent `statutory-kg` namespace (the only
path through which new citable legal knowledge enters the system) or the
session-scoped `user-docs` namespace.

---

## 2. Top-level layout

```
backend/
├── app/
│   ├── api/              auth routes + admin routes
│   │   ├── auth.py           user authentication (register, login, refresh, logout, me)
│   │   ├── admin_auth.py     admin authentication (NEW)
│   │   └── admin.py          admin dashboard data endpoints (NEW)
│   ├── core/              config, redis, security
│   │   ├── config.py
│   │   ├── redis.py
│   │   └── security.py       JWT helpers for both user and admin tokens
│   ├── shared/             cross-cutting schemas + provider-isolated SDK boundaries
│   │   ├── schemas/           Citation, AuditEntry, TaxYearContext, etc.
│   │   ├── llm/                the LLM provider abstraction (see below)
│   │   ├── embeddings/         openai_embedding_provider.py — the only file allowed to embed text
│   │   ├── vector/              pinecone_client.py — the only file allowed to import the Pinecone SDK
│   │   └── graph/               neo4j_client.py — the only file allowed to import the neo4j SDK
│   ├── services/           all business logic, organized by capability
│   │   ├── query/          entrypoint, intent routing, temporal resolution
│   │   ├── computation/    the deterministic tax rules engine
│   │   ├── rag/            retrieval, LLM narration, citation verification
│   │   └── ingestion/      scraping/upload → parse → embed → upsert
│   ├── orchestration/      LangGraph wiring only — no business logic
│   ├── db.py               Prisma client
│   ├── main.py             FastAPI app entry point (mounts all routers, seeds DB)
│   ├── middleware.py        AuthEventLoggingMiddleware
│   └── schemas.py           Pydantic schemas for auth + admin + org
├── prisma/schema.prisma     data model (Organization, Admin, User, AuditLog, etc.)
└── requirements.txt
```

---

## 3. Multi-Tenancy: Organizations, Admins, and Users

### Overview

The system is structured around **Organizations**. Every Admin and every User
belongs to exactly one Organization. This enables the same username (e.g. `admin`)
to exist independently under different organizations — usernames are unique
**per organization**, not globally.

```
Organization (ICMAI | INTIME | Tax AI)
    ├── Admin (username unique per org)
    └── User (email globally unique; belongs to org + optionally to an admin)
```

### `prisma/schema.prisma` — data model

```prisma
model Organization {
  id          String   @id @default(uuid())
  slug        String   @unique          // "icmai" | "intime" | "tax_ai"
  displayName String
  createdAt   DateTime @default(now())
  admins      Admin[]
  users       User[]
}

model Admin {
  id             String       @id @default(uuid())
  username       String
  passwordHash   String
  organizationId String
  organization   Organization @relation(fields: [organizationId], references: [id])
  createdAt      DateTime     @default(now())
  updatedAt      DateTime     @updatedAt
  users          User[]
  @@unique([username, organizationId])   // same username allowed across orgs
}

model User {
  id              String        @id @default(uuid())
  email           String        @unique
  name            String
  bio             String?
  profilePhotoUrl String?
  passwordHash    String
  adminId         String?
  admin           Admin?        @relation(fields: [adminId], references: [id], onDelete: SetNull)
  organizationId  String?
  organization    Organization? @relation(fields: [organizationId], references: [id], onDelete: SetNull)
  createdAt       DateTime      @default(now())
  updatedAt       DateTime      @updatedAt
  authLogs        AuthEventLog[]
  @@index([email])
  @@index([adminId])
  @@index([organizationId])
}
```

### Seeding (startup)

On every application startup (`main.py` lifespan), the following is ensured
automatically — no manual migration step needed:

1. Three organizations are created if they do not already exist:
   `icmai`, `intime`, `tax_ai`.
2. A default admin (`username: admin`, `password: admin`) is created under the
   `intime` organization if one does not already exist.

This means a fresh database is fully usable immediately after the first server
start.

---

## 4. Folder-by-folder guide

### `app/api/auth.py` — user authentication (updated)

Handles user register, login, token refresh, logout, and `/me`. Updated to
require an `organization_id` on both register and login:

- **Register**: validates the org exists, assigns the new user to the first
  Admin found in the same org (so all users are visible in the admin dashboard),
  and sets `organizationId` on the User row.
- **Login**: validates that the user's `organizationId` matches the submitted
  `organization_id`. A user who registered under ICMAI cannot log in with the
  INTIME org selected.

Tokens issued are typed `"access"` / `"refresh"` — never usable on admin
endpoints.

### `app/api/admin_auth.py` — admin authentication (NEW)

Mirrors the pattern of `auth.py` but for the Admin model. Endpoints mounted
at `/admin/auth/*`:

| Endpoint | Description |
|----------|-------------|
| `POST /admin/auth/register` | Create a new Admin under a given org |
| `POST /admin/auth/login`    | Validate username + password + org, issue tokens |
| `POST /admin/auth/refresh`  | Rotate refresh token via HttpOnly cookie |
| `POST /admin/auth/logout`   | Clear cookie + revoke Redis key |
| `GET  /admin/auth/me`       | Return current admin info |

**Token distinction** — admin tokens carry `"type": "admin_access"` /
`"type": "admin_refresh"` in their JWT payload. The `get_current_admin`
FastAPI dependency rejects any token that is not `admin_access`, so user
tokens cannot be used on admin endpoints and vice versa.

**Refresh cookie** — stored as `taxai_admin_refresh_token` (separate from the
user refresh cookie `taxai_refresh_token`), path `/admin/auth`, HttpOnly,
SameSite=Lax, Secure in production.

**Redis keys** — stored as `admin_refresh:{token_id}` (separate namespace from
user refresh keys `refresh:{token_id}`).

### `app/api/admin.py` — admin dashboard data (NEW)

All routes require the `get_current_admin` dependency. Mounted at `/admin/*`:

| Endpoint | Returns |
|----------|---------|
| `GET /admin/stats` | `total_users`, `total_audit_logs`, `total_provisions`, `security_alerts` |
| `GET /admin/users` | Paginated list of all users (id, name, email, created_at) |
| `GET /admin/audit-logs` | Recent AuditLog entries (id, userId, query, gateStatus, createdAt) |
| `GET /admin/documents` | KnowledgeGraphProvision entries |

### `app/core/security.py` — JWT helpers (updated)

Added admin-specific token creators alongside the existing user functions:

```python
# User tokens (unchanged)
create_access_token(user_id)          # type: "access"
create_refresh_token(user_id)         # type: "refresh"

# Admin tokens (new)
create_admin_access_token(admin_id)   # type: "admin_access"
create_admin_refresh_token(admin_id)  # type: "admin_refresh"

# Shared decoder
decode_token(token, expected_type)    # raises ValueError on type mismatch
```

Also includes a bcrypt compatibility shim at module load time to suppress the
`AttributeError: module 'bcrypt' has no attribute '__about__'` warning that
passlib 1.7.4 produces with bcrypt 4.x. This is a no-op on bcrypt 3.x.

### `app/schemas.py` — Pydantic schemas (updated)

Added schemas for organization, admin register/login, and admin responses:

```python
class OrganizationResponse(BaseModel):
    id: str; slug: str; display_name: str

class AdminRegisterRequest(BaseModel):
    username: str          # 3–50 chars
    password: str          # 8–128 chars
    organization_id: str

class AdminLoginRequest(BaseModel):
    username: str
    password: str
    organization_id: str

class AdminResponse(BaseModel):
    id: str; username: str; organization_id: str; created_at: datetime

class AdminAuthResponse(BaseModel):
    access_token: str; token_type: str = "bearer"; admin: AdminResponse

class AdminStatsResponse(BaseModel):
    total_users: int; total_audit_logs: int
    total_provisions: int; security_alerts: int

class AdminUserItem(BaseModel):
    id: str; name: str; email: str; created_at: datetime
```

User schemas (`RegisterRequest`, `LoginRequest`) also gained `organization_id: str`.

### `app/main.py` — app entry point (updated)

Router mounts:

```python
app.include_router(auth_router)                        # /register, /login, etc.
app.include_router(admin_auth_router, prefix="/admin/auth")
app.include_router(admin_router,      prefix="/admin")
app.include_router(query_router)
```

New public endpoint:

```python
GET /organizations   # returns the list of orgs for populating login/register dropdowns
```

### `app/api/` and `app/core/` — existing, unchanged (RAG/computation)

Auth routes and the app-wide config/redis/security utilities. Nothing new
goes here for AI/RAG/computation work — see `app/shared/llm/config.py`
instead for LLM-specific settings, so this layer stays untouched.

### `app/shared/schemas/` — types shared across every service

Pydantic models with no business logic: `Citation`, `AuditEntry`,
`TaxYearContext` / `AssessmentYear` / `TaxActRegime`, and the two hard pivot
dates the whole system resolves as-of first — **23 Jul 2024** (capital gains
rate/indexation change) and **1 Apr 2026** (1961 Act → 2025 Act transition).
**Put a type here** when two or more of `services/` or `orchestration/` need
to agree on its shape.

### `app/shared/llm/` — the provider-agnostic LLM boundary

This is the wall around the "ONLY LLM TOUCHPOINT IN SYSTEM" box. **Correction
to the original diagram**: the diagram assumed Claude/Anthropic; the actual
provider wired up is **OpenAI** (`gpt-4o`). If you're looking for an
`anthropic_provider.py`, it doesn't exist — this is the current, real set of
files:
- `base.py` — the `LLMProvider` interface every provider implements
  (`generate(system_prompt, messages, temperature=0.0) -> LLMResponse`).
- `primary_provider.py` — **implemented.** Wraps `AsyncOpenAI`, the only file
  under `services/` or `shared/` other than `shared/embeddings/` allowed to
  import the `openai` SDK. Current-gen OpenAI/Anthropic models reject an
  explicit `temperature` param on some tiers — check the model you're
  targeting before assuming `temperature=0.0` is accepted as a literal kwarg.
- `fallback_provider.py` — **still a stub** (`NotImplementedError`). The
  router below falls through to this on any primary-provider exception; today
  that just means the caller's request fails after the primary attempt (e.g.
  ingestion's rule-extraction step catches this specific case and skips
  gracefully rather than failing the whole document — see
  `app/api/admin.py`'s upload endpoint).
- `router.py` — **implemented.** Tries the primary provider, falls back on
  any exception, logs which provider actually served the response.
- `config.py` — API keys / model names (`PRIMARY_LLM_API_KEY`,
  `PRIMARY_LLM_MODEL`, `PRIMARY_LLM_BASE_URL`, `FALLBACK_LLM_*`), kept
  separate from `app/core/config.py`.

**Never** import an LLM SDK anywhere else. If you're adding a new provider,
it's a new file in this folder implementing `LLMProvider` — no other file
changes. `services/rag/llm_client.py` (below) is the only file under
`services/` allowed to import from this package at all.

### `app/shared/vector/`, `app/shared/embeddings/`, `app/shared/graph/` — the other SDK boundaries

Same isolation pattern as `shared/llm/`, one per external service:
- `vector/pinecone_client.py` — the only file allowed to import the
  `pinecone` SDK. Exposes `upsert(namespace, vectors)` and
  `query(namespace, vector, top_k, filter)`, returning plain `list[dict]` —
  no Pinecone SDK types leak out. Two namespaces, never mixed:
  `statutory-kg` (permanent, ingestion-only writes) and `user-docs` (session-
  scoped uploads — **reserved but not yet used**, no user-facing upload
  endpoint exists yet, only the admin console can ingest documents).
- `embeddings/openai_embedding_provider.py` — the only file allowed to call
  OpenAI's embeddings endpoint (separate from `llm/primary_provider.py`,
  which handles chat completions — different concern, same vendor).
- `graph/neo4j_client.py` — the only file allowed to import the `neo4j` SDK.
  Exposes `run_read(query, **params)` / `run_write(query, **params)`,
  returning plain `list[dict]`.

### `app/services/query/` — the entrypoint (**fully implemented**)

- `routes.py` — `POST /api/v1/{domain}/query`, e.g.
  `domain="corporate-tax"`. `QueryRequest` also carries an optional
  `computation_inputs: dict[str, Any] | None` field (see the note in §1).
- `intent_classifier.py` — **implemented**, regex/keyword-based
  `Intent.COMPUTATION | RETRIEVAL | BOTH`. Routes each query without ever
  calling an LLM — this is a control-flow decision, and the LLM never makes
  control-flow decisions in this system.
- `temporal_resolver.py` — **implemented.** Parses an explicit date out of
  the query (`AY 2025-26`, `FY 2024-25`, or a raw date) or falls back to
  today, derives the Assessment Year, and branches `regime` /
  `capital_gains_period` on the two pivot dates.

### `app/services/computation/` — the deterministic rules engine (**fully implemented**)

Zero I/O, as designed: nothing under `rules/` (or `engine.py`) imports the
database, an LLM client, or an HTTP client — the caller (the orchestration
layer) passes in plain values via `computation_inputs`.
- `engine.py` — **implemented.** `compute(rule_name, inputs, as_of)` looks up
  the rule, coerces raw JSON-shaped values (strings, ISO date strings) into
  the rule's `Decimal`/`date` dataclass fields, and raises
  `MissingComputationInputError` (naming exactly which fields are absent) if
  a required input wasn't supplied — it never defaults a missing figure to 0.
- `rules/mat.py`, `rules/amt.py`, `rules/regime_comparison.py`,
  `rules/depreciation.py`, `rules/capital_gains.py` — **implemented**, real
  `Decimal` math (Sec 115JB MAT, Sec 115JC AMT, Sec 115BAA/115BAB regime
  comparison, Schedule III/WDV depreciation, date-split capital gains with
  23-Jul-2024 grandfathering). Each has a docstring flagging its known scope
  boundaries (e.g. MAT/AMT don't add surcharge since their inputs don't carry
  an income tier; capital gains raises a clear error instead of guessing an
  indexation multiplier when CII data isn't supplied — see `cii_tables.py`
  below). 2025-Act rate equivalents are implemented as "same as 1961 Act,
  pending domain-expert verification" since that Act isn't in force yet.
  **Add a new tax computation here** — same pattern: a frozen input/result
  dataclass pair + a pure function, registered in `engine.py`'s `RULES` dict.
- `cii_tables.py` — **still a stub** (`CII_TABLE = {}`, `get_cii()` raises
  `NotImplementedError`). Not yet wired to `rules/capital_gains.py` — that
  function currently raises its own explicit "CII data required" error
  instead of calling this. Wiring them together is the natural next step for
  indexed LTCG support.
- `computation_trace.py` — **implemented.** `build_computation_trace(...)`
  returns a `ComputationTrace` (rule name, inputs, outputs, statutory
  references, as-of context, timestamp) — this is what ends up in the API
  response's `computation_trace` field and in the `AuditLog` row.
- `validators.py` — **still a stub**, not called anywhere yet. The "never an
  estimated figure" guarantee is currently enforced structurally instead (the
  rule functions only accept the exact fields their dataclass defines, and
  `engine.py` refuses to proceed if one is missing) rather than through an
  explicit `is_estimated` marker check.

### `app/services/rag/` — retrieval, narration, citation verification (**fully implemented**)

- `retriever/vector_store.py` — **implemented, and redirected from the
  original scaffold.** The scaffold assumed pgvector-via-Postgres (no
  embedding table was ever added); this now queries the real **Pinecone**
  index ingestion writes to (`statutory-kg` namespace), embedding the query
  text via `shared/embeddings/openai_embedding_provider.py` first.
- `retriever/graph_store.py` — **new file, not in the original scaffold.**
  The "vectorless"/structured half of retrieval. Deterministic text-matching
  against section-number/asset-class hints extracted from the query, reading
  the `Section` / `AssetClass` / `RateRule` / `VectorChunkRef` nodes that
  `services/ingestion/kg_graph_extraction/graph_writer.py` populates in
  Neo4j. Replaces the scaffold's originally-planned `keyword_store.py` path.
- `retriever/keyword_store.py` — **still the original stub, not wired into
  `hybrid_retriever.py`.** It targets Postgres full-text search over
  `KnowledgeGraphProvision.content`, but nothing in the current ingestion
  pipeline writes to that table (ingestion writes to `Document` +
  `GraphRuleProposal` + Pinecone + Neo4j instead) — so `graph_store.py`
  covers this pipeline's structured-retrieval need instead, per above.
- `retriever/hybrid_retriever.py` — **implemented.** Fuses
  `vector_store.similarity_search` + `graph_store.structured_search` via
  Reciprocal Rank Fusion (not vector + keyword, per the note above).
- `evidence_gate.py` — **implemented.** `extract_citations()` pulls
  `[chunk:<id>]` markers out of the LLM's narrative text; `verify_citations()`
  confirms each cited chunk_id was actually retrieved *and* that the claim's
  text is substantively supported by that chunk's content (word-overlap
  check, not exact-verbatim — narrative prose paraphrases, unlike ingestion's
  stricter verbatim evidence-span check); `strip_unverified_claims()`
  replaces any unverified claim with an explicit "sources not in the
  Knowledge Graph" sentence rather than silently deleting it.
  `gate_status`: `VERIFIED` (all citations verified) / `PARTIAL` (some) /
  `FLAGGED` (none, or no citations were produced at all for a substantive
  answer).
- `confidence.py` — **still a stub, not called anywhere.** Retrieval ranking
  currently relies on Pinecone's own similarity score + RRF fusion rank
  instead of a separate calibrated confidence pass.
- `llm_client.py` — **implemented.** `generate_narrative()` delegates to
  `shared/llm/router.py`'s `get_llm_provider().generate(...)`. The only file
  under `services/` allowed to import from `shared/llm/`.
- `prompts/` — **implemented.** `SYSTEM_PROMPT_TEMPLATE` instructs the model
  to answer only from the provided chunks, tag every claim with
  `[chunk:<id>]`, never fabricate a chunk_id, and say "This query requires
  sources not currently in the Knowledge Graph — consult a domain expert."
  when the retrieved context is insufficient — never answer from training
  data. `build_context_block()` formats retrieved chunks into the prompt.
- `external_research/allowlist.py` — implemented (real domain allowlist +
  `is_allowed()` check), untouched by this round of work.
- `external_research/session_documents.py` — **still a stub.** Retrieval
  scoped to one user's own uploaded documents (as opposed to the permanent
  statutory-kg namespace) isn't wired up — this is the retrieval-side
  counterpart to the "no user-facing upload endpoint yet" gap noted in §5.

### `app/services/ingestion/` — the diagram's "Scheduled Ingestion Pipeline"

- `scheduler.py` — periodic trigger for re-scraping statutory sources.
- `sources/gov_scraper.py` — pulls from allow-listed external tax sources.
- `sources/upload_handler.py` — accepts user document uploads (P&L, GSTR,
  balance sheets).
- `parsing/pdf_parser.py`, `parsing/xlsx_parser.py` — the diagram's
  "Parse & chunk" step.
- `dedup.py` — content-hash idempotency check. Already fully implemented.
- `embedding.py` — text embedding calls (diagram specifies OpenAI
  `text-embedding-3-large`). **Open design question** — see §5.
- `upsert/statutory_kg_upsert.py` — writes into the permanent knowledge-graph
  namespace. **This is the only path new citable legal knowledge enters the
  system through.** `upsert_chunk_to_statutory_kg()` is implemented and is
  what `services/rag/retriever/vector_store.py` reads back from.
- `upsert/user_docs_upsert.py` — writes into the session-scoped namespace.
  Never mixed with the statutory KG namespace. **Not yet implemented/called
  anywhere** — there's no user-facing upload endpoint yet, only the admin
  console (`app/api/admin.py`'s `/admin/documents/upload`) can ingest
  documents today, and it only ever writes to `statutory-kg`.
- `kg_graph_extraction/` — **not in the original diagram, but real and
  implemented.** The LLM-based structured-rule-extraction half of ingestion,
  separate from the vector-embedding half above:
  - `rule_proposal.py` — asks the LLM to extract a structured tax rule
    (section number, asset class, rate, condition) from a chunk, with a
    mandatory independent verbatim-substring check (`verify_evidence_span`)
    that never trusts the LLM's own claim about where its answer came from.
  - `pipeline.py` — `process_chunk_for_graph()`: decides `AUTO_APPROVED` vs
    `PENDING_REVIEW` based on that verification, writes a `GraphRuleProposal`
    row (Postgres) always, and calls `graph_writer.py` only when
    auto-approved.
  - `graph_writer.py` — idempotent (`MERGE`-based) Cypher writes into Neo4j:
    `Section` / `AssetClass` / `RateRule` / `VectorChunkRef` nodes — this is
    exactly what `services/rag/retriever/graph_store.py` reads back from on
    the query side.

### `app/orchestration/` — wiring only, no business logic (**query_graph.py fully implemented**)

This package's only job is control flow — it calls into `services/*` and
manages state; it must never contain a statutory rule, a prompt, or a
retrieval algorithm itself.
- `state.py` — the shared state schema threaded through every graph node.
  Now also carries `computation_inputs: dict[str, Any] | None`.
- `graphs/query_graph.py` — **fully implemented.** The LangGraph
  `StateGraph` wiring the full sequence: `classify_intent → resolve_temporal
  → (computation | retrieval → narrate → evidence_gate) → assemble_response →
  audit_log`. `run_query_graph()` builds the initial state from the request,
  invokes the compiled graph, and returns `final_response` merged with the
  persisted audit row's id as `audit_log_id`.
- `graphs/ingestion_graph.py` — the executable version of the
  ingestion-pipeline diagram: dedup → parse → embed → upsert. Untouched by
  this round of work — the admin upload endpoint
  (`app/api/admin.py`) currently calls the ingestion services directly
  rather than through this graph; worth reconciling at some point so there's
  one ingestion entrypoint, not two.
- `nodes/assemble_response.py` — **implemented.** Builds the final
  `{answer, citations, computation_trace, gate_status, as_of_date}` object
  from whichever branch ran; a missing-computation-data result becomes an
  explicit `FLAGGED` response naming what's missing, never a guess.
- `nodes/audit_log_node.py` — **implemented.** Writes the insert-only
  `AuditLog` row (first real writes to this table) — `citations` is stored
  via Prisma's `Json(...)` wrapper (required for JSON-typed fields in
  prisma-client-py, not just a raw dict/list).

---

## 5. Where this scaffold differs from the diagram (read before building further)

- ~~**Vector store**: pgvector vs Pinecone~~ — **RESOLVED.** Retrieval now
  queries the real Pinecone index (`shared/vector/pinecone_client.py`,
  `services/rag/retriever/vector_store.py`), matching the original diagram.
  No pgvector extension or embedding table was ever added — that path is
  dead, not just deferred.
- **Gate status naming**: the `GateStatus` enum (`VERIFIED` / `FLAGGED` /
  `PARTIAL`) is what's actually implemented end-to-end in
  `services/rag/evidence_gate.py` and the `AuditLog.gateStatus` column — no
  further reconciliation needed, this is simply the system's naming now.
- ~~**Embedding provider**: undecided~~ — **RESOLVED.**
  `shared/embeddings/openai_embedding_provider.py` exists and is used by both
  the ingestion write path and the query-side `vector_store.py` read path.
- **LLM provider**: the diagram (and earlier versions of this doc) assumed
  Claude/Anthropic. The actual wired-up provider is **OpenAI** (`gpt-4o`) via
  `shared/llm/primary_provider.py`. If Claude/Anthropic support is wanted
  later, it's a new file in `shared/llm/` implementing `LLMProvider` — no
  other file should need to change.
- **No user-facing document upload yet**: only the admin console can ingest
  documents (`POST /admin/documents/upload`, always into the permanent
  `statutory-kg` namespace). The `user-docs` Pinecone namespace and
  `services/rag/external_research/session_documents.py` are reserved for a
  regular-user upload flow that doesn't exist yet — building it is a
  distinct feature (auth model, storage, namespace routing), not a small
  addition to the admin upload path.
- **No structured financial-figure extraction yet**: the computation engine
  is real and correct, but nothing parses a user's uploaded P&L/balance
  sheet into the numeric fields (`book_profit`, `total_income`, etc.) it
  needs — a caller must supply `computation_inputs` directly on the request
  today. This is a distinct, sizeable feature (reliable table extraction
  from arbitrary financial statements), not a gap in the computation engine
  itself.
- **Two ingestion entrypoints**: `app/api/admin.py`'s upload endpoint calls
  ingestion services directly; `orchestration/graphs/ingestion_graph.py`
  exists as a separate, not-currently-invoked LangGraph version of the same
  flow. Worth consolidating to one entrypoint eventually.

---

## 6. Quick reference — "I need to add X, where does it go?"

| You're adding...                                      | Goes in...                                              |
|-------------------------------------------------------|----------------------------------------------------------|
| A new statutory computation (e.g. Sec 80-IAC)         | `services/computation/rules/<new_rule>.py`               |
| A new allow-listed government source                  | `services/rag/external_research/allowlist.py`            |
| A new document type to parse (e.g. .docx)             | `services/ingestion/parsing/<new>_parser.py`             |
| A change to how citations are verified                | `services/rag/evidence_gate.py`                          |
| A change to the LLM prompt / citation mandate         | `services/rag/prompts/`                                  |
| A second LLM provider (e.g. as the real fallback)     | `shared/llm/fallback_provider.py` only                   |
| A new field on the audit row                          | `prisma/schema.prisma` (`AuditLog`) + `shared/schemas/audit_entry.py` |
| A change to the query flow's sequencing               | `orchestration/graphs/query_graph.py`                    |
| A new API endpoint under `/api/v1/...`                | `services/query/routes.py` (or a new `services/<domain>/routes.py`) |
| A new admin dashboard endpoint                        | `app/api/admin.py`                                       |
| A new organization (tenant)                           | Add to `SEED_ORGS` list in `app/main.py`                 |
| A new admin-specific JWT operation                    | `app/core/security.py` (follow existing admin token pattern) |
| A change to how a query gets routed to computation vs. retrieval | `services/query/intent_classifier.py` (keep it deterministic — no LLM) |
| A change to vector retrieval (Pinecone)                | `services/rag/retriever/vector_store.py`                  |
| A change to structured/graph retrieval (Neo4j)          | `services/rag/retriever/graph_store.py`                   |
| Wiring Cost Inflation Index data for indexed capital gains | `services/computation/cii_tables.py` (currently a stub) + `services/computation/rules/capital_gains.py` |
| A user-facing (non-admin) document upload endpoint      | New — doesn't exist yet; see the `user-docs` namespace note in §5 |

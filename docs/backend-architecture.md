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

**Query pipeline** — a user's question comes in at
`POST /api/v1/{domain}/query` (e.g. `POST /api/v1/corporate-tax/query`). A
deterministic intent classifier (no LLM, regex-fast-path + embedding-based
k-NN fallback against curated examples) decides whether the query needs the
**computation engine**, the **retrieval pipeline**, or both. A computation
can be triggered three ways, tried in this order: (1) an explicit
`computation_request` (`{rule_name, inputs}`) supplied on the request; (2) an
uploaded document (`uploaded_document_text`) that the document-extraction
step LLM-extracts and evidence-span-verifies fields from (currently wired for
capital gains, via `services/rag/extraction/document_extraction.py`); or (3),
when neither is given but the query text itself names a computation (MAT,
AMT, regime comparison, depreciation, capital gains), the rule name is
inferred from the query and paired with `computation_inputs` supplied on the
request. Any of these runs the matched rule through a pure Python function
(`services/computation/rules/`) producing an exact, auditable
`computation_trace`; a genuinely successful computation is then cross-checked
against the statutory rule graph in Neo4j by a **ground-truth check** before
the response is assembled, and a query that was guessed as a computation but
matches no known rule falls through to retrieval instead of dead-ending.
Retrieval queries go through a hybrid retriever that fans out to **Pinecone**
(semantic vector search over the `statutory-kg` namespace) and **Neo4j**
(structured/"vectorless" lookups over the rule graph ingestion populates),
fused with Reciprocal Rank Fusion. The fused chunks are handed to the
configured LLM provider — **the only LLM touchpoint in the entire system**,
currently OpenAI via `shared/llm/primary_provider.py` (not Anthropic/Claude —
see the `shared/llm/` section below) — to draft a narrative with `[N]`
citation tags (a numeric index into the numbered context block, not the raw
chunk_id), and every citation is then run through an **Evidence Gate** that
verifies each cited chunk was actually retrieved and that the claim's
specific facts (section references, rates, monetary amounts) are verbatim-
traceable to that chunk's content, falling back to a word-overlap check for
claims with no such specific facts to check. Unverifiable claims are stripped
and replaced with an explicit "sources not in the Knowledge Graph" fallback
sentence, never silently dropped; `gate_status` becomes `VERIFIED` /
`PARTIAL` / `FLAGGED` accordingly. Response Assembly merges the gated
narrative (or the computation trace plus its ground-truth check), an
extractive `summary`, and verified citations into one JSON response, and an
insert-only `AuditLog` row is written before the response goes back to the
user.

**ITR return analysis** (`services/analysis/`) — a separate, reverse-direction
capability alongside the query pipeline: instead of "what would I owe",
`POST /api/v1/personal-tax/analyze-return` takes a filed return, recomputes it
from its own declared figures using the same personal-tax rules the query
pipeline uses, diffs the result against what was actually filed, and returns
the discrepancies (each tagged with the source line it came from) plus a
deterministic accuracy/risk score. No LLM decides whether a return is wrong,
picks a penalty, or computes the score — only arithmetic and (for penalties,
currently returning none pending graph coverage) a Neo4j lookup.

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
│   │   └── ingestion/      scraping/upload → parse → embed → upsert → graph extraction (NEW)
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
| `GET /admin/stats` | `total_users`, `total_audit_logs`, `total_provisions`, `security_alerts` (hardcoded `0` — not yet implemented) |
| `GET /admin/users` | Paginated list of users in the admin's org (id, name, email, created_at) |
| `POST /admin/users` | Create a user directly under the calling admin (NEW) |
| `PATCH /admin/users/{id}` | Update a user's name/email (NEW) |
| `PATCH /admin/users/{id}/password` | Reset a user's password (NEW) |
| `PATCH /admin/users/{id}/status` | Activate/deactivate a user (NEW) |
| `GET /admin/audit-logs` | Recent AuditLog entries (id, userId, query, gateStatus, createdAt) |
| `POST /admin/documents/upload` | Upload a document; parses, chunks, embeds + upserts each chunk to Pinecone `statutory-kg`, and (best-effort) runs each chunk through `kg_graph_extraction` for rule proposals (NEW) |
| `GET /admin/documents` | `Document` rows (filename, status, chunks embedded, uploader) — **not** `KnowledgeGraphProvision` as previously documented |
| `GET /admin/rule-proposals` | `GraphRuleProposal` rows from the knowledge-graph extraction pipeline, optionally filtered by `status` (NEW) |

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
- `fallback_provider.py` — **implemented.** Groq, via an OpenAI-compatible
  endpoint (`FALLBACK_LLM_API_KEY`/`FALLBACK_LLM_MODEL`/`FALLBACK_LLM_BASE_URL`),
  reusing the `openai` SDK client rather than adding a new one since Groq
  speaks the same chat-completions protocol. An unset `FALLBACK_LLM_API_KEY`
  raises a clear error immediately rather than attempting a request that
  would fail with a confusing auth error.
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
- `intent_classifier.py` — **implemented**: a regex fast-path for the
  clearest phrasings, falling back to an embedding-based k-NN classifier
  (cosine similarity against curated labeled examples in
  `intent_examples.py`, rank-weighted voting) for anything ambiguous.
  Deterministic and reproducible either way — this is a control-flow
  decision, and the LLM never makes control-flow decisions in this system.
- `input_extractor.py` — **implemented.** Deterministic (regex, never an
  LLM) extraction of personal-tax computation inputs straight out of a
  query's text, e.g. "my salary is 21 lakhs, I have 80C of 1.5L" ->
  `{gross_income: 2100000, deductions: {section_80c: 150000}}`. Handles
  Indian numeral notation (lakh/crore/lpa/k), binds each amount to the
  nearest income/section label rather than just taking the largest number,
  and reports `missing`/`assumptions` so the graph can ask a clarifying
  question instead of guessing. `states_income()` is also used by
  `query_graph.py`'s rule-name inference to recognize a personal-tax
  computation query, and is exported for `intent_classifier.py`'s "what is
  my payable tax" vs "what is HRA" disambiguation (not currently wired
  into the kept classifier, but available).
- `temporal_resolver.py` — **implemented.** Parses an explicit date, or an
  AY/FY mention (`AY 2025-26`, `FY 2024-25`), out of the query; if neither
  is present, defaults to the **most recently completed FY** (the one a
  taxpayer would currently be filing for) rather than today's wall-clock
  date — a query asked in July 2026 about "my tax" concerns FY 2025-26
  (ended 31 Mar 2026), not whatever regime happens to govern today. Every
  code path that resolves a year without an exact date anchors to that
  year's **start** (1 Apr), consistently: FY 2024-25 straddles the
  23-Jul-2024 capital-gains rate change, so the start/end choice actually
  changes which side of that pivot the year resolves to.

### `app/services/computation/` — the deterministic rules engine (**fully implemented**)

Zero I/O, as designed: nothing under `rules/` (or `engine.py`) imports the
database, an LLM client, or an HTTP client — the caller (the orchestration
layer) passes in plain values via `computation_inputs`.
- `engine.py` — **implemented**, with two dispatch mechanisms side by side.
  Most rules use reflection (`_INPUT_TYPES` + generic `_build_input`):
  `compute(rule_name, inputs, as_of)` coerces raw JSON-shaped values (strings,
  ISO date strings) into the rule's `Decimal`/`date` dataclass fields via
  `dataclasses.fields()`, and raises `MissingComputationInputError` (naming
  exactly which fields are absent) if a required input wasn't supplied — it
  never defaults a missing figure to 0. A rule whose input shape reflection
  can't handle generically (a nested dataclass, an enum field) instead
  registers a `RuleSpec` in `_SPECS` with explicit `build_input`/`to_outputs`/
  `to_steps` functions; `compute()` tries `_SPECS` first, falling back to the
  reflection path. `personal_regime_comparison` (below) is the one rule that
  needs this today, because `PersonalRegimeInput` nests a `DeductionInputs`
  dataclass and an `IncomeType` enum.
- `rules/mat.py`, `rules/amt.py`, `rules/regime_comparison.py`,
  `rules/depreciation.py`, `rules/capital_gains.py`,
  `rules/capital_gains_exemptions.py` — **implemented**, real `Decimal` math
  (Sec 115JB MAT, Sec 115JC AMT, Sec 115BAA/115BAB regime comparison,
  Schedule III/WDV depreciation, date-split capital gains, and the Sec
  54/54B/54EC/54F reinvestment exemptions). Each has a docstring flagging
  its known scope boundaries (e.g. MAT/AMT don't add surcharge since their
  inputs don't carry an income tier; `capital_gains.py` raises a clear error
  instead of guessing an indexation multiplier when CII data isn't supplied,
  rather than computing it itself — see `cii_tables.py` below). 2025-Act
  rate equivalents are implemented as "same as 1961 Act, pending
  domain-expert verification" since that Act isn't in force yet. **Add a new
  tax computation here** — same pattern: a frozen input/result dataclass
  pair + a pure function, registered in `engine.py`'s `RULES`/`_INPUT_TYPES`
  dicts (or `_SPECS` if the input shape needs custom construction).
- `rules/personal/` — **implemented.** The individual (Sec 115BAC old-vs-new
  regime) computation, a separate taxpayer/Act chapter from
  `rules/regime_comparison.py`'s corporate 115BAA/115BAB comparison despite
  the similar name — the two share no code. `regime_comparison_personal.py`
  computes both regimes via `slab_tables.py` (rate/slab data),
  `deductions.py` (Chapter VI-A + salary deductions, regime-eligibility
  aware), `rebate_87a.py`, and `surcharge_cess.py`, and reports a
  `breakeven_deductions` figure (the deduction total at which the old regime
  overtakes) plus a real `RegimeRecommendation.EITHER` case for when the Sec
  87A rebate zeroes both regimes at low incomes — never a bare
  old-regime-wins default from an unclaimed-deductions input. Every step is
  tagged with its section, feeding `orchestration/nodes/computation_citations.py`.
- `cii_tables.py` — **implemented** (a real `CII_TABLE` + `get_cii()`), but
  currently **unwired** — `rules/capital_gains.py` deliberately raises its
  own explicit "CII data required" error for any indexed-LTCG case instead
  of calling this. Wiring them together to compute indexed LTCG directly,
  rather than erroring out, is the natural next step.
- `computation_trace.py` — **implemented.** `build_computation_trace(...)`
  returns a `ComputationTrace` (rule name, inputs, outputs, statutory
  references, as-of context, timestamp) — this is what ends up in the API
  response's `computation_trace` field and in the `AuditLog` row.
- `validators.py` — **implemented and wired.** `validate_no_estimates()` is
  called by `engine.py` before building a rule's input, walking every
  input value (including nested mappings/lists) for an `is_estimated`
  marker and rejecting the whole call if any figure is flagged as such —
  the computation engine never runs on an LLM guess or unconfirmed
  extraction, only sourced figures.

### `app/services/rag/` — retrieval, narration, citation verification (**fully implemented**)

- `retriever/vector_store.py` — **implemented, and redirected from the
  original scaffold.** The scaffold assumed pgvector-via-Postgres (no
  embedding table was ever added); this now queries the real **Pinecone**
  index ingestion writes to (`statutory-kg` namespace), embedding the query
  text via `shared/embeddings/openai_embedding_provider.py` first. The
  Pinecone SDK's `query()` call is synchronous, so it's run via
  `asyncio.to_thread` rather than blocking the event loop.
- `retriever/graph_store.py` — **new file, not in the original scaffold.**
  Two independent read paths over the same graph: `structured_search()` does
  deterministic text-matching against section-number/asset-class hints
  extracted from the query, feeding `hybrid_retriever.py`'s RRF fusion;
  `lookup_rate_rule()` does fuzzy keyword matching against free-text
  asset-class labels, feeding the computation path's ground-truth check
  (see `ground_truth_gate.py` below). Both read the `Section` / `AssetClass`
  / `RateRule` / `VectorChunkRef` nodes that
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
- `evidence_gate.py` — **implemented.** `extract_citations()` pulls `[N]`
  markers out of the LLM's narrative text (a numeric index into
  `prompts.build_context_block()`'s numbered context, not the raw chunk_id —
  short numeric tokens are reproduced far more reliably by the model) and
  pairs each with the preceding clause as its excerpt; `verify_citations()`
  confirms each cited chunk was actually retrieved and that the excerpt's
  specific facts (section references, percentages, monetary amounts) are
  verbatim-traceable to that chunk's content, falling back to a word-overlap
  check only when the excerpt makes no such specific, checkable claim;
  `strip_unverified_claims()` replaces any unverified claim with an explicit
  "sources not in the Knowledge Graph" sentence rather than silently
  deleting it. `gate_status`: `VERIFIED` (all citations verified) /
  `PARTIAL` (some) / `FLAGGED` (none, or no citations were produced at all
  for a substantive answer).
- `ground_truth_gate.py` — **new file.** The computation path's cross-check,
  distinct from the retrieval path's evidence gate: `derive_ground_truth_keywords()`
  turns a computation's rule name + outputs into keywords for
  `graph_store.lookup_rate_rule()`, and `verify_computation_ground_truth()`
  compares the rule's applied rate against whatever the graph/retrieved
  chunks say. Degrades to "no ground truth available" (never blocks or
  fails the response) if Neo4j/Pinecone are unreachable or simply have no
  matching rule yet — the computation result is already correct on its own,
  this is only a corroboration signal.
- `confidence.py` — **still a stub, not called anywhere.** Retrieval ranking
  currently relies on Pinecone's own similarity score + RRF fusion rank
  instead of a separate calibrated confidence pass.
- `llm_client.py` — **implemented.** `generate_narrative()` delegates to
  `shared/llm/router.py`'s `get_llm_provider().generate(...)`. The only file
  under `services/` allowed to import from `shared/llm/`.
- `prompts/` — **implemented.** `SYSTEM_PROMPT_TEMPLATE` instructs the model
  to answer only from the provided chunks, tag every claim with `[N]`, never
  cite a number higher than the highest one shown, and say "This query
  requires sources not currently in the Knowledge Graph — consult a domain
  expert." when the retrieved context is insufficient — never answer from
  training data. `build_context_block()` formats retrieved chunks into the
  numbered prompt context.
- `extraction/document_extraction.py` — **new file.** LLM-extracts capital
  gains computation fields (dates, consideration, cost figures) from an
  uploaded document's raw text, verifying every extracted field against an
  evidence span in the source text before it's trusted — a field the LLM
  can't back with a verbatim quote from the document is dropped and reported
  as missing rather than used. Feeds `query_graph.py`'s document-extraction
  node, which only auto-builds a `computation_request` once every required
  field is verified.
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
- `parsing/pdf_parser.py`, `parsing/xlsx_parser.py`, `parsing/docx_parser.py`,
  `parsing/text_parser.py` — the diagram's "Parse & chunk" step.
- `dedup.py` — content-hash idempotency check. Already fully implemented.
- `embedding.py` — text embedding calls. Delegates to
  `shared/embeddings/openai_embedding_provider.py` (OpenAI
  `text-embedding-3-large`) — implemented, no SDK import in this file itself.
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
  Now also carries `computation_inputs`/`parsed_query_inputs`/`assumptions`
  (personal-tax free-text extraction) and `uncited_sections` (computation
  citations).
- `graphs/query_graph.py` — **fully implemented.** The LangGraph
  `StateGraph` wiring the full sequence: `classify_intent → resolve_temporal
  → (computation [→ ground_truth_check → computation_citations] | retrieval →
  narrate → evidence_gate) → assemble_response → audit_log`. A computation is
  triggered, in priority order, by an explicit `computation_request`, an
  uploaded document, or (for personal-tax queries specifically) inputs parsed
  straight out of the query text via `services/query/input_extractor.py` —
  see `_infer_rule_name`'s `states_income()` check, which takes priority over
  the generic corporate `regime_comparison` keyword match precisely because
  "which regime should I choose" alone is ambiguous between the corporate
  and personal comparisons, and a stated income figure disambiguates
  decisively. `run_query_graph()` builds the initial state from the request,
  invokes the compiled graph, and returns `final_response` merged with the
  persisted audit row's id as `audit_log_id`.
- `graphs/ingestion_graph.py` — the executable version of the
  ingestion-pipeline diagram: dedup → parse → embed → upsert. Untouched by
  this round of work — the admin upload endpoint
  (`app/api/admin.py`) currently calls the ingestion services directly
  rather than through this graph; worth reconciling at some point so there's
  one ingestion entrypoint, not two.
- `nodes/assemble_response.py` — **implemented.** Builds the final
  `{answer, citations, computation_trace, gate_status, as_of_date, ...}`
  object from whichever branch ran; a missing-computation-data result becomes
  an explicit `FLAGGED` response naming what's missing (or, for personal-tax,
  a natural clarifying question) rather than a guess. `personal_regime_comparison`
  gets a dedicated narrative renderer (old vs new regime figures, breakeven
  point, deciding factors) since its output doesn't read well through the
  generic key:value renderer every other rule uses.
- `nodes/computation_citations.py` — **new.** Resolves the statutory sections
  a computation trace cited (`ComputationTrace.statutory_references`, itself
  merged from each `TraceStep.section_reference`) into verbatim citations via
  `graph_store.citations_for_sections()`, so a computation-only answer still
  returns real, checkable sources instead of `citations: []`. These are
  verified by construction (never pass through an LLM) and skip the Evidence
  Gate. Runs after `ground_truth_check` for every successfully computed
  result — distinct from that node, which cross-checks the applied *rate*,
  not provenance. `uncited_sections` surfaces whichever cited sections the
  graph couldn't resolve (today, that's every personal-tax section — the
  graph holds committed rules for Sec 80C/80D/24(b) but zero for
  115BAC/87A/16(ia)) rather than silently returning fewer citations.
- `nodes/audit_log_node.py` — **implemented.** Writes the insert-only
  `AuditLog` row (first real writes to this table) — `citations` is stored
  via Prisma's `Json(...)` wrapper (required for JSON-typed fields in
  prisma-client-py, not just a raw dict/list). A write failure is logged
  loudly but never sinks an otherwise-good answer: the response still reaches
  the user with `audit_log_id: ""`.

### `app/services/analysis/` — ITR return analysis (**new top-level package**)

Recomputes a filed personal-tax return from its own declared inputs, diffs
the result against what was actually filed, and scores the discrepancies —
distinct from `services/query/`'s forward computation (a user asks "what
would I owe"), this is the reverse direction ("here's what I filed, was it
right"). Doesn't fit under `query/`, `computation/`, or `rag/` alone since
it's part pure computation and part retrieval-adjacent extraction, so it's
its own package:
- `itr_extractor.py` — document (a filed return, uploaded as text/PDF) ->
  declared facts, each with the source line it came from.
- `reconciler.py` — **pure, zero I/O.** Recomputes from the declared inputs
  via the same `computation/rules/personal/` rules the forward query path
  uses, diffs against what was actually filed, and emits `Discrepancy`
  objects (type, severity, declared vs. correct figure, cost, source line).
- `penalty_mapper.py` — discrepancy -> statutory penalty, via a Neo4j rule
  graph lookup only (no penalty logic of its own). Currently returns no
  penalties in practice — the graph has no committed personal-tax rules yet
  (see `graph_store.py`'s coverage note) — so `routes.py` always returns
  `penalties: []` today; detection and "where it went wrong" don't depend on
  this and work regardless.
- `ai_score.py` — **pure, deterministic.** Discrepancies -> an accuracy and
  risk score. No LLM anywhere in this package: it never decides whether a
  return is wrong, never picks a penalty, and never computes the score --
  those are arithmetic and graph lookups. An LLM only narrates the result,
  upstream in the frontend/orchestration layer.
- `routes.py` — `POST /api/v1/personal-tax/analyze-return`: upload a filed
  return, get back the discrepancies (each tagged with its source line) plus
  the AI score. Wiring only, same as `services/query/routes.py` is wiring
  over the query graph — no detection logic lives in this file.

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
- **Knowledge-graph extraction (Neo4j)**: not in the original diagram at all.
  `services/ingestion/kg_graph_extraction/` + `shared/graph/neo4j_client.py`
  propose and (depending on `GRAPH_AUTO_APPROVE`) auto-commit statutory rules
  into a Neo4j graph, backed by the `GraphRuleProposal`/`ProposalStatus` and
  `Document`/`DocumentStatus` Prisma models. This is now the system's second
  knowledge source alongside the Pinecone `statutory-kg` namespace, read back
  on the query side by both `retriever/graph_store.py` (RRF fusion) and
  `ground_truth_gate.py` (the computation path's cross-check) — the diagram
  should be updated to show it.
- **No user-facing document upload yet**: only the admin console can ingest
  documents into the permanent `statutory-kg` namespace
  (`POST /admin/documents/upload`). The `user-docs` Pinecone namespace and
  `services/rag/external_research/session_documents.py` are reserved for a
  regular-user *statutory-search* upload flow that doesn't exist yet —
  building it is a distinct feature (auth model, storage, namespace
  routing), not a small addition to the admin upload path. This is separate
  from the per-query `uploaded_document_text` flow below, which is about
  extracting a single query's own computation inputs, not adding to the
  searchable knowledge base.
- **Structured financial-figure extraction — partial**: a caller can still
  supply `computation_inputs` directly on the request (no parsing involved),
  and for capital gains specifically, a caller can instead attach
  `uploaded_document_text` and let `services/rag/extraction/document_extraction.py`
  LLM-extract + evidence-span-verify the needed fields (dates, consideration,
  cost figures) from it. Every other rule (MAT, AMT, regime comparison,
  depreciation) still has no extraction path — a caller must supply
  `computation_inputs` for those directly. Generalizing document extraction
  to the other rules, and reliable table extraction from arbitrary P&L/
  balance-sheet layouts, remain open.
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
| A new document type to parse (e.g. .pptx)             | `services/ingestion/parsing/<new>_parser.py`             |
| A change to how citations are verified                | `services/rag/evidence_gate.py`                          |
| A change to the LLM prompt / citation mandate         | `services/rag/prompts/`                                  |
| A second LLM provider (e.g. as the real fallback)     | `shared/llm/fallback_provider.py` only                   |
| A new field on the audit row                          | `prisma/schema.prisma` (`AuditLog`) + `shared/schemas/audit_entry.py` |
| A change to the query flow's sequencing               | `orchestration/graphs/query_graph.py`                    |
| A new API endpoint under `/api/v1/...`                | `services/query/routes.py` (or a new `services/<domain>/routes.py`) |
| A new admin dashboard endpoint                        | `app/api/admin.py`                                       |
| A new organization (tenant)                           | Add to `SEED_ORGS` list in `app/main.py`                 |
| A new admin-specific JWT operation                    | `app/core/security.py` (follow existing admin token pattern) |
| A new rule-proposal / graph-extraction source          | `services/ingestion/kg_graph_extraction/`                |
| A new vector-store backend (replacing/adding to Pinecone) | `shared/vector/<new>_client.py` (rewrite `retriever/vector_store.py` to call it) |
| A change to how a query gets routed to computation vs. retrieval | `services/query/intent_classifier.py` (keep it deterministic — no LLM) |
| A change to vector retrieval (Pinecone)                | `services/rag/retriever/vector_store.py`                  |
| A change to structured/graph retrieval (Neo4j)          | `services/rag/retriever/graph_store.py`                   |
| A change to the computation ground-truth cross-check   | `services/rag/ground_truth_gate.py`                       |
| Wiring Cost Inflation Index data into indexed capital gains (currently unwired) | `services/computation/cii_tables.py` + `services/computation/rules/capital_gains.py` |
| Extending document-upload extraction to a rule other than capital gains | `services/rag/extraction/document_extraction.py` + `services/rag/prompts/extraction_prompts.py` |
| A user-facing (non-admin) *statutory-search* document upload endpoint | New — doesn't exist yet; see the `user-docs` namespace note in §5 |
| A new personal-tax deduction/rebate/slab rule            | `services/computation/rules/personal/` (`slab_tables.py` for rate data) |
| A change to how personal-tax inputs get parsed from free text | `services/query/input_extractor.py`                    |
| A change to how a computed trace's citations get resolved | `orchestration/nodes/computation_citations.py` + `services/rag/retriever/graph_store.py`'s `citations_for_sections` |
| A new ITR discrepancy check / penalty mapping             | `services/analysis/reconciler.py` / `services/analysis/penalty_mapper.py` |

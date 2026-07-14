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

**Query pipeline** — a user's question comes in at
`POST /api/v1/{domain}/query` (the diagram shows a concrete example,
`POST /api/corporate-tax/query`). A deterministic intent classifier (no LLM)
decides whether the query needs the **computation engine**, the **retrieval
pipeline**, or both. Computation queries pull structured figures out of
Postgres (parsed P&L / balance sheet / GSTR fields) and run them through pure
Python rule functions (MAT, regime comparison, depreciation, capital gains,
etc.), producing an exact, auditable `computation_trace`. Retrieval queries
go through a hybrid retriever (vector + keyword search) to pull statutory
chunks, hand them to Claude — **the only LLM touchpoint in the entire
system** — to draft a narrative with citation tags, and then run every
citation through an **Evidence Gate** that verifies it against what was
actually retrieved. Unverifiable claims are stripped and the response is
flagged for human review, never silently dropped. Response Assembly merges
the gated narrative, the computation engine's exact numbers, and verified
citations into one JSON response, and an insert-only Audit Log row is written
before the response goes back to the user.

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
│   ├── shared/             cross-cutting schemas + the LLM provider abstraction
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

This is the wall around the diagram's "Claude — Sonnet 5, ONLY LLM TOUCHPOINT
IN SYSTEM" box.
- `base.py` — the `LLMProvider` interface every provider implements
  (`generate(system_prompt, messages, temperature=0)`).
- `anthropic_provider.py` — the **only file in the whole codebase** allowed
  to import the Anthropic SDK. Hardcodes `temperature=0`.
- `fallback_provider.py` — a second provider, same interface, for when Claude
  is down/times out.
- `router.py` — tries Claude, falls back on failure, and logs which provider
  actually served the response for the audit trail.
- `config.py` — API keys / model names, kept separate from `app/core/config.py`.

**Never** import an LLM SDK anywhere else. If you're adding a new provider,
it's a new file in this folder implementing `LLMProvider` — no other file
changes.

### `app/services/query/` — the entrypoint

- `routes.py` — `POST /api/v1/{domain}/query` (the diagram's
  `/api/corporate-tax/query` is one instance of this pattern, with
  `domain="corporate-tax"`).
- `intent_classifier.py` — the diagram's "Intent Classifier (deterministic,
  no LLM)" box. Routes each query to computation, retrieval, or both. This
  must stay rule/keyword-based — it is a control-flow decision, and the LLM
  never makes control-flow decisions in this system.
- `temporal_resolver.py` — resolves the as-of date / Assessment Year / regime
  before anything else runs, branching on the two pivot dates.

### `app/services/computation/` — the deterministic rules engine

Everything the diagram calls the "Deterministic Computation Engine." **Zero
I/O rule**: nothing under `rules/` (or `engine.py`) may import the database,
an LLM client, or an HTTP client. The caller fetches data (e.g. the parsed
P&L/balance-sheet/GSTR figures the diagram shows coming out of Postgres) and
passes it in as plain values.
- `engine.py` — dispatches a rule name to the right function in `rules/`.
- `rules/mat.py`, `rules/amt.py`, `rules/regime_comparison.py`,
  `rules/depreciation.py`, `rules/capital_gains.py` — one pure function per
  statutory computation (Sec 115JB, Sec 115JC, Sec 115BAA/115BAB, Schedule
  III/WDV, date-split capital gains). **Add a new tax computation here.**
- `cii_tables.py` — versioned Cost Inflation Index lookup.
- `computation_trace.py` — builds the diagram's "computation_trace (every
  step tagged w/ statutory section) + final numeric results" object.
- `validators.py` — enforces "no estimated figures" — every number going
  into a rule must be sourced, never an LLM guess.

### `app/services/rag/` — retrieval, narration, citation verification

- `retriever/vector_store.py`, `retriever/keyword_store.py`,
  `retriever/hybrid_retriever.py` — the diagram's "Hybrid Retriever" fanning
  out to the vector DB and the structured/keyword DB, fused with Reciprocal
  Rank Fusion.
- `evidence_gate.py` — the diagram's "Evidence Gate" diamond. Verifies every
  citation Claude produced against the chunks actually retrieved for *this*
  query. Verified → `gate_status = VERIFIED`. Unverifiable → the claim is
  stripped and the response is flagged for human review — never silently dropped.
- `confidence.py` — calibrated confidence score (retrieval score + source
  tier + cross-chunk agreement).
- `llm_client.py` — the only file under `services/` allowed to import from
  `shared/llm/`. Calls `router.get_llm_provider()`, never a provider module
  directly.
- `prompts/` — system prompts and the citation-mandate instructions given to
  Claude (grounding-only: it may never answer outside retrieved content).
- `external_research/allowlist.py` — the government domains ingestion is
  allowed to pull from (`incometax.gov.in`, `cbic-gst.gov.in`,
  `egazette.gov.in`, `mca.gov.in`).
- `external_research/session_documents.py` — retrieval scoped to one user's
  uploaded documents, kept separate from the permanent knowledge graph.

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
  system through.**
- `upsert/user_docs_upsert.py` — writes into the session-scoped namespace.
  Never mixed with the statutory KG namespace.

### `app/orchestration/` — wiring only, no business logic

This package's only job is control flow — it calls into `services/*` and
manages state; it must never contain a statutory rule, a prompt, or a
retrieval algorithm itself.
- `state.py` — the shared state schema threaded through every graph node.
- `graphs/query_graph.py` — the LangGraph `StateGraph` wiring the full
  sequence: intent classify → temporal resolve → (computation engine |
  hybrid retriever → llm_client → evidence gate) → assemble_response →
  audit_log_node.
- `graphs/ingestion_graph.py` — the executable version of the
  ingestion-pipeline diagram: dedup → parse → embed → upsert.
- `nodes/assemble_response.py` — the diagram's "Response Assembly" box.
- `nodes/audit_log_node.py` — writes the insert-only Audit Log row.

---

## 5. Where this scaffold differs from the diagram (read before building further)

- **Vector store**: the diagram specifies **Pinecone** with two namespaces
  (`statutory-kg`, `user-docs`). The current `vector_store.py` stub assumes
  pgvector-via-Postgres instead, to avoid adding a new client/dependency
  during scaffolding.
- **Gate status naming**: the diagram's Evidence Gate uses
  `VERIFIED` / `REVIEW_REQUIRED`. The current `GateStatus` enum uses
  `VERIFIED` / `FLAGGED` / `PARTIAL`. Reconcile before wiring `evidence_gate.py`.
- **Embedding provider**: the diagram specifies OpenAI `text-embedding-3-large`.
  `ingestion/embedding.py` deliberately has no SDK import yet. Decide whether
  embeddings get their own provider-isolated module (e.g.
  `shared/embeddings/openai_embedding_provider.py`) before implementing.

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

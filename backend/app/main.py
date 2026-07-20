import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# INFO-level so the [FLOW] debug logs in orchestration/graphs/query_graph.py
# (which node fired, which external service was hit -- Pinecone/Neo4j/OpenAI/
# Postgres/pure-computation -- and what it returned) print to the console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# RequestTimingMiddleware logs one line per request carrying method, path,
# status AND where the time went, which is a superset of uvicorn's access line
# -- leaving both on prints every request twice. Uvicorn's loggers set
# propagate=False and own their handlers, so disabling this logger is the
# lever that works; a root-level change would not touch it.
logging.getLogger("uvicorn.access").disabled = True

from app.api.admin import router as admin_router
from app.shared.graph.neo4j_client import get_neo4j_client
from app.api.admin_auth import router as admin_auth_router
from app.api.auth import router as auth_router
from app.core.config import get_settings
from app.core.redis import close_redis, connect_redis
from app.core.security import hash_password
from app.db import prisma
from app.middleware import AuthEventLoggingMiddleware, RequestTimingMiddleware
from app.schemas import OrganizationResponse
from app.services.analysis.routes import router as analysis_router
from app.services.query.routes import router as query_router

SEED_ORGS = [
    {"slug": "icmai", "displayName": "ICMAI"},
    {"slug": "intime", "displayName": "INTIME"},
    {"slug": "tax_ai", "displayName": "Tax AI"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prisma.connect()
    await connect_redis()
    get_neo4j_client()

    # Seed organizations
    for org_data in SEED_ORGS:
        existing = await prisma.organization.find_unique(where={"slug": org_data["slug"]})
        if not existing:
            await prisma.organization.create(data=org_data)

    # Seed default admin under "intime"
    intime_org = await prisma.organization.find_unique(where={"slug": "intime"})
    existing_admin = await prisma.admin.find_unique(
        where={"username_organizationId": {"username": "admin", "organizationId": intime_org.id}}
    ) if intime_org else None
    if not existing_admin and intime_org:
            await prisma.admin.create(
                data={
                    "username": "admin",
                    "passwordHash": hash_password("admin"),
                    "organizationId": intime_org.id,
                }
            )

    yield
    await get_neo4j_client().close()
    await close_redis()
    await prisma.disconnect()


settings = get_settings()
app = FastAPI(title="TaxAI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.frontend_origin).rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthEventLoggingMiddleware)
# Registered last => outermost (Starlette applies middleware in reverse order),
# so the measured total covers the whole stack including the middleware above.
app.add_middleware(RequestTimingMiddleware)

app.mount("/public", StaticFiles(directory="public"), name="public")
app.include_router(auth_router)
app.include_router(admin_auth_router, prefix="/admin/auth")
app.include_router(admin_router, prefix="/admin")
app.include_router(query_router)
app.include_router(analysis_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations():
    orgs = await prisma.organization.find_many(order={"displayName": "asc"})
    return [
        OrganizationResponse(id=o.id, slug=o.slug, display_name=o.displayName)
        for o in orgs
    ]

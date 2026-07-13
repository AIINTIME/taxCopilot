from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.core.config import get_settings
from app.core.redis import close_redis, connect_redis
from app.db import prisma
from app.middleware import AuthEventLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prisma.connect()
    await connect_redis()
    yield
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

app.mount("/public", StaticFiles(directory="public"), name="public")
app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

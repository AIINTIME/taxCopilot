from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.core.security import (
    create_admin_access_token,
    create_admin_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db import prisma
from app.schemas import AdminAuthResponse, AdminLoginRequest, AdminRegisterRequest, AdminResponse

router = APIRouter(tags=["admin-auth"])
bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_REFRESH_COOKIE = "taxai_admin_refresh_token"
ADMIN_ACCESS_COOKIE = "taxai_admin_access_token"


def serialize_admin(admin) -> AdminResponse:
    return AdminResponse(
        id=admin.id,
        username=admin.username,
        organization_id=admin.organizationId,
        created_at=admin.createdAt,
    )


def set_admin_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = int(timedelta(days=settings.refresh_token_days).total_seconds())
    response.set_cookie(
        key=ADMIN_REFRESH_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/admin",
    )


def set_admin_access_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = int(timedelta(minutes=settings.access_token_minutes).total_seconds())
    response.set_cookie(
        key=ADMIN_ACCESS_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/admin",
    )


def clear_admin_access_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=ADMIN_ACCESS_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/admin",
    )


def clear_admin_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=ADMIN_REFRESH_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/admin",
    )


async def store_admin_refresh_token(
    redis: Redis, token_id: str, admin_id: str, settings: Settings
) -> None:
    ttl = int(timedelta(days=settings.refresh_token_days).total_seconds())
    await redis.setex(f"admin_refresh:{token_id}", ttl, admin_id)


async def issue_admin_tokens(
    admin_id: str, response: Response, redis: Redis, settings: Settings
) -> str:
    access_token = create_admin_access_token(admin_id)
    refresh_token, refresh_token_id = create_admin_refresh_token(admin_id)
    await store_admin_refresh_token(redis, refresh_token_id, admin_id, settings)
    set_admin_access_cookie(response, access_token, settings)
    set_admin_refresh_cookie(response, refresh_token, settings)
    return access_token


async def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    payload = getattr(request.state, "admin_token_payload", None)
    token = credentials.credentials if credentials else None
    if payload is None and token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token"
        )

    if payload is None and token is not None:
        try:
            payload = decode_token(token, "admin_access")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
            ) from exc

    admin = await prisma.admin.find_unique(where={"id": payload["sub"]})
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found"
        )
    return admin


@router.post("/register", response_model=AdminAuthResponse, status_code=status.HTTP_201_CREATED)
async def register_admin(
    payload: AdminRegisterRequest,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    username = payload.username.lower().strip()

    org = await prisma.organization.find_unique(where={"id": payload.organization_id})
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization"
        )

    existing = await prisma.admin.find_unique(
        where={"username_organizationId": {"username": username, "organizationId": org.id}}
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already taken in this organization"
        )

    admin = await prisma.admin.create(
        data={
            "username": username,
            "passwordHash": hash_password(payload.password),
            "organizationId": org.id,
        }
    )
    access_token = await issue_admin_tokens(admin.id, response, redis, settings)
    return AdminAuthResponse(access_token=access_token, admin=serialize_admin(admin))


@router.post("/login", response_model=AdminAuthResponse)
async def login_admin(
    payload: AdminLoginRequest,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    admin = await prisma.admin.find_unique(
        where={
            "username_organizationId": {
                "username": payload.username.lower(),
                "organizationId": payload.organization_id,
            }
        }
    )
    if admin is None or not verify_password(payload.password, admin.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username, password, or organization"
        )

    access_token = await issue_admin_tokens(admin.id, response, redis, settings)
    return AdminAuthResponse(access_token=access_token, admin=serialize_admin(admin))


@router.post("/refresh", response_model=AdminAuthResponse)
async def refresh_admin(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    refresh_token = request.cookies.get(ADMIN_REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    try:
        payload = decode_token(refresh_token, "admin_refresh")
    except ValueError as exc:
        clear_admin_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    token_id = payload.get("jti")
    admin_id = payload["sub"]
    if not token_id:
        clear_admin_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    redis_key = f"admin_refresh:{token_id}"
    stored_admin_id = await redis.get(redis_key)
    if stored_admin_id != admin_id:
        clear_admin_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired"
        )

    await redis.delete(redis_key)
    admin = await prisma.admin.find_unique(where={"id": admin_id})
    if admin is None:
        clear_admin_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found"
        )

    access_token = await issue_admin_tokens(admin.id, response, redis, settings)
    return AdminAuthResponse(access_token=access_token, admin=serialize_admin(admin))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_admin(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    refresh_token = request.cookies.get(ADMIN_REFRESH_COOKIE)
    if refresh_token:
        try:
            payload = decode_token(refresh_token, "admin_refresh")
            token_id = payload.get("jti")
            if token_id:
                await redis.delete(f"admin_refresh:{token_id}")
        except ValueError:
            pass

    clear_admin_refresh_cookie(response, settings)
    clear_admin_access_cookie(response, settings)


@router.get("/me", response_model=AdminResponse)
async def me_admin(admin=Depends(get_current_admin)):
    return serialize_admin(admin)

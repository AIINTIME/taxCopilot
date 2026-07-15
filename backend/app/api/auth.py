from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db import prisma
from app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)
profile_upload_dir = Path("public/uploads/profiles")
allowed_photo_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
max_photo_size = 2 * 1024 * 1024


def serialize_user(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        bio=user.bio,
        profile_photo_url=user.profilePhotoUrl,
        organization_id=user.organizationId,
        is_active=user.isActive,
        created_at=user.createdAt,
    )


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = int(timedelta(days=settings.refresh_token_days).total_seconds())
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth",
    )


async def store_refresh_token(
    redis: Redis, token_id: str, user_id: str, settings: Settings
) -> None:
    ttl = int(timedelta(days=settings.refresh_token_days).total_seconds())
    await redis.setex(f"refresh:{token_id}", ttl, user_id)


async def issue_tokens(
    user_id: str, response: Response, redis: Redis, settings: Settings
) -> str:
    access_token = create_access_token(user_id)
    refresh_token, refresh_token_id = create_refresh_token(user_id)
    await store_refresh_token(redis, refresh_token_id, user_id, settings)
    set_refresh_cookie(response, refresh_token, settings)
    return access_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token"
        )

    try:
        payload = decode_token(credentials.credentials, "access")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc

    user = await prisma.user.find_unique(where={"id": payload["sub"]})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated"
        )
    return user


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    normalized_email = payload.email.lower()
    existing_user = await prisma.user.find_unique(where={"email": normalized_email})
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    org = await prisma.organization.find_unique(where={"id": payload.organization_id})
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization"
        )

    first_admin = await prisma.admin.find_first(where={"organizationId": org.id})
    user = await prisma.user.create(
        data={
            "email": normalized_email,
            "name": payload.name.strip(),
            "passwordHash": hash_password(payload.password),
            "organizationId": org.id,
            "adminId": first_admin.id if first_admin else None,
        }
    )
    request.state.auth_user_id = user.id
    access_token = await issue_tokens(user.id, response, redis, settings)
    return AuthResponse(access_token=access_token, user=serialize_user(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    user = await prisma.user.find_unique(where={"email": payload.email.lower()})
    if (
        user is None
        or not verify_password(payload.password, user.passwordHash)
        or (user.organizationId is not None and user.organizationId != payload.organization_id)
        or not user.isActive
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email, password, or organization"
        )

    request.state.auth_user_id = user.id
    access_token = await issue_tokens(user.id, response, redis, settings)
    return AuthResponse(access_token=access_token, user=serialize_user(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    try:
        payload = decode_token(refresh_token, "refresh")
    except ValueError as exc:
        clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    token_id = payload.get("jti")
    user_id = payload["sub"]
    if not token_id:
        clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    redis_key = f"refresh:{token_id}"
    stored_user_id = await redis.get(redis_key)
    if stored_user_id != user_id:
        clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired"
        )

    await redis.delete(redis_key)
    user = await prisma.user.find_unique(where={"id": user_id})
    if user is None:
        clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    if not user.isActive:
        clear_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated"
        )

    access_token = await issue_tokens(user.id, response, redis, settings)
    return AuthResponse(access_token=access_token, user=serialize_user(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token:
        try:
            payload = decode_token(refresh_token, "refresh")
            token_id = payload.get("jti")
            if token_id:
                await redis.delete(f"refresh:{token_id}")
        except ValueError:
            pass

    clear_refresh_cookie(response, settings)


@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return serialize_user(user)


@router.patch("/profile", response_model=UserResponse)
async def update_profile(payload: UpdateProfileRequest, user=Depends(get_current_user)):
    updated_user = await prisma.user.update(
        where={"id": user.id},
        data={
            "name": payload.name.strip(),
            "bio": payload.bio.strip() if payload.bio else None,
        },
    )
    return serialize_user(updated_user)


@router.post("/profile/photo", response_model=UserResponse)
async def upload_profile_photo(
    request: Request,
    photo: UploadFile = File(...),
    user=Depends(get_current_user),
):
    extension = allowed_photo_types.get(photo.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo must be a JPEG, PNG, or WebP image",
        )

    content = await photo.read()
    if len(content) > max_photo_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo must be 2 MB or smaller",
        )

    profile_upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{user.id}-{uuid4().hex}{extension}"
    destination = profile_upload_dir / filename
    destination.write_bytes(content)

    photo_url = str(request.url_for("public", path=f"uploads/profiles/{filename}"))
    updated_user = await prisma.user.update(
        where={"id": user.id},
        data={"profilePhotoUrl": photo_url},
    )
    return serialize_user(updated_user)


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest, user=Depends(get_current_user)
):
    if not verify_password(payload.current_password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(payload.new_password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different",
        )

    await prisma.user.update(
        where={"id": user.id},
        data={"passwordHash": hash_password(payload.new_password)},
    )

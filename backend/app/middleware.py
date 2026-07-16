from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.security import decode_token
from app.db import prisma


class CookieJWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        access_token = request.cookies.get(settings.access_cookie_name)
        admin_access_token = request.cookies.get("taxai_admin_access_token")

        if access_token:
            try:
                request.state.user_token_payload = decode_token(access_token, "access")
            except ValueError:
                request.state.user_token_payload = None

        if admin_access_token:
            try:
                request.state.admin_token_payload = decode_token(
                    admin_access_token, "admin_access"
                )
            except ValueError:
                request.state.admin_token_payload = None

        return await call_next(request)


class AuthEventLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.url.path in {"/auth/login", "/auth/register"}:
            try:
                await prisma.autheventlog.create(
                    data={
                        "action": request.url.path.rsplit("/", 1)[-1],
                        "status": response.status_code,
                        "success": 200 <= response.status_code < 400,
                        "ipAddress": request.client.host if request.client else None,
                        "userAgent": request.headers.get("user-agent"),
                        "userId": getattr(request.state, "auth_user_id", None),
                    }
                )
            except Exception:
                pass

        return response

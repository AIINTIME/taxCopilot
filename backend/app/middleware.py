from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import prisma


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

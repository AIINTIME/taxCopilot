import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.request_timing import (
    clear_request,
    format_timings,
    start_request,
)
from app.core.security import decode_token
from app.db import prisma

logger = logging.getLogger("app.request")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """One line per request: method, path, status, total, and where the time went.

    Registered LAST in main.py so it is outermost (Starlette applies middleware
    in reverse order of registration) and measures the whole stack, including
    the other middleware.
    """

    async def dispatch(self, request: Request, call_next):
        spans = start_request()
        started = time.perf_counter()
        status = 500  # an unhandled exception never reaches a response object
        handler_ms = 0.0
        try:
            handler_started = time.perf_counter()
            response = await call_next(request)
            handler_ms = (time.perf_counter() - handler_started) * 1000
            status = response.status_code
            return response
        finally:
            total_ms = (time.perf_counter() - started) * 1000
            # Everything outside the handler: the middleware stack, routing,
            # request/response plumbing. Tiny in practice -- surfaced so the
            # numbers visibly account for the whole request rather than
            # leaving an unexplained gap.
            framework_ms = max(0.0, total_ms - handler_ms)
            logger.info(
                "%s %s %s in %.0fms (%s)",
                request.method,
                request.url.path,
                status,
                total_ms,
                format_timings(spans, total_ms, framework_ms),
            )
            # Spans are per request; leaving them set would leak into whatever
            # task reuses this context.
            clear_request()


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

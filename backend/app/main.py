import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, oauth, accounts, scan, incidents, dashboard, reports, content, admin, profile
from app.core.config import settings
from app.core.csrf import issue_csrf, valid_csrf
from app.services.scheduler import start_scheduler, stop_scheduler


logging.basicConfig(level=logging.INFO)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logging.exception("Unhandled error request_id=%s", request_id)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path in {"/docs", "/redoc", "/openapi.json"}:
            csp = (
                "default-src 'self'; connect-src 'self' http://localhost:8000; "
                "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
            )
        else:
            csp = (
                "default-src 'self'; connect-src 'self' http://localhost:8000; "
                "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'"
            )
        response.headers["Content-Security-Policy"] = csp
        logging.info(
            "%s %s %.2fms request_id=%s",
            request.method, request.url.path,
            (time.perf_counter() - start) * 1000, request_id,
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

STATE_CHANGING = {"POST", "PATCH", "PUT", "DELETE"}
CSRF_EXEMPT = {
    "/api/auth/login", "/api/auth/register", "/api/auth/refresh", "/api/auth/logout",
    "/api/oauth/mastodon/callback", "/health",
}

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in STATE_CHANGING and request.url.path not in CSRF_EXEMPT:
            if not valid_csrf(
                request.cookies.get("csrf_token"),
                request.headers.get("X-CSRF-Token"),
            ):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        response = await call_next(request)
        if not request.cookies.get("csrf_token") and request.method in {"GET", "HEAD", "OPTIONS"}:
            response.set_cookie(
                "csrf_token", issue_csrf(), httponly=False,
                secure=settings.cookie_secure, samesite=settings.cookie_samesite,
                max_age=86400, path="/",
            )
        return response

app.add_middleware(CSRFMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name, "version": "1.1.0"}

app.include_router(auth.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(scan.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(
    profile.router,
    prefix="/api",
)
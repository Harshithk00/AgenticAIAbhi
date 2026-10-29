"""FastAPI application entry point.  Run with:  uvicorn app.main:app --reload"""

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .api import auth, dashboard, emails, tasks
from .config import Settings, get_settings
from .database import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smart_email")


class RedactOAuthQuery(logging.Filter):
    """Keep the OAuth authorization code out of uvicorn's access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and str(args[2]).startswith("/api/auth/google/callback?"):
            record.args = (*args[:2], "/api/auth/google/callback?[redacted]", *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(RedactOAuthQuery())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()  # creates the SQLite tables on first start
        yield

    app = FastAPI(title="Smart Email Management Using Agentic AI", version="1.0.0", lifespan=lifespan)

    session_secret = settings.session_secret
    if not session_secret:
        session_secret = secrets.token_urlsafe(32)
        log.warning("SESSION_SECRET is not set: using a random one, so sessions reset on every restart.")

    if not settings.token_encryption_key:
        log.error("TOKEN_ENCRYPTION_KEY is not set: Gmail cannot be connected until you add it to backend/.env.")

    # Signed session cookie: holds only the account id and the OAuth state/PKCE verifier, never tokens.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="smart_email_session",
        max_age=7 * 24 * 3600,
        same_site="lax",
        https_only=settings.session_https_only,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "oauth_configured": settings.google_oauth_configured,
            "gemini_configured": bool(settings.gemini_api_key),
        }

    for router in (auth.router, emails.router, tasks.router, dashboard.router):
        app.include_router(router)
    return app


app = create_app()

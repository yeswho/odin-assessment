import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.ai.providers import build_provider
from app.api.routes import router
from app.core.config import Settings
from app.core.database import create_database
from app.core.errors import AppError
from app.repositories.work_items import WorkItemRepository
from app.services.work_items import WorkItemService

logger = logging.getLogger("odin")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, sessions = create_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await engine.dispose()

    app = FastAPI(title="Odin Work Intake", version="1.0.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.service = WorkItemService(
        WorkItemRepository(sessions), build_provider(settings), settings
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        # Bound request bytes even when Content-Length is missing or untrusted.
        if request.method in {"POST", "PATCH", "PUT"}:
            chunks = bytearray()
            async for chunk in request.stream():
                chunks.extend(chunk)
                if len(chunks) > 65536:
                    return error_response(
                        request, 413, "BODY_TOO_LARGE", "Request body must be at most 64 KiB."
                    )
            request._body = bytes(chunks)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(request, status, code, message):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "requestId": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Avoid echoing potentially sensitive input or arbitrary request bodies.
        fields = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return error_response(request, 422, "VALIDATION_ERROR", fields)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error(
            "database_failure request_id=%s type=%s", request.state.request_id, type(exc).__name__
        )
        return error_response(
            request,
            503,
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable. Please try again.",
        )

    app.include_router(router)
    return app


app = create_app()

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    archaeology,
    architecture_history,
    code,
    github_context,
    graph,
    health,
    history,
    investigation,
    repositories,
    system,
)
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logging.getLogger("ctm").info("application_start")
    yield
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()
    logging.getLogger("ctm").info("application_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    # DEBUG does not enable traceback responses, which could disclose configuration.
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_exception_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")
    app.include_router(archaeology.router, prefix="/api")
    app.include_router(repositories.router, prefix="/api")
    # Register fixed historical file routes before the Phase 2 catch-all file path route.
    app.include_router(history.router, prefix="/api")
    app.include_router(github_context.router, prefix="/api")
    app.include_router(architecture_history.router, prefix="/api")
    app.include_router(investigation.router, prefix="/api")
    app.include_router(graph.router, prefix="/api")
    app.include_router(code.router, prefix="/api")
    return app


app = create_app()

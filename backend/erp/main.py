"""FastAPI application: the ERP's REST API for the Next.js front end and outside systems."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from .api import auth, catalog, finance, integration, inventory, partners, promotions, purchasing, reports, sales
from .api import settings as settings_api
from .config import Settings, get_settings
from .db import make_session_factory
from .services.common import DomainError


def create_app(session_factory: sessionmaker | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="ERP API",
        version="1.0.0",
        description="Inventory, purchasing, sales, finance and reporting. "
                    "The `/api/integration/v1` routes are for outside systems (client-credentials tokens).",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(settings.database_url, settings.serverless)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(DomainError)
    def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, catalog, partners, inventory, purchasing, sales, promotions, finance, reports, settings_api,
                   integration):
        app.include_router(module.router)
    return app

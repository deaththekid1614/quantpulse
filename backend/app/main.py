"""FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.log_config import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("quantpulse.app")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.0.1",
        description="Post-Market Intelligence & Forecasting Platform",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    @app.on_event("startup")
    def _on_startup() -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        log.info("%s starting (env=%s)", settings.app_name, settings.app_env)

    @app.get("/")
    def root() -> dict:
        return {
            "app": settings.app_name,
            "status": "ok",
            "docs": "/docs",
        }

    return app


app = create_app()

"""FastAPI entrypoint for the backend service."""

from fastapi import FastAPI

from src.config import load_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Financial Research Assistant",
        version="0.1.0",
    )
    app.state.settings = load_settings()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

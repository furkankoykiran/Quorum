"""FastAPI application factory for the Quorum Observatory API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import debates, live, payout, runner, shapley


def create_app() -> FastAPI:
    app = FastAPI(
        title="Quorum Observatory API",
        version="0.1.0",
        description="Read-only adapter over runner jsonl artefacts.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(debates.router)
    app.include_router(shapley.router)
    app.include_router(runner.router)
    app.include_router(payout.router)
    app.include_router(live.router)
    return app


app = create_app()

"""FastAPI application factory for the Quorum Observatory API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.exceptions import HTTPException

from .routers import debates, live, payout, runner, shapley


def create_app() -> FastAPI:
    app = FastAPI(
        title="Quorum Observatory API",
        version="0.1.0",
        description="Read-only adapter over runner jsonl artefacts.",
    )
    
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://quorum.arcehub.com",
        "http://quorum.arcehub.com",
    ]
    env_origins = os.environ.get("ALLOWED_ORIGINS", "")
    if env_origins:
        allowed_origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(debates.router, prefix="/api")
    app.include_router(shapley.router, prefix="/api")
    app.include_router(runner.router, prefix="/api")
    app.include_router(payout.router, prefix="/api")
    app.include_router(live.router)
    
    dist_dir = Path(__file__).parent.parent.parent / "apps" / "web" / "dist"
    
    if dist_dir.exists():
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")
        
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            path = dist_dir / full_path
            if path.is_file():
                return FileResponse(path)
            index_path = dist_dir / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="Not Found")

    return app

app = create_app()

"""AIHF Web — a web API and UI over the aihf (ai-hedge-fund) engine.

    uvicorn app.main:app --host 127.0.0.1 --port 8000

There is no authentication: this is a local, single-user tool. Keep it
bound to localhost.
"""

from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Importing verbose from langchain root module")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import config  # noqa: E402
from app.api import router  # noqa: E402
from app.services import settings  # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    settings.startup()
    app = FastAPI(
        title="AIHF Web", version=config.APP_VERSION,
        description="Mandates, backtests and paper funds over the aihf engine. Educational use only.",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            """Serve the built UI; unknown paths get index.html for client routing."""
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            target = (FRONTEND_DIST / path).resolve()
            if path and target.is_file() and FRONTEND_DIST in target.parents:
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()

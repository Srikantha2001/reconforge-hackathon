"""ReconForge FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import actors, audit, breaks, configs, loops, runs, seed

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ReconForge API",
    description=(
        "Author reconciliations from natural language, run them deterministically, "
        "and resolve breaks with agents that explain themselves and never guess."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider}


app.include_router(actors.router)
app.include_router(configs.router)
app.include_router(runs.router)
app.include_router(breaks.router)
app.include_router(loops.router)
app.include_router(audit.router)
app.include_router(seed.router)

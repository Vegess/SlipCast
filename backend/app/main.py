import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, engine
from app.routers import advice, analytics, auth, data, github, live, projects, tasks, team

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_for_production()
    if settings.auto_create_tables and engine.url.get_backend_name() == "sqlite":
        # Local convenience only; Postgres schemas are managed by Alembic.
        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="SlipCast API",
    version="1.7.0",
    description="Delivery analytics for software teams: flow metrics, scored forecasts and write-time slip risk.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-SlipCast-Key"],
    expose_headers=["Content-Disposition"],  # lets the web app name downloaded exports
)

for r in (
    auth.router,
    team.router,
    projects.router,
    tasks.router,
    data.router,
    analytics.router,
    advice.router,
    live.router,
    github.router,
):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}

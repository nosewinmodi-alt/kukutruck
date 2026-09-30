import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register tables)
from .config import settings
from .db import Base, engine
from .routers import auth, integrations, lender, market, operations, reports, vet

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "production" and ("change-me" in (settings.secret_key + settings.callback_secret)):
        raise RuntimeError("Set SECRET_KEY and CALLBACK_SECRET before running in production")
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    if settings.environment != "production":
        Base.metadata.create_all(engine)  # dev/test only; production uses Alembic (see README)
    yield


app = FastAPI(title="KukuTrack API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"],
)
for r in (auth.router, operations.router, reports.router, lender.router, market.router, vet.router, integrations.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


_fe = Path(__file__).resolve().parents[2] / "frontend"
if _fe.exists():
    app.mount("/", StaticFiles(directory=_fe, html=True), name="web")

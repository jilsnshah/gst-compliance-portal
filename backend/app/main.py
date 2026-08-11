from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import Base, engine
from app.models import *  # noqa: F401,F403  (register every table)
from app.api.routes import (
    auth,
    cases,
    conversations,
    dashboard,
    discussion,
    documents,
    gstr3b,
    masters,
    queries,
    recon,
)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    auth, masters, cases, documents, queries, discussion, conversations, recon, gstr3b, dashboard
):
    app.include_router(module.router)


@app.on_event("startup")
def on_startup():
    # Dev stage: create tables directly. Stage 2 switches to Alembic migrations.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}

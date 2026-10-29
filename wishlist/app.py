"""HTTP API and static frontend for the wishlist."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from wishlist.config import ConfigSource
from wishlist.store import PledgeStore

USERNAME_MAX_CHARS = 40
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Pledge(BaseModel):
    """A request to pledge or withdraw under a username."""

    username: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_username(value)


def normalize_username(raw: str) -> str:
    """Collapse whitespace and enforce the length limit on a username."""
    username = " ".join(raw.split())
    if not username:
        raise ValueError("username is empty")
    if len(username) > USERNAME_MAX_CHARS:
        raise ValueError(f"username is longer than {USERNAME_MAX_CHARS} characters")
    return username


def create_app(config_path: Path, db_path: Path) -> FastAPI:
    """Build the application around a config file and a pledge database."""
    config = ConfigSource(config_path)
    store = PledgeStore(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        config.load()
        store.open()
        yield
        store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    def require_item(item_id: str) -> None:
        if not config.load().has_item(item_id):
            raise HTTPException(status_code=404, detail="no such item")

    @app.get("/api/wishlist")
    def get_wishlist() -> dict:
        wishlist = config.load()
        givers = store.givers_by_item()
        return {
            "title": wishlist.title,
            "subtitle": wishlist.subtitle,
            "preview_chars": wishlist.preview_chars,
            "want": {"min": wishlist.want_min, "max": wishlist.want_max},
            "items": [
                {
                    "id": item.id,
                    "label": item.label,
                    "description": item.description,
                    "want": item.want,
                    "givers": givers.get(item.id, []),
                }
                for item in wishlist.items
            ],
        }

    @app.post("/api/items/{item_id}/pledges", status_code=204)
    def add_pledge(item_id: str, pledge: Pledge) -> None:
        require_item(item_id)
        store.add(item_id, pledge.username)

    @app.delete("/api/items/{item_id}/pledges", status_code=204)
    def remove_pledge(item_id: str, pledge: Pledge) -> None:
        require_item(item_id)
        store.remove(item_id, pledge.username)

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def app_from_env() -> FastAPI:
    """Build the application from WISHLIST_CONFIG and WISHLIST_DB."""
    return create_app(
        Path(os.environ.get("WISHLIST_CONFIG", "config.toml")),
        Path(os.environ.get("WISHLIST_DB", "data/wishlist.db")),
    )

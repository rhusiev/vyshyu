"""HTTP API and static frontend for the wishlist."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from starlette.middleware.sessions import SessionMiddleware

from vyshyu.auth import GoogleVerifier, InvalidCredentialError, google_verifier
from vyshyu.config import ConfigSource, Item
from vyshyu.store import Giver, NameTakenError, Store

USERNAME_MAX_CHARS = 40
SESSION_MAX_AGE_S = 400 * 24 * 60 * 60
SESSION_SUB_KEY = "google_sub"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@dataclass(frozen=True)
class Settings:
    """Where the app keeps its files, and how Google sign-in is set up."""

    config_path: Path
    db_path: Path
    google_client_id: str | None = None
    secret_key: str | None = None
    secure_cookies: bool = True


def normalize_username(raw: str) -> str:
    """Collapse whitespace and enforce the length limit on a username."""
    username = " ".join(raw.split())
    if not username:
        raise ValueError("username is empty")
    if len(username) > USERNAME_MAX_CHARS:
        raise ValueError(f"username is longer than {USERNAME_MAX_CHARS} characters")
    return username


class Pledge(BaseModel):
    """Who pledges. Signed-in visitors may leave it out - their reserved name is used."""

    username: str | None = None

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        return None if value is None else normalize_username(value)


class Username(BaseModel):
    """A name to reserve for the signed-in account."""

    username: str

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_username(value)


class GoogleCredential(BaseModel):
    """The ID token the "Sign in with Google" button hands to the page."""

    credential: str


def item_view(item: Item, givers: list[Giver]) -> dict:
    """Shape an item and its givers for the API."""
    return {
        "id": item.id,
        "label": item.label,
        "description": item.description,
        "want": item.want,
        "givers": [{"username": g.username, "protected": g.is_protected} for g in givers],
    }


def create_app(settings: Settings, verify_google: GoogleVerifier | None = None) -> FastAPI:
    """Build the application. verify_google defaults to checking tokens with Google."""
    if settings.google_client_id and not settings.secret_key:
        raise ValueError("Google sign-in needs a secret key to sign session cookies")
    if settings.google_client_id and verify_google is None:
        verify_google = google_verifier(settings.google_client_id)
    config = ConfigSource(settings.config_path)
    store = Store(settings.db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        config.load()
        store.open()
        yield
        store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        # Without Google sign-in nothing is stored in the session, so a throwaway key is fine
        secret_key=settings.secret_key or secrets.token_urlsafe(),
        max_age=SESSION_MAX_AGE_S,
        https_only=settings.secure_cookies,
    )

    def signed_in_sub(request: Request) -> str | None:
        return request.session.get(SESSION_SUB_KEY)

    def session_view(request: Request) -> dict:
        sub = signed_in_sub(request)
        return {
            "google_client_id": settings.google_client_id,
            "signed_in": sub is not None,
            "username": store.username_of(sub) if sub else None,
        }

    def pledger(request: Request, item_id: str, pledge: Pledge) -> str:
        if not config.load().has_item(item_id):
            raise HTTPException(status_code=404, detail="no such item")
        sub = signed_in_sub(request)
        if sub:
            username = store.username_of(sub)
            if username is None:
                raise HTTPException(status_code=409, detail="choose a name first")
            return username
        if pledge.username is None:
            raise HTTPException(status_code=422, detail="username is required")
        if store.is_reserved(pledge.username):
            raise HTTPException(status_code=403, detail="this name is reserved")
        return pledge.username

    @app.get("/api/vyshyu")
    def get_vyshyu() -> dict:
        wishlist = config.load()
        givers = store.givers_by_item()
        return {
            "title": wishlist.title,
            "subtitle": wishlist.subtitle,
            "preview_chars": wishlist.preview_chars,
            "default_language": wishlist.default_language,
            "want": {"min": wishlist.want_min, "max": wishlist.want_max},
            "groups": [
                {
                    "id": group.id,
                    "label": group.label,
                    "folded": group.is_folded,
                    "items": [item_view(item, givers.get(item.id, [])) for item in group.items],
                }
                for group in wishlist.groups
            ],
        }

    @app.post("/api/items/{item_id}/pledges", status_code=204)
    def add_pledge(request: Request, item_id: str, pledge: Pledge) -> None:
        store.add(item_id, pledger(request, item_id, pledge))

    @app.delete("/api/items/{item_id}/pledges", status_code=204)
    def remove_pledge(request: Request, item_id: str, pledge: Pledge) -> None:
        store.remove(item_id, pledger(request, item_id, pledge))

    @app.get("/api/usernames/{username}")
    def get_username(username: str) -> dict:
        return {"reserved": store.is_reserved(username)}

    @app.get("/api/session")
    def get_session(request: Request) -> dict:
        return session_view(request)

    @app.post("/api/session/google")
    def sign_in(request: Request, body: GoogleCredential) -> dict:
        if verify_google is None:
            raise HTTPException(status_code=404, detail="Google sign-in is not enabled")
        try:
            request.session[SESSION_SUB_KEY] = verify_google(body.credential)
        except InvalidCredentialError as exc:
            raise HTTPException(status_code=401, detail="invalid Google credential") from exc
        return session_view(request)

    @app.put("/api/session/username")
    def reserve_username(request: Request, body: Username) -> dict:
        sub = signed_in_sub(request)
        if sub is None:
            raise HTTPException(status_code=401, detail="not signed in")
        try:
            store.reserve(sub, body.username)
        except NameTakenError as exc:
            raise HTTPException(status_code=409, detail="this name is reserved") from exc
        return session_view(request)

    @app.delete("/api/session", status_code=204)
    def sign_out(request: Request) -> None:
        request.session.clear()

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def app_from_env() -> FastAPI:
    """Build the application from VYSHYU_* and GOOGLE_CLIENT_ID variables."""
    return create_app(
        Settings(
            config_path=Path(os.environ.get("VYSHYU_CONFIG", "config.toml")),
            db_path=Path(os.environ.get("VYSHYU_DB", "data/vyshyu.db")),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID") or None,
            secret_key=os.environ.get("VYSHYU_SECRET_KEY") or None,
            secure_cookies=os.environ.get("VYSHYU_SECURE_COOKIES", "1") != "0",
        )
    )

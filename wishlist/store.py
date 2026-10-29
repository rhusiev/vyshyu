"""SQLite storage for pledges and for the names Google accounts have reserved."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pledges (
    item_id TEXT NOT NULL,
    username TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (item_id, username)
);
CREATE TABLE IF NOT EXISTS accounts (
    google_sub TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE
);
"""


class NameTakenError(Exception):
    """The username is reserved by a different account, or someone else pledged under it."""


@dataclass(frozen=True)
class Giver:
    """A username pledged to an item, and whether a Google account reserved it."""

    username: str
    is_protected: bool


def username_key(username: str) -> str:
    """Return the form used to compare names, so 'Anna' and 'anna' collide."""
    return username.casefold()


class Store:
    """Pledges (a username saying it will gift an item) and reserved names."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open the database and create the schema if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        # SQLite's lower() folds ASCII only, which would let "Аня" and "аня" differ
        self._conn.create_function("username_key", 1, username_key, deterministic=True)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        """Close the database."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def givers_by_item(self) -> dict[str, list[Giver]]:
        """Return the givers of each item, oldest pledge first."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT item_id, username FROM pledges ORDER BY created_at, rowid"
            ).fetchall()
            reserved = {key for (key,) in conn.execute("SELECT username_key FROM accounts")}
        givers: dict[str, list[Giver]] = defaultdict(list)
        for item_id, username in rows:
            givers[item_id].append(Giver(username, username_key(username) in reserved))
        return givers

    def add(self, item_id: str, username: str) -> None:
        """Pledge username to item_id. Pledging twice is a no-op."""
        with self._transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO pledges (item_id, username) VALUES (?, ?)",
                (item_id, username),
            )

    def remove(self, item_id: str, username: str) -> None:
        """Withdraw a pledge. Withdrawing a missing pledge is a no-op."""
        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM pledges WHERE item_id = ? AND username = ?",
                (item_id, username),
            )

    def username_of(self, google_sub: str) -> str | None:
        """Return the name an account reserved, or None if it has not chosen one."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT username FROM accounts WHERE google_sub = ?", (google_sub,)
            ).fetchone()
        return row[0] if row else None

    def is_reserved(self, username: str) -> bool:
        """Return whether any account reserved this name, ignoring case."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT 1 FROM accounts WHERE username_key = ?", (username_key(username),)
            ).fetchone()
        return row is not None

    def reserve(self, google_sub: str, username: str) -> None:
        """Reserve username for an account, moving its pledges if it had another name.

        Raises:
            NameTakenError: another account reserved the name, or pledges were made under
                it by anyone but this account. Those are never taken over.
        """
        key = username_key(username)
        with self._transaction() as conn:
            old = conn.execute(
                "SELECT username FROM accounts WHERE google_sub = ?", (google_sub,)
            ).fetchone()
            if self._is_taken(conn, key, google_sub, old[0] if old else None):
                raise NameTakenError(username)
            conn.execute(
                "INSERT INTO accounts (google_sub, username, username_key) VALUES (?, ?, ?)"
                " ON CONFLICT (google_sub) DO UPDATE"
                " SET username = excluded.username, username_key = excluded.username_key",
                (google_sub, username, key),
            )
            if old and old[0] != username:
                self._move_pledges(conn, old[0], username)

    @staticmethod
    def _is_taken(
        conn: sqlite3.Connection, key: str, google_sub: str, own_name: str | None
    ) -> bool:
        owner = conn.execute(
            "SELECT google_sub FROM accounts WHERE username_key = ?", (key,)
        ).fetchone()
        if owner:
            return owner[0] != google_sub
        foreign_pledge = conn.execute(
            "SELECT 1 FROM pledges WHERE username_key(username) = ? AND username IS NOT ?",
            (key, own_name),
        ).fetchone()
        return foreign_pledge is not None

    @staticmethod
    def _move_pledges(conn: sqlite3.Connection, old: str, new: str) -> None:
        conn.execute(
            "UPDATE OR IGNORE pledges SET username = ? WHERE username = ?", (new, old)
        )
        conn.execute("DELETE FROM pledges WHERE username = ?", (old,))

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._conn is None:
            raise RuntimeError("Store.open() was not called")
        with self._lock, self._conn:
            yield self._conn

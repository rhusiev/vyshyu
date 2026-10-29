"""SQLite storage for who intends to gift which item."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pledges (
    item_id TEXT NOT NULL,
    username TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (item_id, username)
)
"""


class PledgeStore:
    """Pledges: a username saying it will gift an item. No accounts behind them."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open the database and create the schema if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def givers_by_item(self) -> dict[str, list[str]]:
        """Return the usernames pledged to each item, oldest pledge first."""
        rows = self._execute(
            "SELECT item_id, username FROM pledges ORDER BY created_at, rowid"
        )
        givers: dict[str, list[str]] = defaultdict(list)
        for item_id, username in rows:
            givers[item_id].append(username)
        return givers

    def add(self, item_id: str, username: str) -> None:
        """Pledge username to item_id. Pledging twice is a no-op."""
        self._execute(
            "INSERT OR IGNORE INTO pledges (item_id, username) VALUES (?, ?)",
            (item_id, username),
        )

    def remove(self, item_id: str, username: str) -> None:
        """Withdraw a pledge. Withdrawing a missing pledge is a no-op."""
        self._execute(
            "DELETE FROM pledges WHERE item_id = ? AND username = ?",
            (item_id, username),
        )

    def _execute(self, sql: str, params: tuple = ()) -> list[tuple]:
        if self._conn is None:
            raise RuntimeError("PledgeStore.open() was not called")
        with self._lock, self._conn:
            return self._conn.execute(sql, params).fetchall()

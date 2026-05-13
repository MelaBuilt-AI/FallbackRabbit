"""Persistent storage backend for FallbackRabbit chains.

Supports SQLite (default) and in-memory (for testing/ephemeral use).
The storage layer is a thin CRUD wrapper that serializes Chain models to JSON
and stores them in a single ``chains`` table.

Usage::

    from fallbackrabbit.storage import get_storage, StorageBackend

    # Default: SQLite at ~/.fallbackrabbit/chains.db
    store = get_storage()

    # Or specify a path
    store = get_storage("sqlite:///path/to/chains.db")

    # Or in-memory (for tests)
    store = get_storage("memory")

    # CRUD operations
    chain_id = store.create(chain)
    chain = store.get(chain_id)
    store.update(chain_id, chain)
    store.delete(chain_id)
    chains = store.list_all()
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .models import Chain


class StorageError(Exception):
    """Base exception for storage errors."""


class ChainNotFoundError(StorageError):
    """Raised when a chain ID is not found in storage."""


class StorageBackend:
    """Abstract base for storage backends."""

    def create(self, chain: Chain, *, chain_id: str | None = None) -> str:
        raise NotImplementedError

    def get(self, chain_id: str) -> Chain:
        raise NotImplementedError

    def update(self, chain_id: str, chain: Chain) -> Chain:
        raise NotImplementedError

    def delete(self, chain_id: str) -> None:
        raise NotImplementedError

    def list_all(self) -> list[tuple[str, Chain]]:
        raise NotImplementedError

    def exists(self, chain_id: str) -> bool:
        try:
            self.get(chain_id)
            return True
        except ChainNotFoundError:
            return False


class MemoryStorage(StorageBackend):
    """In-memory storage backend (for testing / ephemeral use)."""

    def __init__(self) -> None:
        self._chains: dict[str, Chain] = {}

    def create(self, chain: Chain, *, chain_id: str | None = None) -> str:
        cid = chain_id or uuid.uuid4().hex[:12]
        self._chains[cid] = chain
        return cid

    def get(self, chain_id: str) -> Chain:
        if chain_id not in self._chains:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")
        return self._chains[chain_id]

    def update(self, chain_id: str, chain: Chain) -> Chain:
        if chain_id not in self._chains:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")
        self._chains[chain_id] = chain
        return chain

    def delete(self, chain_id: str) -> None:
        if chain_id not in self._chains:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")
        del self._chains[chain_id]

    def list_all(self) -> list[tuple[str, Chain]]:
        return list(self._chains.items())

    def clear(self) -> None:
        self._chains.clear()


class SqliteStorage(StorageBackend):
    """SQLite-backed persistent storage.

    Stores chains as JSON blobs in a single ``chains`` table with metadata
    columns for fast filtering.
    """

    def __init__(self, db_path: str | Path = "~/.fallbackrabbit/chains.db") -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self.connection
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chains (
                chain_id    TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                provider_count INTEGER NOT NULL,
                rule_count  INTEGER NOT NULL DEFAULT 0,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chains_name
            ON chains(name)
        """)
        conn.commit()

    def _serialize(self, chain: Chain) -> str:
        return chain.model_dump_json()

    def _deserialize(self, data: str) -> Chain:
        return Chain.model_validate_json(data)

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def create(self, chain: Chain, *, chain_id: str | None = None) -> str:
        cid = chain_id or uuid.uuid4().hex[:12]
        now = self._now()
        data = self._serialize(chain)
        conn = self.connection
        try:
            conn.execute(
                "INSERT INTO chains "
                "(chain_id, name, provider_count, rule_count, data, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, chain.name, len(chain.providers), len(chain.fallback_rules), data, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"Chain {cid!r} already exists") from exc
        return cid

    def get(self, chain_id: str) -> Chain:
        conn = self.connection
        row = conn.execute(
            "SELECT data FROM chains WHERE chain_id = ?",
            (chain_id,),
        ).fetchone()
        if row is None:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")
        return self._deserialize(row[0])

    def update(self, chain_id: str, chain: Chain) -> Chain:
        conn = self.connection
        exists = conn.execute(
            "SELECT 1 FROM chains WHERE chain_id = ?",
            (chain_id,),
        ).fetchone()
        if exists is None:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")

        now = self._now()
        data = self._serialize(chain)
        conn.execute(
            "UPDATE chains SET name=?, provider_count=?, rule_count=?, data=?, updated_at=? "
            "WHERE chain_id=?",
            (chain.name, len(chain.providers), len(chain.fallback_rules), data, now, chain_id),
        )
        conn.commit()
        return chain

    def delete(self, chain_id: str) -> None:
        conn = self.connection
        result = conn.execute(
            "DELETE FROM chains WHERE chain_id = ?",
            (chain_id,),
        )
        conn.commit()
        if result.rowcount == 0:
            raise ChainNotFoundError(f"Chain {chain_id!r} not found")

    def list_all(self) -> list[tuple[str, Chain]]:
        conn = self.connection
        rows = conn.execute("SELECT chain_id, data FROM chains ORDER BY created_at").fetchall()
        return [(row[0], self._deserialize(row[1])) for row in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def get_storage(url: str | None = None) -> StorageBackend:
    """Factory function to create a storage backend.

    Args:
        url: Storage URL. Supported formats:
            - ``"memory"`` or ``None`` — in-memory storage (default)
            - ``"sqlite:///path/to/chains.db"`` — SQLite storage
            - ``"sqlite://"``, ``"sqlite"`` — default SQLite path

    Returns:
        StorageBackend instance.
    """
    if url is None or url == "memory":
        return MemoryStorage()

    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///") :]
        return SqliteStorage(path)

    if url in ("sqlite://", "sqlite"):
        return SqliteStorage()

    raise StorageError(f"Unsupported storage URL: {url!r}")


# Default storage instance (lazy, can be replaced for testing)
_default_storage: StorageBackend | None = None


def get_default_storage() -> StorageBackend:
    """Get the default storage instance (singleton)."""
    global _default_storage
    if _default_storage is None:
        _default_storage = MemoryStorage()
    return _default_storage


def set_default_storage(storage: StorageBackend) -> None:
    """Replace the default storage instance (for testing / startup config)."""
    global _default_storage
    _default_storage = storage

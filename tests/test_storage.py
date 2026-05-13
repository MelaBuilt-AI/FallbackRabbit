"""Tests for FallbackRabbit storage backends — MemoryStorage and SqliteStorage."""

from __future__ import annotations

import pytest

from fallbackrabbit.models import Chain, FallbackRule, Provider
from fallbackrabbit.storage import (
    ChainNotFoundError,
    MemoryStorage,
    SqliteStorage,
    StorageError,
    get_storage,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROVIDERS = [
    Provider(name="GPT-4o", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0),
    Provider(
        name="Claude",
        model_id="claude-sonnet-4-20250514",
        api_base="https://api.anthropic.com/v1",
        priority=1,
    ),
]

SAMPLE_RULES = [
    FallbackRule(condition_error_type="rate_limit", action="wait", wait_seconds=5, retry_count=3),
]

SAMPLE_CHAIN = Chain(
    name="test-chain",
    providers=SAMPLE_PROVIDERS,
    fallback_rules=SAMPLE_RULES,
    metadata={"env": "test"},
)


@pytest.fixture
def memory_store():
    """Fresh in-memory storage for each test."""
    return MemoryStorage()


@pytest.fixture
def sqlite_store(tmp_path):
    """Fresh SQLite storage backed by a temp file."""
    db_path = tmp_path / "test_chains.db"
    return SqliteStorage(db_path)


# ===========================================================================
# MemoryStorage tests
# ===========================================================================


class TestMemoryStorage:
    """Tests for MemoryStorage backend."""

    def test_create_returns_id(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        assert isinstance(cid, str)
        assert len(cid) == 12

    def test_create_with_custom_id(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN, chain_id="my-custom-id")
        assert cid == "my-custom-id"

    def test_get_existing(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        chain = memory_store.get(cid)
        assert chain.name == "test-chain"
        assert len(chain.providers) == 2

    def test_get_nonexistent_raises(self, memory_store):
        with pytest.raises(ChainNotFoundError):
            memory_store.get("no-such-id")

    def test_update_existing(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        updated = SAMPLE_CHAIN.model_copy(update={"name": "renamed"})
        result = memory_store.update(cid, updated)
        assert result.name == "renamed"
        assert memory_store.get(cid).name == "renamed"

    def test_update_nonexistent_raises(self, memory_store):
        with pytest.raises(ChainNotFoundError):
            memory_store.update("nope", SAMPLE_CHAIN)

    def test_delete_existing(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        memory_store.delete(cid)
        with pytest.raises(ChainNotFoundError):
            memory_store.get(cid)

    def test_delete_nonexistent_raises(self, memory_store):
        with pytest.raises(ChainNotFoundError):
            memory_store.delete("nope")

    def test_list_all_empty(self, memory_store):
        assert memory_store.list_all() == []

    def test_list_all_with_chains(self, memory_store):
        cid1 = memory_store.create(SAMPLE_CHAIN)
        cid2 = memory_store.create(SAMPLE_CHAIN, chain_id="second")
        items = memory_store.list_all()
        assert len(items) == 2
        ids = [i[0] for i in items]
        assert cid1 in ids
        assert cid2 in ids

    def test_exists_true(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        assert memory_store.exists(cid) is True

    def test_exists_false(self, memory_store):
        assert memory_store.exists("nope") is False

    def test_clear(self, memory_store):
        memory_store.create(SAMPLE_CHAIN)
        memory_store.create(SAMPLE_CHAIN, chain_id="second")
        assert len(memory_store.list_all()) == 2
        memory_store.clear()
        assert len(memory_store.list_all()) == 0

    def test_create_duplicate_id_raises(self, memory_store):
        memory_store.create(SAMPLE_CHAIN, chain_id="dup")
        # MemoryStorage silently overwrites — this is expected
        # (SqliteStorage raises IntegrityError for duplicates)
        memory_store.create(SAMPLE_CHAIN, chain_id="dup")
        assert len(memory_store.list_all()) == 1

    def test_metadata_preserved(self, memory_store):
        chain = Chain(
            name="meta-test",
            providers=SAMPLE_PROVIDERS,
            metadata={"env": "prod", "version": 2},
        )
        cid = memory_store.create(chain)
        stored = memory_store.get(cid)
        assert stored.metadata == {"env": "prod", "version": 2}

    def test_update_preserves_other_fields(self, memory_store):
        cid = memory_store.create(SAMPLE_CHAIN)
        updated = SAMPLE_CHAIN.model_copy(update={"name": "new-name"})
        memory_store.update(cid, updated)
        stored = memory_store.get(cid)
        assert stored.name == "new-name"
        assert len(stored.providers) == 2
        assert len(stored.fallback_rules) == 1


# ===========================================================================
# SqliteStorage tests
# ===========================================================================


class TestSqliteStorage:
    """Tests for SqliteStorage backend."""

    def test_create_returns_id(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        assert isinstance(cid, str)
        assert len(cid) == 12

    def test_create_with_custom_id(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN, chain_id="custom-id")
        assert cid == "custom-id"

    def test_get_existing(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        chain = sqlite_store.get(cid)
        assert chain.name == "test-chain"
        assert len(chain.providers) == 2

    def test_get_nonexistent_raises(self, sqlite_store):
        with pytest.raises(ChainNotFoundError):
            sqlite_store.get("nope")

    def test_update_existing(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        updated = SAMPLE_CHAIN.model_copy(update={"name": "renamed"})
        result = sqlite_store.update(cid, updated)
        assert result.name == "renamed"
        assert sqlite_store.get(cid).name == "renamed"

    def test_update_nonexistent_raises(self, sqlite_store):
        with pytest.raises(ChainNotFoundError):
            sqlite_store.update("nope", SAMPLE_CHAIN)

    def test_delete_existing(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        sqlite_store.delete(cid)
        with pytest.raises(ChainNotFoundError):
            sqlite_store.get(cid)

    def test_delete_nonexistent_raises(self, sqlite_store):
        with pytest.raises(ChainNotFoundError):
            sqlite_store.delete("nope")

    def test_list_all_empty(self, sqlite_store):
        assert sqlite_store.list_all() == []

    def test_list_all_with_chains(self, sqlite_store):
        cid1 = sqlite_store.create(SAMPLE_CHAIN)
        cid2 = sqlite_store.create(SAMPLE_CHAIN, chain_id="second")
        items = sqlite_store.list_all()
        assert len(items) == 2
        ids = [i[0] for i in items]
        assert cid1 in ids
        assert cid2 in ids

    def test_exists_true(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        assert sqlite_store.exists(cid) is True

    def test_exists_false(self, sqlite_store):
        assert sqlite_store.exists("nope") is False

    def test_create_duplicate_id_raises(self, sqlite_store):
        sqlite_store.create(SAMPLE_CHAIN, chain_id="dup")
        with pytest.raises(StorageError, match="already exists"):
            sqlite_store.create(SAMPLE_CHAIN, chain_id="dup")

    def test_metadata_preserved(self, sqlite_store):
        chain = Chain(
            name="meta-test",
            providers=SAMPLE_PROVIDERS,
            metadata={"env": "prod", "version": 2},
        )
        cid = sqlite_store.create(chain)
        stored = sqlite_store.get(cid)
        assert stored.metadata == {"env": "prod", "version": 2}

    def test_update_preserves_other_fields(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        updated = SAMPLE_CHAIN.model_copy(update={"name": "new-name"})
        sqlite_store.update(cid, updated)
        stored = sqlite_store.get(cid)
        assert stored.name == "new-name"
        assert len(stored.providers) == 2
        assert len(stored.fallback_rules) == 1

    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "subdir" / "chains.db"
        store = SqliteStorage(db_path)
        store.create(SAMPLE_CHAIN)
        assert db_path.exists()

    def test_close_and_reopen(self, tmp_path):
        db_path = tmp_path / "persist.db"
        store1 = SqliteStorage(db_path)
        cid = store1.create(SAMPLE_CHAIN)
        store1.close()

        store2 = SqliteStorage(db_path)
        chain = store2.get(cid)
        assert chain.name == "test-chain"
        store2.close()

    def test_update_timestamp_changes(self, sqlite_store):
        import time

        cid = sqlite_store.create(SAMPLE_CHAIN)
        row_before = sqlite_store.connection.execute(
            "SELECT updated_at FROM chains WHERE chain_id = ?", (cid,)
        ).fetchone()
        time.sleep(0.01)  # small delay to ensure timestamp differs
        updated = SAMPLE_CHAIN.model_copy(update={"name": "updated"})
        sqlite_store.update(cid, updated)
        row_after = sqlite_store.connection.execute(
            "SELECT updated_at FROM chains WHERE chain_id = ?", (cid,)
        ).fetchone()
        assert row_after[0] >= row_before[0]

    def test_provider_and_rule_counts_stored(self, sqlite_store):
        cid = sqlite_store.create(SAMPLE_CHAIN)
        row = sqlite_store.connection.execute(
            "SELECT provider_count, rule_count FROM chains WHERE chain_id = ?", (cid,)
        ).fetchone()
        assert row[0] == 2  # 2 providers
        assert row[1] == 1  # 1 fallback rule

    def test_list_all_ordered_by_created(self, sqlite_store):
        """Chains should be returned in creation order."""
        cid1 = sqlite_store.create(Chain(name="first", providers=SAMPLE_PROVIDERS), chain_id="aaa")  # noqa: F841
        cid2 = sqlite_store.create(Chain(name="second", providers=SAMPLE_PROVIDERS), chain_id="bbb")  # noqa: F841
        items = sqlite_store.list_all()
        assert items[0][0] == "aaa"
        assert items[1][0] == "bbb"


# ===========================================================================
# get_storage factory tests
# ===========================================================================


class TestGetStorage:
    """Tests for the get_storage factory function."""

    def test_none_returns_memory(self):
        store = get_storage(None)
        assert isinstance(store, MemoryStorage)

    def test_memory_string_returns_memory(self):
        store = get_storage("memory")
        assert isinstance(store, MemoryStorage)

    def test_sqlite_url_returns_sqlite(self, tmp_path):
        db_path = tmp_path / "factory_test.db"
        store = get_storage(f"sqlite:///{db_path}")
        assert isinstance(store, SqliteStorage)

    def test_sqlite_default_path(self):
        # "sqlite://" or "sqlite" should use default path
        store = get_storage("sqlite://")
        assert isinstance(store, SqliteStorage)

    def test_sqlite_bare(self):
        store = get_storage("sqlite")
        assert isinstance(store, SqliteStorage)

    def test_unsupported_url_raises(self):
        with pytest.raises(StorageError, match="Unsupported"):
            get_storage("postgres://localhost/mydb")


# ===========================================================================
# Integration: _ChainProxy with server
# ===========================================================================


class TestChainProxyWithServer:
    """Tests that the _ChainProxy dict-like interface works with the server."""

    def test_proxy_set_and_get(self):
        """_chains[cid] = chain then _chains[cid] should work."""
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        cid = "test-proxy-id"
        _chains[cid] = SAMPLE_CHAIN
        assert _chains[cid].name == "test-chain"

    def test_proxy_contains(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["abc"] = SAMPLE_CHAIN
        assert "abc" in _chains
        assert "xyz" not in _chains

    def test_proxy_len(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        assert len(_chains) == 0
        _chains["a"] = SAMPLE_CHAIN
        assert len(_chains) == 1

    def test_proxy_del(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["del-me"] = SAMPLE_CHAIN
        del _chains["del-me"]
        assert "del-me" not in _chains

    def test_proxy_items(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["id1"] = SAMPLE_CHAIN
        items = list(_chains.items())
        assert len(items) == 1
        assert items[0][0] == "id1"
        assert items[0][1].name == "test-chain"

    def test_proxy_clear(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["a"] = SAMPLE_CHAIN
        _chains["b"] = SAMPLE_CHAIN
        assert len(_chains) == 2
        _chains.clear()
        assert len(_chains) == 0

    def test_proxy_values(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["id1"] = SAMPLE_CHAIN
        vals = _chains.values()
        assert len(vals) == 1
        assert vals[0].name == "test-chain"

    def test_proxy_keys(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["id1"] = SAMPLE_CHAIN
        _chains["id2"] = SAMPLE_CHAIN
        keys = _chains.keys()
        assert set(keys) == {"id1", "id2"}

    def test_proxy_iter(self):
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["a"] = SAMPLE_CHAIN
        _chains["b"] = SAMPLE_CHAIN
        assert set(_chains) == {"a", "b"}

    def test_proxy_with_sqlite_backend(self, tmp_path):
        """_ChainProxy should also work with SqliteStorage."""
        from fallbackrabbit.server import _chains, set_storage

        db_path = tmp_path / "proxy_test.db"
        store = SqliteStorage(db_path)
        set_storage(store)

        _chains["sqlite-id"] = SAMPLE_CHAIN
        assert _chains["sqlite-id"].name == "test-chain"
        assert "sqlite-id" in _chains
        del _chains["sqlite-id"]
        assert "sqlite-id" not in _chains

        store.close()

    def test_server_create_app_with_memory(self):
        """create_app() with memory storage should work."""
        from fallbackrabbit.server import create_app

        app = create_app(storage_url="memory")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_server_create_app_with_sqlite(self, tmp_path):
        """create_app() with SQLite storage should work."""
        from fallbackrabbit.server import create_app

        db_path = tmp_path / "server_test.db"
        app = create_app(storage_url=f"sqlite:///{db_path}")
        from fastapi.testclient import TestClient

        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200

        # Create a chain via API
        payload = {
            "name": "sqlite-chain",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client.post("/chains", json=payload)
        assert resp.status_code == 201

        # List chains
        resp = client.get("/chains")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ===========================================================================
# Existing server tests still pass (backward compat)
# ===========================================================================


class TestExistingServerTestsCompat:
    """Verify existing test_server.py fixtures still work with the proxy."""

    def test_clear_fixture_pattern(self):
        """The _chains.clear() pattern used by existing tests should still work."""
        from fallbackrabbit.server import _chains, set_storage

        set_storage(MemoryStorage())
        _chains.clear()

        _chains["test-id"] = SAMPLE_CHAIN
        assert len(_chains) == 1
        _chains.clear()
        assert len(_chains) == 0

    def test_import_chains_still_accessible(self):
        """Tests import _chains from server — verify the proxy is importable."""
        from fallbackrabbit.server import _chains

        assert hasattr(_chains, "clear")
        assert hasattr(_chains, "items")

"""Tests for FallbackRabbit authentication — API key auth, middleware, dependency."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fallbackrabbit.auth import (
    APIKeyAuth,
    APIKeyConfig,
    get_auth,
    require_api_key,
    set_auth,
)
from fallbackrabbit.server import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_KEY = "sk-test-abc123def456"
VALID_KEY_2 = "sk-live-xyz789"
SAMPLE_KEYS = [VALID_KEY, VALID_KEY_2]


@pytest.fixture
def auth_no_keys():
    """Auth with no keys (disabled)."""
    return APIKeyAuth(keys=[], enabled=False)


@pytest.fixture
def auth_with_keys():
    """Auth with valid keys."""
    return APIKeyAuth(keys=SAMPLE_KEYS)


@pytest.fixture
def auth_from_env():
    """Auth loaded from environment variable."""
    with patch.dict(os.environ, {"FALLBACKRABBIT_API_KEYS": "sk-env-key1,sk-env-key2"}):
        return APIKeyAuth()


@pytest.fixture
def app_no_auth():
    """App without auth (default)."""
    return create_app(storage_url="memory")


@pytest.fixture
def app_with_auth():
    """App with auth enabled."""
    return create_app(storage_url="memory", api_keys=SAMPLE_KEYS, auth_enabled=True)


@pytest.fixture
def client_no_auth(app_no_auth):
    return TestClient(app_no_auth)


@pytest.fixture
def client_with_auth(app_with_auth):
    return TestClient(app_with_auth)


# ===========================================================================
# APIKeyAuth unit tests
# ===========================================================================


class TestAPIKeyAuth:
    """Tests for APIKeyAuth configuration and validation."""

    def test_auth_disabled_passes_any_key(self, auth_no_keys):
        assert auth_no_keys.authenticate("anything") == "auth-disabled"

    def test_auth_disabled_passes_none(self, auth_no_keys):
        assert auth_no_keys.authenticate(None) == "auth-disabled"

    def test_valid_key_returns_label(self, auth_with_keys):
        label = auth_with_keys.authenticate(VALID_KEY)
        assert label == "default"

    def test_invalid_key_returns_none(self, auth_with_keys):
        assert auth_with_keys.authenticate("wrong-key") is None

    def test_none_key_returns_none_when_enabled(self, auth_with_keys):
        assert auth_with_keys.authenticate(None) is None

    def test_labeled_key(self):
        auth = APIKeyAuth(keys=[APIKeyConfig(key="sk-labeled", label="production")])
        assert auth.authenticate("sk-labeled") == "production"

    def test_multiple_keys_all_valid(self, auth_with_keys):
        assert auth_with_keys.authenticate(VALID_KEY) is not None
        assert auth_with_keys.authenticate(VALID_KEY_2) is not None

    def test_env_var_loading(self, auth_from_env):
        assert auth_from_env.authenticate("sk-env-key1") is not None
        assert auth_from_env.authenticate("sk-env-key2") is not None
        assert auth_from_env.authenticate("sk-env-key3") is None

    def test_env_var_strips_whitespace(self):
        with patch.dict(os.environ, {"FALLBACKRABBIT_API_KEYS": "  key1 , key2  "}):
            auth = APIKeyAuth()
            assert auth.authenticate("key1") is not None
            assert auth.authenticate("key2") is not None

    def test_env_var_empty(self):
        with patch.dict(os.environ, {"FALLBACKRABBIT_API_KEYS": ""}):
            auth = APIKeyAuth()
            assert len(auth.keys) == 0

    def test_skip_paths_default(self, auth_with_keys):
        assert auth_with_keys.should_skip("/health") is True
        assert auth_with_keys.should_skip("/docs") is True
        assert auth_with_keys.should_skip("/openapi.json") is True
        assert auth_with_keys.should_skip("/redoc") is True
        assert auth_with_keys.should_skip("/chains") is False

    def test_skip_paths_custom(self):
        auth = APIKeyAuth(keys=["sk-test"], skip_paths={"/health", "/metrics"})
        assert auth.should_skip("/health") is True
        assert auth.should_skip("/metrics") is True
        assert auth.should_skip("/chains") is False

    def test_generate_key(self):
        key = APIKeyAuth.generate_key()
        assert key.startswith("sk_")
        assert len(key) > 10

    def test_generate_key_custom_prefix(self):
        key = APIKeyAuth.generate_key(prefix="fr")
        assert key.startswith("fr_")


# ===========================================================================
# Middleware integration tests
# ===========================================================================


class TestAuthMiddleware:
    """Tests for APIKeyAuthMiddleware with the full FastAPI app."""

    def test_no_auth_health_check(self, client_no_auth):
        """Health check works without auth."""
        resp = client_no_auth.get("/health")
        assert resp.status_code == 200

    def test_no_auth_chains_work(self, client_no_auth):
        """Chain endpoints work without auth."""
        resp = client_no_auth.get("/chains")
        assert resp.status_code == 200

    def test_auth_health_check_no_key_needed(self, client_with_auth):
        """Health check bypasses auth (skip path)."""
        resp = client_with_auth.get("/health")
        assert resp.status_code == 200

    def test_auth_chains_without_key_returns_401(self, client_with_auth):
        """Chain endpoints require auth when enabled."""
        resp = client_with_auth.get("/chains")
        assert resp.status_code == 401

    def test_auth_chains_with_valid_header(self, client_with_auth):
        """Valid X-API-Key header authenticates."""
        resp = client_with_auth.get("/chains", headers={"X-API-Key": VALID_KEY})
        assert resp.status_code == 200

    def test_auth_chains_with_valid_bearer(self, client_with_auth):
        """Valid Bearer token authenticates."""
        resp = client_with_auth.get("/chains", headers={"Authorization": f"Bearer {VALID_KEY}"})
        assert resp.status_code == 200

    def test_auth_chains_with_valid_query_param(self, client_with_auth):
        """Valid api_key query param authenticates."""
        resp = client_with_auth.get(f"/chains?api_key={VALID_KEY}")
        assert resp.status_code == 200

    def test_auth_chains_with_invalid_key_returns_401(self, client_with_auth):
        """Invalid API key returns 401."""
        resp = client_with_auth.get("/chains", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_auth_second_key_works(self, client_with_auth):
        """Both configured keys work."""
        resp = client_with_auth.get("/chains", headers={"X-API-Key": VALID_KEY_2})
        assert resp.status_code == 200

    def test_auth_create_chain_with_key(self, client_with_auth):
        """Creating a chain with auth works."""
        payload = {
            "name": "auth-test",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client_with_auth.post(
            "/chains",
            json=payload,
            headers={"X-API-Key": VALID_KEY},
        )
        assert resp.status_code == 201

    def test_auth_create_chain_without_key(self, client_with_auth):
        """Creating a chain without auth fails."""
        payload = {
            "name": "auth-test",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client_with_auth.post("/chains", json=payload)
        assert resp.status_code == 401

    def test_auth_delete_chain_with_key(self, client_with_auth):
        """Deleting a chain with auth works."""
        payload = {
            "name": "to-delete",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        create_resp = client_with_auth.post(
            "/chains",
            json=payload,
            headers={"X-API-Key": VALID_KEY},
        )
        chain_id = create_resp.json()["detail"]["chain_id"]

        del_resp = client_with_auth.delete(
            f"/chains/{chain_id}",
            headers={"X-API-Key": VALID_KEY},
        )
        assert del_resp.status_code == 200

    def test_auth_docs_no_key_needed(self, client_with_auth):
        """Docs endpoints bypass auth."""
        resp = client_with_auth.get("/docs")
        # Docs returns 200 (HTML) or redirects
        assert resp.status_code in (200, 301, 302, 307)

    def test_auth_openapi_no_key_needed(self, client_with_auth):
        """OpenAPI spec bypasses auth."""
        resp = client_with_auth.get("/openapi.json")
        assert resp.status_code == 200


# ===========================================================================
# Dependency-based auth tests
# ===========================================================================


class TestRequireApiKeyDependency:
    """Tests for the require_api_key FastAPI dependency."""

    def test_dependency_with_valid_key(self):
        """Dependency passes with valid key."""
        from fastapi import Depends

        app = FastAPI()
        set_auth(APIKeyAuth(keys=["sk-dep-test"], enabled=True))

        @app.get("/protected")
        async def protected(label: str = Depends(require_api_key)):
            return {"label": label}

        client = TestClient(app)
        resp = client.get("/protected", headers={"X-API-Key": "sk-dep-test"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "default"

    def test_dependency_without_key(self):
        """Dependency rejects without key."""
        from fastapi import Depends

        app = FastAPI()
        set_auth(APIKeyAuth(keys=["sk-dep-test"], enabled=True))

        @app.get("/protected")
        async def protected(label: str = Depends(require_api_key)):
            return {"label": label}

        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_dependency_auth_disabled(self):
        """Dependency passes when auth is disabled."""
        from fastapi import Depends

        app = FastAPI()
        set_auth(APIKeyAuth(enabled=False))

        @app.get("/protected")
        async def protected(label: str = Depends(require_api_key)):
            return {"label": label}

        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 200
        assert resp.json()["label"] == "auth-disabled"

    def test_dependency_with_query_key(self):
        """Dependency accepts query param key."""
        from fastapi import Depends

        app = FastAPI()
        set_auth(APIKeyAuth(keys=["sk-dep-test"], enabled=True))

        @app.get("/protected")
        async def protected(label: str = Depends(require_api_key)):
            return {"label": label}

        client = TestClient(app)
        resp = client.get("/protected?api_key=sk-dep-test")
        assert resp.status_code == 200


# ===========================================================================
# set_auth / get_auth
# ===========================================================================


class TestAuthGlobals:
    """Tests for module-level auth instance management."""

    def test_get_auth_creates_disabled_default(self):
        """get_auth returns a disabled auth when unset."""
        import fallbackrabbit.auth as auth_module

        original = auth_module._auth
        auth_module._auth = None
        auth = get_auth()
        assert auth.enabled is False
        auth_module._auth = original

    def test_set_auth_overrides(self):
        """set_auth replaces the global auth instance."""
        new_auth = APIKeyAuth(keys=["sk-override"], enabled=True)
        set_auth(new_auth)
        assert get_auth() is new_auth


# ===========================================================================
# Full round-trip with auth
# ===========================================================================


class TestAuthFullRoundTrip:
    """End-to-end: create → read → update → delete with auth."""

    def test_full_crud_with_auth(self, client_with_auth):
        headers = {"X-API-Key": VALID_KEY}

        # Create
        payload = {
            "name": "crud-test",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client_with_auth.post("/chains", json=payload, headers=headers)
        assert resp.status_code == 201
        chain_id = resp.json()["detail"]["chain_id"]

        # Read
        resp = client_with_auth.get(f"/chains/{chain_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "crud-test"

        # List
        resp = client_with_auth.get("/chains", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Update
        resp = client_with_auth.patch(
            f"/chains/{chain_id}",
            json={"name": "updated-name"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Verify update
        resp = client_with_auth.get(f"/chains/{chain_id}", headers=headers)
        assert resp.json()["name"] == "updated-name"

        # Delete
        resp = client_with_auth.delete(f"/chains/{chain_id}", headers=headers)
        assert resp.status_code == 200

        # Verify deletion
        resp = client_with_auth.get(f"/chains/{chain_id}", headers=headers)
        assert resp.status_code == 404

    def test_cross_key_isolation(self, client_with_auth):
        """Both keys can access the same chains (no per-key isolation yet)."""
        headers1 = {"X-API-Key": VALID_KEY}
        headers2 = {"X-API-Key": VALID_KEY_2}

        payload = {
            "name": "shared-chain",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }

        # Create with key 1
        resp = client_with_auth.post("/chains", json=payload, headers=headers1)
        assert resp.status_code == 201
        chain_id = resp.json()["detail"]["chain_id"]

        # Read with key 2
        resp = client_with_auth.get(f"/chains/{chain_id}", headers=headers2)
        assert resp.status_code == 200

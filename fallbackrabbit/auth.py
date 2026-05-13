"""API key authentication middleware for FallbackRabbit server.

Supports:
- Static API keys (configured at startup via env var or constructor)
- Multiple keys with optional labels (for rotation)
- Per-route skip list (e.g. ``/health`` is unauthenticated by default)
- ``X-API-Key`` header or ``?api_key=`` query param
- Bearer token support (``Authorization: Bearer <key>``)

Usage::

    from fallbackrabbit.auth import APIKeyAuth

    auth = APIKeyAuth(keys=["sk-live-abc123", "sk-test-def456"])

    # With FastAPI
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware, auth=auth)

    # Or use as a dependency
    from fallbackrabbit.auth import require_api_key
    app.get("/chains", dependencies=[Depends(require_api_key)])
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY_ENV_VAR = "FALLBACKRABBIT_API_KEYS"
DEFAULT_SKIP_PATHS: set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}


@dataclass
class APIKeyConfig:
    """A single API key with an optional label."""

    key: str
    label: str = "default"


@dataclass
class APIKeyAuth:
    """API key authentication manager.

    Args:
        keys: List of valid API keys (raw strings or ``APIKeyConfig`` objects).
        skip_paths: URL paths that bypass authentication.
    """

    keys: set[str] = field(default_factory=set)
    key_labels: dict[str, str] = field(default_factory=dict)
    skip_paths: set[str] = field(default_factory=lambda: set(DEFAULT_SKIP_PATHS))
    enabled: bool = True

    def __init__(
        self,
        keys: Sequence[str | APIKeyConfig] | None = None,
        skip_paths: set[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.skip_paths = skip_paths or set(DEFAULT_SKIP_PATHS)
        self.keys = set()
        self.key_labels = {}

        if keys is None:
            # Try env var
            env_keys = os.environ.get(API_KEY_ENV_VAR, "")
            keys = [k.strip() for k in env_keys.split(",") if k.strip()]

        for k in keys:
            if isinstance(k, APIKeyConfig):
                self.keys.add(k.key)
                self.key_labels[k.key] = k.label
            else:
                self.keys.add(k)

    def authenticate(self, api_key: str | None) -> str | None:
        """Validate an API key. Returns the key label or None if invalid.

        If auth is disabled (``enabled=False``), always returns ``"auth-disabled"``.
        """
        if not self.enabled:
            return "auth-disabled"

        if api_key is None or api_key not in self.keys:
            return None

        return self.key_labels.get(api_key, "default")

    def should_skip(self, path: str) -> bool:
        """Check if a path should bypass authentication."""
        return path in self.skip_paths

    @classmethod
    def generate_key(cls, prefix: str = "sk") -> str:
        """Generate a random API key."""
        return f"{prefix}_{secrets.token_urlsafe(32)}"


# ---------------------------------------------------------------------------
# FastAPI Middleware
# ---------------------------------------------------------------------------


class APIKeyAuthMiddleware:
    """ASGI middleware that enforces API key authentication.

    Skips paths listed in ``auth.skip_paths``.
    Checks ``X-API-Key`` header, ``Authorization: Bearer <key>``, and
    ``api_key`` query parameter (in that order).

    Usage::

        auth = APIKeyAuth(keys=["sk-abc123"])
        app.add_middleware(APIKeyAuthMiddleware, auth=auth)
    """

    def __init__(self, app, auth: APIKeyAuth) -> None:
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip auth for whitelisted paths
        if self.auth.should_skip(path):
            await self.app(scope, receive, send)
            return

        # Auth disabled — pass through
        if not self.auth.enabled:
            await self.app(scope, receive, send)
            return

        # Extract API key from headers or query string
        api_key = self._extract_key(scope)

        if self.auth.authenticate(api_key) is None:
            # Build a proper 401 response
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _extract_key(self, scope) -> str | None:
        """Extract API key from headers or query string."""
        # Headers are bytes in ASGI scope
        for key_bytes, val_bytes in scope.get("headers", []):
            key = key_bytes.decode("latin-1") if isinstance(key_bytes, bytes) else key_bytes
            val = val_bytes.decode("latin-1") if isinstance(val_bytes, bytes) else val_bytes
            if key.lower() == "x-api-key":
                return val
            if key.lower() == "authorization" and val.lower().startswith("bearer "):
                return val[7:].strip()

        # Check query string
        qs = scope.get("query_string", b"").decode("latin-1")
        if "api_key=" in qs:
            for part in qs.split("&"):
                if part.startswith("api_key="):
                    return part[8:]

        return None


# ---------------------------------------------------------------------------
# FastAPI Dependency (alternative to middleware)
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key_query = APIKeyQuery(name="api_key", auto_error=False)

# Module-level auth instance (set by server at startup)
_auth: APIKeyAuth | None = None


def set_auth(auth: APIKeyAuth) -> None:
    """Set the module-level auth instance."""
    global _auth
    _auth = auth


def get_auth() -> APIKeyAuth:
    """Get the module-level auth instance (creates a disabled one if unset)."""
    global _auth
    if _auth is None:
        _auth = APIKeyAuth(enabled=False)
    return _auth


async def require_api_key(
    header_key: str | None = Security(_api_key_header),
    query_key: str | None = Security(_api_key_query),
) -> str:
    """FastAPI dependency that requires a valid API key.

    Returns the key label on success, raises 401 on failure.
    Auth-disabled mode always passes.
    """
    auth = get_auth()
    api_key = header_key or query_key
    label = auth.authenticate(api_key)
    if label is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return label

"""Rate limiting middleware for FallbackRabbit server.

Token-bucket rate limiter with:
- Per-IP and global limits
- Configurable windows and burst sizes
- Per-route custom limits
- ``X-RateLimit-*`` response headers
- Skip paths (same as auth)

Usage::

    from fallbackrabbit.ratelimit import RateLimiter, RateLimitMiddleware

    limiter = RateLimiter(requests_per_minute=60, burst=10)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------


@dataclass
class TokenBucket:
    """Single token bucket for one client/IP.

    Args:
        max_tokens: Maximum tokens (burst size).
        refill_rate: Tokens added per second.
    """

    max_tokens: float
    refill_rate: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


@dataclass
class RateLimiter:
    """Configurable rate limiter with per-IP and global limits.

    Args:
        requests_per_minute: Max requests per minute per IP.
        burst: Max burst size per IP.
        global_rpm: Max total requests per minute across all IPs (0 = unlimited).
        global_burst: Max global burst size.
        skip_paths: URL paths that bypass rate limiting.
    """

    requests_per_minute: float = 60
    burst: float = 10
    global_rpm: float = 0  # 0 = no global limit
    global_burst: float = 100
    skip_paths: set[str] = field(
        default_factory=lambda: {"/health", "/docs", "/openapi.json", "/redoc"}
    )

    # Internal state
    _buckets: dict[str, TokenBucket] = field(default_factory=dict, repr=False)
    _global_bucket: TokenBucket | None = field(default=None, repr=False)
    _last_cleanup: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        if self.global_rpm > 0:
            self._global_bucket = TokenBucket(
                max_tokens=self.global_burst,
                refill_rate=self.global_rpm / 60.0,
                tokens=self.global_burst,  # Start with full bucket
            )

    def _get_bucket(self, key: str) -> TokenBucket:
        """Get or create a bucket for a client key."""
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                max_tokens=self.burst,
                refill_rate=self.requests_per_minute / 60.0,
                tokens=self.burst,  # Start with full bucket
            )
        return self._buckets[key]

    def check(self, client_key: str, path: str = "/") -> tuple[bool, dict[str, Any]]:
        """Check if a request is allowed.

        Returns:
            (allowed, headers) where headers include X-RateLimit-* info.
        """
        if path in self.skip_paths:
            return True, self._headers(0, self.burst, self.requests_per_minute)

        # Cleanup old buckets periodically
        self._cleanup()

        # Check global limit first
        if self._global_bucket and not self._global_bucket.consume():
            headers = self._headers(
                0, 0, self.global_rpm, retry_after=self._retry_after(self._global_bucket)
            )
            return False, headers

        # Check per-IP limit
        bucket = self._get_bucket(client_key)
        allowed = bucket.consume()
        headers = self._headers(
            remaining=int(bucket.tokens),
            limit=int(self.burst),
            rpm=int(self.requests_per_minute),
            retry_after=None if allowed else self._retry_after(bucket),
        )
        return allowed, headers

    def _headers(
        self,
        remaining: int,
        limit: int,
        rpm: int,
        retry_after: float | None = None,
    ) -> dict[str, str]:
        """Build rate limit response headers."""
        h = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Window": f"{rpm}rpm",
        }
        if retry_after is not None:
            h["Retry-After"] = str(int(retry_after) + 1)
        return h

    def _retry_after(self, bucket: TokenBucket) -> float:
        """Estimate seconds until a token is available."""
        if bucket.refill_rate <= 0:
            return 60.0
        tokens_needed = 1.0 - bucket.tokens
        return max(0.0, tokens_needed / bucket.refill_rate)

    def _cleanup(self) -> None:
        """Remove stale buckets (inactive for > 5 minutes)."""
        now = time.monotonic()
        if now - self._last_cleanup < 60:  # Only cleanup every 60s
            return
        stale = []
        for key, bucket in self._buckets.items():
            if now - bucket.last_refill > 300:
                stale.append(key)
        for key in stale:
            del self._buckets[key]
        self._last_cleanup = now

    def reset(self) -> None:
        """Reset all buckets (useful for testing)."""
        self._buckets.clear()
        if self._global_bucket:
            self._global_bucket = TokenBucket(
                max_tokens=self.global_burst,
                refill_rate=self.global_rpm / 60.0,
                tokens=self.global_burst,
            )


# ---------------------------------------------------------------------------
# FastAPI Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware:
    """ASGI middleware that enforces rate limiting.

    Usage::

        limiter = RateLimiter(requests_per_minute=60, burst=10)
        app.add_middleware(RateLimitMiddleware, limiter=limiter)
    """

    def __init__(self, app, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        client_key = self._get_client_key(scope)

        allowed, headers = self.limiter.check(client_key, path)

        if not allowed:
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers=headers,
            )
            await response(scope, receive, send)
            return

        # Pass through — rate limit headers are included in 429 responses
        await self.app(scope, receive, send)

    def _get_client_key(self, scope) -> str:
        """Extract client IP from ASGI scope."""
        client = scope.get("client")
        if client:
            return client[0] if isinstance(client, tuple) else str(client)
        return "unknown"

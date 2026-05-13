"""Tests for FallbackRabbit rate limiting — TokenBucket, RateLimiter, middleware."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from fallbackrabbit.ratelimit import RateLimiter, TokenBucket
from fallbackrabbit.server import create_app

# ---------------------------------------------------------------------------
# TokenBucket unit tests
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Tests for the TokenBucket algorithm."""

    def test_initial_tokens_zero(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0)
        assert bucket.tokens == 0.0

    def test_consume_within_burst(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.consume(5) is True
        assert bucket.tokens == 5.0

    def test_consume_exact_burst(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.consume(10) is True
        assert bucket.tokens == 0.0

    def test_consume_exceeds_burst(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=10.0)
        assert bucket.consume(11) is False

    def test_consume_empty_bucket(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=0.0)
        assert bucket.consume(1) is False

    def test_refill_adds_tokens(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=10.0, tokens=0.0)
        bucket.last_refill = time.monotonic() - 1.0  # 1 second ago
        bucket._refill()
        assert bucket.tokens >= 9.0  # ~10 tokens/sec, 1 sec elapsed

    def test_refill_capped_at_max(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=100.0, tokens=5.0)
        bucket.last_refill = time.monotonic() - 10.0  # Long time ago
        bucket._refill()
        assert bucket.tokens == 10.0  # Capped at max

    def test_refill_then_consume(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=10.0, tokens=0.0)
        bucket.last_refill = time.monotonic() - 0.5  # 0.5 seconds ago
        assert bucket.consume(1) is True  # ~5 tokens available

    def test_consume_default_one_token(self):
        bucket = TokenBucket(max_tokens=10, refill_rate=1.0, tokens=5.0)
        assert bucket.consume() is True  # Default 1 token
        assert abs(bucket.tokens - 4.0) < 0.01  # Approximate due to refill timing


# ---------------------------------------------------------------------------
# RateLimiter unit tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for the RateLimiter manager."""

    def test_check_allows_under_limit(self):
        limiter = RateLimiter(requests_per_minute=60, burst=10)
        allowed, headers = limiter.check("127.0.0.1", "/chains")
        assert allowed is True
        assert "X-RateLimit-Limit" in headers

    def test_check_blocks_over_burst(self):
        limiter = RateLimiter(requests_per_minute=60, burst=3)
        # Exhaust the burst
        for _ in range(3):
            limiter.check("127.0.0.1", "/chains")
        # Next request should be blocked
        allowed, headers = limiter.check("127.0.0.1", "/chains")
        assert allowed is False
        assert "Retry-After" in headers

    def test_check_skip_paths(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        limiter.check("127.0.0.1", "/health")
        # Even after one request, health should still pass (skip path)
        allowed, _ = limiter.check("127.0.0.1", "/health")
        assert allowed is True

    def test_check_skip_path_doesnt_consume_tokens(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        # Request to /health (skip path)
        limiter.check("127.0.0.1", "/health")
        # Still have tokens for /chains
        allowed, _ = limiter.check("127.0.0.1", "/chains")
        assert allowed is True

    def test_per_ip_isolation(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        # Exhaust IP 1
        limiter.check("127.0.0.1", "/chains")
        # IP 1 is blocked
        allowed, _ = limiter.check("127.0.0.1", "/chains")
        assert allowed is False
        # IP 2 still has tokens
        allowed, _ = limiter.check("192.168.0.1", "/chains")
        assert allowed is True

    def test_global_limit(self):
        limiter = RateLimiter(requests_per_minute=60, burst=100, global_rpm=60, global_burst=2)
        # Exhaust global burst
        limiter.check("127.0.0.1", "/chains")
        limiter.check("192.168.0.1", "/chains")
        # Third request blocked by global limit
        allowed, _ = limiter.check("10.0.0.1", "/chains")
        assert allowed is False

    def test_no_global_limit(self):
        limiter = RateLimiter(requests_per_minute=60, burst=100, global_rpm=0)
        # Many requests should still pass (no global limit)
        for i in range(50):
            allowed, _ = limiter.check(f"10.0.0.{i}", "/chains")
            assert allowed is True

    def test_headers_structure(self):
        limiter = RateLimiter(requests_per_minute=60, burst=10)
        _, headers = limiter.check("127.0.0.1", "/chains")
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Window" in headers

    def test_retry_after_when_limited(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        limiter.check("127.0.0.1", "/chains")  # Exhaust burst
        allowed, headers = limiter.check("127.0.0.1", "/chains")
        assert allowed is False
        assert "Retry-After" in headers
        retry = int(headers["Retry-After"])
        assert retry > 0

    def test_reset(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1)
        limiter.check("127.0.0.1", "/chains")  # Exhaust
        limiter.reset()
        # Should have tokens again after reset
        # Note: reset clears buckets, next check creates new bucket with full tokens
        allowed, _ = limiter.check("127.0.0.1", "/chains")
        assert allowed is True

    def test_custom_skip_paths(self):
        limiter = RateLimiter(requests_per_minute=60, burst=1, skip_paths={"/health", "/metrics"})
        limiter.check("127.0.0.1", "/chains")  # Exhaust burst
        allowed, _ = limiter.check("127.0.0.1", "/metrics")
        assert allowed is True

    def test_cleanup_removes_stale(self):
        limiter = RateLimiter(requests_per_minute=60, burst=10)
        # Create a bucket
        limiter.check("127.0.0.1", "/chains")
        assert "127.0.0.1" in limiter._buckets
        # Simulate stale by setting last_refill far in the past
        limiter._buckets["127.0.0.1"].last_refill = time.monotonic() - 400
        limiter._last_cleanup = time.monotonic() - 100  # Force cleanup
        # Trigger cleanup via another check
        limiter.check("192.168.0.1", "/chains")
        assert "127.0.0.1" not in limiter._buckets


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware with FastAPI app."""

    def test_no_rate_limit_by_default(self):
        """App without rate limit config works normally."""
        app = create_app(storage_url="memory")
        client = TestClient(app)
        for _ in range(20):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_rate_limit_blocks_excess_requests(self):
        """App with rate limit blocks after burst is exhausted."""
        app = create_app(storage_url="memory", rate_limit_rpm=60, rate_limit_burst=3)
        client = TestClient(app)

        # First 3 should pass
        for _ in range(3):
            resp = client.get("/chains")
            assert resp.status_code == 200

        # 4th should be rate limited
        resp = client.get("/chains")
        assert resp.status_code == 429

    def test_rate_limit_health_not_limited(self):
        """Health endpoint bypasses rate limiting."""
        app = create_app(storage_url="memory", rate_limit_rpm=60, rate_limit_burst=1)
        client = TestClient(app)

        # Exhaust burst on /chains
        client.get("/chains")
        client.get("/chains")  # This should be 429

        # But /health still works
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_rate_limit_with_auth(self):
        """Rate limit + auth both work together."""
        app = create_app(
            storage_url="memory",
            api_keys=["sk-test"],
            auth_enabled=True,
            rate_limit_rpm=60,
            rate_limit_burst=5,
        )
        client = TestClient(app)

        headers = {"X-API-Key": "sk-test"}

        # Authenticated + within rate limit → 200
        resp = client.get("/chains", headers=headers)
        assert resp.status_code == 200

        # Unauthenticated → 401 (auth checked before rate limit in middleware stack)
        resp = client.get("/chains")
        assert resp.status_code == 401

    def test_rate_limit_429_response_body(self):
        """429 response includes error detail."""
        app = create_app(storage_url="memory", rate_limit_rpm=60, rate_limit_burst=1)
        client = TestClient(app)

        client.get("/chains")  # Use the burst
        resp = client.get("/chains")
        assert resp.status_code == 429
        assert "detail" in resp.json()

    def test_different_ips_separate_limits(self):
        """Different clients have separate rate limits."""
        app = create_app(storage_url="memory", rate_limit_rpm=60, rate_limit_burst=2)
        client1 = TestClient(app)

        # Exhaust IP 1
        client1.get("/chains")
        client1.get("/chains")
        resp = client1.get("/chains")
        assert resp.status_code == 429

        # Note: TestClient uses same IP (testclient) so we can't easily
        # test different IPs with TestClient alone. This test verifies
        # the middleware is working; IP isolation is tested at unit level.


# ---------------------------------------------------------------------------
# Combined: auth + rate limit + storage
# ---------------------------------------------------------------------------


class TestCombinedMiddleware:
    """Tests for auth + rate limit + storage working together."""

    def test_full_stack_with_sqlite_auth_ratelimit(self, tmp_path):
        """Full stack: SQLite + auth + rate limit."""
        db_path = tmp_path / "full_stack.db"
        app = create_app(
            storage_url=f"sqlite:///{db_path}",
            api_keys=["sk-full"],
            auth_enabled=True,
            rate_limit_rpm=100,
            rate_limit_burst=20,
        )
        client = TestClient(app)
        headers = {"X-API-Key": "sk-full"}

        # Health check (no auth, no rate limit)
        resp = client.get("/health")
        assert resp.status_code == 200

        # Create chain
        payload = {
            "name": "full-stack-test",
            "providers": [
                {
                    "name": "GPT-4o",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client.post("/chains", json=payload, headers=headers)
        assert resp.status_code == 201
        chain_id = resp.json()["detail"]["chain_id"]

        # Read chain
        resp = client.get(f"/chains/{chain_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "full-stack-test"

        # No auth → 401
        resp = client.get(f"/chains/{chain_id}")
        assert resp.status_code == 401

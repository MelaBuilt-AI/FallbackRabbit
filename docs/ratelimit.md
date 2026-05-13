# Rate Limiting

Built-in token bucket rate limiting for the REST API.

## Configuration

```python
from fallbackrabbit.server import create_app

app = create_app(
    storage_url="memory://",
    rate_limit_per_minute=60,    # Per-IP rate limit
    rate_limit_global=600,        # Global rate limit
    rate_limit_burst=10,         # Burst allowance
)
```

## Default Limits

| Scope | Default | Description |
|-------|---------|-------------|
| Per-IP | 60/min | Requests per IP per minute |
| Global | 600/min | Total requests across all IPs |
| Burst | 10 | Extra requests allowed in burst |

## Response Headers

Rate-limited responses include standard headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1705312800
Retry-After: 30
```

## Skip Paths

These paths skip rate limiting:

- `/health`
- `/docs`
- `/openapi.json`
- `/dashboard`

## 429 Response

When rate limit is exceeded:

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 30
}
```

## Production Settings

For production deployments, consider:

- Lower per-IP limits (30/min) with higher burst (5)
- Higher global limit (1000/min) for multi-user scenarios
- Combine with API key authentication for per-key limits
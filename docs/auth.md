# Authentication

FallbackRabbit supports static API key authentication for the REST API and dashboard.

## Configuration

Set API keys via environment variable or server configuration:

```bash
# Simple: comma-separated keys
export FALLBACKRABBIT_API_KEYS="my-secret-key-1,my-secret-key-2"

# Labeled: name=key pairs
export FALLBACKRABBIT_API_KEYS="admin:sk-admin-123,reader:sk-reader-456"
```

Or programmatically:

```python
from fallbackrabbit.server import create_app

app = create_app(
    storage_url="sqlite:///data/frabbit.db",
    api_keys={"admin": "sk-admin-123", "reader": "sk-reader-456"},
)
```

## Authentication Methods

### X-API-Key Header

```bash
curl -H "X-API-Key: sk-admin-123" http://localhost:8000/chains
```

### Bearer Token

```bash
curl -H "Authorization: Bearer sk-admin-123" http://localhost:8000/chains
```

### Query Parameter

```bash
curl http://localhost:8000/chains?api_key=sk-admin-123
```

## Skip Paths

The following paths skip authentication:

- `/health` — Health check endpoint
- `/docs` — OpenAPI documentation
- `/redoc` — ReDoc documentation
- `/openapi.json` — OpenAPI schema
- `/dashboard` — Dashboard UI (browser access)

## Rate Limiting

API keys can be combined with rate limiting for production use:

```bash
fallbackrabbit serve \
  --storage sqlite:///data/frabbit.db \
  --rate-limit 100/minute
```
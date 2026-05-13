# REST API

FallbackRabbit provides a full REST API for programmatic chain management.

## Starting the Server

```bash
fallbackrabbit serve --port 8000

# With SQLite persistence
fallbackrabbit serve --storage sqlite:///data/frabbit.db

# With API key authentication
FALLBACKRABBIT_API_KEYS="key1:admin,key2:read" fallbackrabbit serve
```

## Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

### Chains

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chains` | Create a chain |
| GET | `/chains` | List all chains |
| GET | `/chains/{id}` | Get a chain |
| PATCH | `/chains/{id}` | Update a chain |
| DELETE | `/chains/{id}` | Delete a chain |
| GET | `/chains/{id}/routing` | Get routing info |
| GET | `/chains/{id}/summary` | Get chain summary |

### Testing

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chains/{id}/test` | Run a test |
| GET | `/test-results/{id}` | Get test results |

### Export

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chains/{id}/export` | Export chain config |
| POST | `/export-template` | Export with custom template |

### Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboard` | Dashboard UI |
| GET | `/dashboard/` | Dashboard UI (trailing slash) |

## Create Chain

```bash
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-chain",
    "providers": [
      {"name": "GPT-4", "model_id": "gpt-4", "priority": 0},
      {"name": "Claude", "model_id": "claude-3-sonnet", "priority": 1}
    ],
    "fallback_rules": [
      {"condition": "rate_limit", "action": "retry", "max_retries": 2},
      {"condition": "timeout", "action": "failover"}
    ]
  }'
```

## Run Test

```bash
curl -X POST http://localhost:8000/chains/{id}/test \
  -H "Content-Type: application/json" \
  -d '{"prompt_count": 5}'
```

## Export

```bash
curl -X POST http://localhost:8000/chains/{id}/export?format=litellm
```
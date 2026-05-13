# Fallback Rules

Fallback rules define how the chain responds to different error types.

## Rule Structure

```yaml
fallback_rules:
  - condition: rate_limit
    action: retry
    max_retries: 2
    wait_ms: 1000
  - condition: timeout
    action: failover
  - condition: auth_error
    action: fail
```

## Conditions (Error Types)

| Condition | Description | Default Status Codes |
|-----------|-------------|---------------------|
| `rate_limit` | Provider rate-limited the request | 429 |
| `timeout` | Request exceeded time limit | 408, 504 |
| `server_error` | Provider returned 5xx | 500, 502, 503 |
| `auth_error` | Authentication failed | 401, 403 |
| `connection_error` | Network/connection failure | — |
| `validation_error` | Request validation failed | 400 |

## Actions

| Action | Description |
|--------|-------------|
| `retry` | Retry the same provider after `wait_ms` |
| `failover` | Try the next provider in priority order |
| `wait` | Wait `wait_ms` then retry the same provider |
| `fail` | Stop — don't try further providers |

## Action Details

### retry
Retries the same provider up to `max_retries` times with `wait_ms` between attempts. After exhausting retries, applies the next matching rule or fails.

```yaml
- condition: rate_limit
  action: retry
  max_retries: 2
  wait_ms: 1000
```

### failover
Immediately tries the next provider in the chain. No waiting, no retries on the current provider.

```yaml
- condition: timeout
  action: failover
```

### wait
Pauses for `wait_ms` then retries the same provider. Useful for temporary outages.

```yaml
- condition: server_error
  action: wait
  wait_ms: 5000
```

### fail
Stops the chain immediately. No further providers are tried.

```yaml
- condition: auth_error
  action: fail
```

## Status Code Matching

Rules can specify exact HTTP status codes for more granular control:

```yaml
- condition: server_error
  status_codes: [502, 503]
  action: failover
- condition: server_error
  status_codes: [500]
  action: retry
  max_retries: 1
```

More specific status code rules take priority over broader condition matches.

## Rule Priority

1. Exact status code match (e.g., `429`)
2. Condition type match (e.g., `rate_limit`)
3. Default behavior: `failover`
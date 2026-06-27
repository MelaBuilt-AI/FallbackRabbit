# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x  | ✅        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities to **security@melabuilt.ai** with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

You will receive a response within 48 hours. If the vulnerability is confirmed, a fix
will be released and credits will be given (if desired).

## Security Features

FallbackRabbit includes several built-in security features:

- **API Key Authentication** — Static key auth with configurable skip paths
- **Rate Limiting** — Token bucket per-IP + global limits with burst control
- **Input Validation** — All API inputs validated via Pydantic models
- **No Secret Storage** — API keys are read from environment variables, never stored

## Best Practices for Deployment

1. **Always set API keys** via environment variables, never hardcode them
2. **Enable rate limiting** in production (`FALLBACKRABBIT_RATE_LIMIT_RPM=60`)
3. **Use API key auth** in any multi-user environment
4. **Run behind a reverse proxy** (nginx, Caddy) with TLS
5. **Use SQLite storage** for persistence (`storage_url=sqlite:///data/chains.db`)
6. **Restrict CORS** to known origins in production
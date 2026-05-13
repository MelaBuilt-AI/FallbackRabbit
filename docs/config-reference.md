# Configuration Reference

## CLI Options

### `fallbackrabbit serve`

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Port number |
| `--storage` | `memory://` | Storage URL (`memory://` or `sqlite:///path.db`) |
| `--reload` | `false` | Enable auto-reload for development |
| `--api-keys` | — | API keys (comma-separated or `label:key` pairs) |
| `--rate-limit` | `60` | Per-IP rate limit per minute |
| `--rate-limit-global` | `600` | Global rate limit per minute |
| `--rate-limit-burst` | `10` | Burst allowance |

### `fallbackrabbit test`

| Flag | Default | Description |
|------|---------|-------------|
| `--prompts` | `5` | Number of test prompts |
| `--outages` | — | Outage scenario file |
| `--verbose` | `false` | Detailed per-prompt results |
| `--real` | `false` | Make real provider calls |

### `fallbackrabbit export`

| Flag | Default | Description |
|------|---------|-------------|
| `--format` | `litellm` | Export format |
| `--output` | stdout | Output file path |
| `--template` | — | Jinja2 template file |
| `--extra-vars` | — | Template variables (`key=value`, repeatable) |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `OLLAMA_BASE_URL` | Ollama base URL (default: `http://localhost:11434`) |
| `FALLBACKRABBIT_API_KEYS` | API keys for authentication |
| `FALLBACKRABBIT_STORAGE_URL` | Default storage URL |

## Export Formats

| Format | Description |
|--------|-------------|
| `litellm` | LiteLLM model config |
| `openrouter` | OpenRouter routing config |
| `langchain` | LangChain router config |
| `haystack` | Haystack pipeline config |
| `custom` | Raw JSON dump |
| `template` | Jinja2 template-based |

## Error Types

| Type | HTTP Codes | Default Action |
|------|-----------|----------------|
| `rate_limit` | 429 | Retry |
| `timeout` | 408, 504 | Failover |
| `server_error` | 500, 502, 503 | Failover |
| `auth_error` | 401, 403 | Fail |
| `connection_error` | — | Failover |
| `validation_error` | 400 | Fail |

## Fallback Actions

| Action | Behavior |
|--------|----------|
| `retry` | Retry same provider (up to `max_retries`) |
| `failover` | Try next provider |
| `wait` | Wait `wait_ms` then retry same provider |
| `fail` | Stop immediately |
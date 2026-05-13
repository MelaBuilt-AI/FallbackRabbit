# 🐇 FallbackRabbit

**Auto-generate, test, and optimize LLM fallback chains.**

When your primary LLM goes down, FallbackRabbit makes sure you fail gracefully — not catastrophically. Build routing chains, simulate outages, measure latency, and export configs for your production stack.

## Features

- **Chain builder** — Define providers, priorities, and fallback rules
- **Simulator** — Run prompts through chains with simulated outages
- **Optimizer** — Auto-reorder chains by latency & success rate
- **Config export** — Export to LiteLLM, LangChain, Haystack, or custom Jinja2 templates
- **Real provider calls** — Test against OpenAI, Anthropic, Azure, Ollama, or custom endpoints
- **REST API** — 15 endpoints for chain CRUD, testing, and export
- **WebSocket** — Live test progress and chain lifecycle events
- **Web dashboard** — Dark-themed SPA at `/dashboard`
- **API key auth** — Static keys with labeled key names
- **Rate limiting** — Token bucket, per-IP + global limits
- **Persistent storage** — In-memory or SQLite backends
- **Rich CLI** — Tables, panels, progress bars via Rich

## Quick Start

```bash
pip install fallbackrabbit

# Create and test a chain
fallbackrabbit create my-chain --provider gpt-4 --provider claude-3 --provider llama3
fallbackrabbit test my-chain --prompt "Hello, world!"
fallbackrabbit optimize my-chain
```

## REST API

```bash
# Start the server
fallbackrabbit serve --port 8000

# Create a chain
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d '{"name": "my-chain", "providers": [{"name": "gpt-4", "model_id": "gpt-4", "api_base": "https://api.openai.com/v1", "priority": 1}]}'

# Test it
curl -X POST http://localhost:8000/chains/{id}/test \
  -d '{"prompts": ["Hello"], "outages": [{"provider": "gpt-4", "error_type": "timeout"}]}'

# Export to LiteLLM config
curl http://localhost:8000/chains/{id}/export?format=litellm
```

## WebSocket

Connect to `/ws` for all events or `/ws/chain/{id}` for chain-specific events:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chain/my-chain");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
// Events: test_progress, test_complete, chain_created, chain_updated, chain_deleted
```

## Dashboard

Open `http://localhost:8000/dashboard` for the built-in SPA. Create chains, run tests with live progress, view results, and export configs — all from the browser.

## CLI Reference

| Command | Description |
|---------|-------------|
| `create` | Create a new fallback chain |
| `list` | List all chains |
| `show` | Show chain details |
| `test` | Run a test simulation |
| `optimize` | Optimize chain order by latency |
| `validate` | Check chain for issues |
| `summarize` | Generate chain summary |
| `export` | Export chain config (litellm/langchain/haystack/template) |
| `serve` | Start the REST API server |

## Architecture

```
Provider → Chain → FallbackRule → Simulator → ChainReport
                                    ↓
                            Real Provider Calls (optional)
                                    ↓
                         Config Export (5 formats)
```

## Requirements

- Python 3.11+
- Dependencies: fastapi, uvicorn, pydantic, click, httpx, rich, pyyaml, jinja2

## License

MIT
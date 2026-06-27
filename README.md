# 🐇 FallbackRabbit

**Auto-generate, test, and optimize LLM fallback chains.**

[![CI](https://github.com/MelaBuilt-AI/FallbackRabbit/actions/workflows/ci.yml/badge.svg)](https://github.com/MelaBuilt-AI/FallbackRabbit/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 556](https://img.shields.io/badge/tests-556-brightgreen.svg)](#)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)

> When your primary LLM goes down, FallbackRabbit makes sure you fail gracefully — not catastrophically. Build routing chains, simulate outages, measure latency, and export configs for your production stack.

## Features

- **🔗 Smart Fallback Chains** — Define priority-ordered provider chains with automatic failover
- **🧪 Simulation Engine** — Run prompts through chains with simulated outages, rate limits, and timeouts
- **⚡ Real Provider Calls** — Test against OpenAI, Anthropic, Azure, Ollama, or custom endpoints
- **📦 Multi-Format Export** — Export to LiteLLM, OpenRouter, LangChain, Haystack, or custom Jinja2 templates
- **🌐 REST API** — 15 endpoints for chain CRUD, testing, export, and import
- **📡 WebSocket** — Live test progress and chain lifecycle events
- **📊 Web Dashboard** — Dark-themed SPA at `/dashboard` — create chains, run tests, export configs
- **🔑 API Key Auth** — Static keys with labeled key names, Bearer token, and query param support
- **⏱️ Rate Limiting** — Token bucket, per-IP + global limits with burst control
- **💾 Persistent Storage** — In-memory or SQLite backends
- **🖥️ Rich CLI** — Tables, panels, progress bars via Rich

## Quick Start

### Install

```bash
pip install fallbackrabbit
# or
uv add fallbackrabbit
```

### CLI Usage

```bash
# Create a starter chain config
fallbackrabbit init my-chain.yaml

# Validate a chain
fallbackrabbit validate my-chain.yaml

# Test a chain with simulated prompts
fallbackrabbit test my-chain.yaml --prompts 10

# Export to LiteLLM config
fallbackrabbit export my-chain.yaml --format litellm --output litellm.yaml

# Start the REST API server
fallbackrabbit serve --port 8000
```

### Python SDK

```python
import asyncio
from fallbackrabbit.models import Chain, Provider, FallbackRule, ErrorType, FallbackAction
from fallbackrabbit.simulator import Simulator, generate_test_prompts

async def main():
    chain = Chain(
        name="production-chain",
        providers=[
            Provider(name="GPT-4", model_id="gpt-4", api_base="https://api.openai.com/v1", priority=0),
            Provider(name="Claude", model_id="claude-3-sonnet", api_base="https://api.anthropic.com", priority=1),
            Provider(name="Llama3", model_id="llama3", api_base="http://localhost:11434", priority=2),
        ],
        fallback_rules=[
            FallbackRule(condition=ErrorType.RATE_LIMIT, action=FallbackAction.RETRY, max_retries=2, wait_seconds=1.0),
            FallbackRule(condition=ErrorType.TIMEOUT, action=FallbackAction.FAILOVER),
        ],
    )

    sim = Simulator(chain=chain)
    prompts = generate_test_prompts(10)
    report = await sim.run_batch(prompts)

    print(f"Success rate: {report.success_rate:.1%}")
    print(f"Average latency: {report.avg_latency_ms:.0f}ms")

asyncio.run(main())
```

### REST API

```bash
# Start the server
fallbackrabbit serve --port 8000

# Create a chain
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d '{"name": "my-chain", "providers": [{"name": "gpt-4", "model_id": "gpt-4", "api_base": "https://api.openai.com/v1", "priority": 1}]}'

# Test it
curl -X POST http://localhost:8000/chains/{id}/test \
  -H "Content-Type: application/json" \
  -d '{"prompts": ["Hello"], "outages": [{"provider": "gpt-4", "error_type": "timeout"}]}'

# Export to LiteLLM config
curl -X POST http://localhost:8000/chains/{id}/export \
  -H "Content-Type: application/json" \
  -d '{"format": "litellm"}'
```

### Docker

```bash
# Build and run
docker compose up -d

# Or build manually
docker build -t fallbackrabbit .
docker run -p 8000:8000 -v ./data:/app/data fallbackrabbit
```

The API will be available at `http://localhost:8000` and the dashboard at `http://localhost:8000/dashboard`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/chains` | Create a new chain |
| GET | `/chains` | List all chains |
| GET | `/chains/{id}` | Get chain details |
| PATCH | `/chains/{id}` | Update a chain |
| DELETE | `/chains/{id}` | Delete a chain |
| GET | `/chains/{id}/routing` | Get routing table |
| GET | `/chains/{id}/summary` | Get chain summary |
| GET | `/chains/{id}/validate` | Validate chain |
| POST | `/chains/{id}/optimize` | Optimize provider order |
| POST | `/chains/{id}/apply-rules` | Apply fallback rules |
| POST | `/chains/{id}/test` | Run test simulation |
| GET | `/chains/{id}/test/single` | Test single prompt |
| POST | `/chains/{id}/export` | Export chain config |
| POST | `/chains/{id}/export/template` | Template-based export |
| GET | `/chains/import` | Import chain from file |
| GET | `/ws` | WebSocket (all events) |
| GET | `/ws/chain/{id}` | WebSocket (per-chain) |
| GET | `/dashboard` | Web dashboard |

## CLI Reference

| Command | Description |
|---------|-------------|
| `init` | Create a starter chain YAML |
| `validate` | Validate a chain config |
| `test` | Run a test simulation |
| `optimize` | Optimize chain order by latency |
| `export` | Export chain (litellm/langchain/haystack/template) |
| `serve` | Start the REST API server |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `FALLBACKRABBIT_API_KEYS` | unset | Comma-separated API keys for auth |
| `FALLBACKRABBIT_RATE_LIMIT_RPM` | unset | Requests per minute limit |
| `FALLBACKRABBIT_RATE_LIMIT_BURST` | unset | Burst limit for rate limiter |
| `FALLBACKRABBIT_STORAGE_URL` | `memory` | Storage URL (`sqlite:///path.db`) |
| `OPENAI_API_KEY` | unset | OpenAI API key for real calls |
| `ANTHROPIC_API_KEY` | unset | Anthropic API key for real calls |

## Examples

Check the [`examples/`](examples/) directory:

- [`basic_chain.py`](examples/basic_chain.py) — Create and test a simple chain
- [`outage_simulation.py`](examples/outage_simulation.py) — Simulate provider outages
- [`export_chain.py`](examples/export_chain.py) — Export to multiple formats
- [`api_usage.py`](examples/api_usage.py) — Use the REST API from Python
- [`load_from_yaml.py`](examples/load_from_yaml.py) — Load chains from YAML

## Documentation

Full documentation is available at [fallbackrabbit.melabuilt.ai](https://fallbackrabbit.melabuilt.ai).

## Architecture

```
Provider → Chain → FallbackRule → Simulator → ChainReport
                                    ↓
                            Real Provider Calls (optional)
                                    ↓
                         Config Export (5 formats + templates)
```

## Development

```bash
# Clone
git clone https://github.com/MelaBuilt-AI/FallbackRabbit.git
cd FallbackRabbit

# Install dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check fallbackrabbit/ tests/

# Build
uv run python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guide.

## Tech Stack

- **FastAPI** — REST API framework
- **Pydantic** — Data validation
- **Click** — CLI framework
- **httpx** — Async HTTP client for real provider calls
- **Rich** — Terminal output
- **Jinja2** — Template-based export
- **PyYAML** — YAML chain config support

## License

MIT — see [LICENSE](LICENSE).

---

Built by [MelaBuilt AI](https://melabuilt.ai) 🐺
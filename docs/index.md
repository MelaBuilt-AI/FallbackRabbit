# FallbackRabbit

Never let your LLM calls fail.

FallbackRabbit generates, tests, and optimizes intelligent fallback chains for any LLM provider. Define your chain once, simulate outages, and export to your framework of choice.

## Why FallbackRabbit?

- **🔍 Smart Fallback Chains** — Priority-ordered provider chains with automatic failover
- **🧪 Simulated Testing** — Test outage scenarios before they happen in production
- **📦 Multi-Format Export** — LiteLLM, OpenRouter, LangChain, Haystack, and custom configs
- **⚡ Live Dashboard** — Dark-themed web UI for chain management and real-time testing
- **🔐 Auth & Rate Limiting** — Production-ready security out of the box
- **🔌 Real Provider Calls** — Test against actual OpenAI, Anthropic, Azure, and Ollama endpoints

## Quick Start

```bash
pip install git+https://github.com/MelaBuilt-AI/FallbackRabbit.git

# Create a chain config
fallbackrabbit init my-chain.yaml

# Validate it
fallbackrabbit validate my-chain.yaml

# Test with simulated outages
fallbackrabbit test my-chain.yaml

# Start the dashboard
fallbackrabbit serve --port 8000
```

## Features at a Glance

| Feature | Description |
|---------|-------------|
| Chain Builder | Build priority-ordered provider chains with validation |
| Simulator | Inject outages, test failover paths, measure latency |
| Export | Output to LiteLLM, OpenRouter, LangChain, Haystack, custom |
| CLI | Full-featured command-line interface |
| REST API | 15+ endpoints for chain CRUD, testing, and export |
| Dashboard | Dark-themed SPA with WebSocket live progress |
| Auth | Static API keys, Bearer tokens, query param auth |
| Rate Limiting | Token bucket, per-IP + global, burst support |
| Storage | In-memory or SQLite persistence |
| WebSocket | Real-time test progress broadcasting |

## License

MIT — use it however you want.
# Changelog

All notable changes to FallbackRabbit will be documented in this file.

## [0.1.0] - 2026-05-12

### Added
- Core data models: Provider, FallbackRule, Chain, PromptSpec, PromptResult, ChainReport, SimulatedOutage
- Chain builder with validation, optimization, and fallback rule application
- Simulator with simulated outages, latency profiles, and batch testing
- Config export: LiteLLM, OpenRouter, LangChain, Haystack, custom Jinja2 templates
- Real provider calls: OpenAI, Anthropic, Azure, Ollama, custom endpoints
- Rich CLI with tables, panels, and progress bars
- FastAPI server: 15 endpoints for chain CRUD, testing, and export
- WebSocket: `/ws` (global) + `/ws/chain/{id}` (per-chain) with live test progress
- Web dashboard: Dark-themed SPA at `/dashboard` with chain CRUD, test runner, and export
- API key authentication: X-API-Key, Bearer, query param, labeled keys
- Rate limiting: Token bucket, per-IP + global, X-RateLimit headers
- Persistent storage: MemoryStorage + SqliteStorage backends
- Status code matching in fallback rules
- Retry/failover timing tracking (retries_used, total_wait_ms)
- CI pipeline: GitHub Actions with ruff, mypy, pytest-cov
- 556 tests passing
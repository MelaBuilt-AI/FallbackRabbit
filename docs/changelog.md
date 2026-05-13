# Changelog

## v0.1.0 (2024-05-13)

### Added

- **Core**: Chain builder, simulator, config export (LiteLLM, OpenRouter, LangChain, Haystack, custom)
- **CLI**: `init`, `validate`, `test`, `export`, `serve`, `analyze` commands
- **REST API**: 15+ endpoints for chain CRUD, testing, and export
- **Dashboard**: Dark-themed SPA with chain CRUD, test runner, export, WebSocket live progress
- **WebSocket**: Real-time test progress broadcasting per chain
- **Auth**: Static API key authentication (header, Bearer, query param)
- **Rate Limiting**: Token bucket with per-IP, global, and burst controls
- **Storage**: In-memory and SQLite backends with thread-safe operations
- **Template Export**: Jinja2 templates with built-in Terraform, Docker, K8s, and .env formats
- **Real Provider Calls**: AsyncProviderClient for OpenAI, Anthropic, Azure, Ollama, custom endpoints
- **Rich CLI**: Tables, panels, progress bars for all commands
- **Testing**: 556 tests across all modules
- **CI**: GitHub Actions with ruff, mypy, pytest-cov on Python 3.11 + 3.12
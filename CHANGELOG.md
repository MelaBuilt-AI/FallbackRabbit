# Changelog

All notable changes to FallbackRabbit are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Docker support (Dockerfile + docker-compose.yml) for self-hosting
- Example scripts in `examples/` directory (5 examples)
- `CONTRIBUTING.md` with development guide
- `CODE_OF_CONDUCT.md` (Contributor Covenant)
- `SECURITY.md` with vulnerability reporting policy
- GitHub issue templates (bug report, feature request)
- GitHub pull request template
- `.gitattributes` for consistent line endings
- `py.typed` marker for PEP 561 type info
- Landing page website for Cloudflare Pages deployment
- Provider chips section on landing page
- Open source section on landing page (replaces fake pricing)
- README badges (CI, Python version, license, tests, code style)
- README Docker quick start section
- README examples section with links
- README environment variable configuration table
- API endpoints reference table in README
- Docker build job in CI pipeline

### Fixed
- Test `test_load_openai_defaults` now properly isolates from `OPENAI_API_KEY` env var leak
- Test `test_load_anthropic_defaults` now properly isolates from `ANTHROPIC_API_KEY` env var leak
- Test `test_load_ollama_defaults` now properly isolates from `OLLAMA_API_KEY` env var leak

### Changed
- README rewritten with badges, better structure, Docker instructions, and examples
- Landing page redesigned — removed fake pricing tiers, added open-source stats and provider grid
- CI pipeline enhanced with Docker build/test stage

## [0.1.0] — 2025-05-13

### Added
- Core data models (Provider, Chain, FallbackRule, PromptResult, ChainReport, SimulatedOutage)
- Chain builder with routing, validation, optimization, and summary generation
- Simulator with async prompt execution, outage injection, latency profiles
- Real provider calls (OpenAI, Anthropic, Azure, Ollama, custom endpoints)
- Config export to LiteLLM, OpenRouter, LangChain, Haystack, and custom formats
- Jinja2 template-based export with built-in templates (Terraform, Docker, K8s, .env)
- FastAPI REST API with 15 endpoints
- WebSocket event streaming with ConnectionManager and ProgressTracker
- Web dashboard (dark-themed SPA)
- API key authentication with middleware
- Rate limiting (token bucket, per-IP + global)
- Persistent storage (MemoryStorage + SqliteStorage)
- Rich CLI with 9 commands
- YAML/JSON chain config loading
- GitHub Actions CI (lint, type check, test, coverage)
- MkDocs Material documentation (18 pages)
- Landing page
- Example YAML configs
- 556 tests covering all functionality
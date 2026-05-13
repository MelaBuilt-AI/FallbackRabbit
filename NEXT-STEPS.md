# FallbackRabbit — NEXT-STEPS.md

## ✅ Completed

- [x] **Project scaffold** — `fallbackrabbit/` package with `__init__.py`, `cli.py`, `models.py`, `chain_builder.py`, `simulator.py`, `config_export.py`
- [x] **pyproject.toml** — project config with all deps
- [x] **Tests directory** — `tests/__init__.py`, `test_models.py`, `test_chain_schema.py`, `test_cli.py`
- [x] **.gitignore** — Python project ignores
- [x] **Core data models (models.py)** — Provider, FallbackRule, Chain, PromptSpec, PromptResult, ChainReport, SimulatedOutage + enums (ErrorType, FallbackAction, ExportFormat)
- [x] **Chain schema (chain_schema.py)** — `load_chain()` and `load_outage_scenario()` with validation
- [x] **Example YAML configs** — `schemas/example_chain.yaml` (3-provider chain) and `schemas/example_outage.yaml`
- [x] **CLI bootstrapping (cli.py)** — `init`, `validate`, `test`, `export`, `serve` commands via Click
- [x] **Chain builder (chain_builder.py)** — `build_routing_chain()`, `apply_fallback_rules()`, `validate_chain()`, `optimize_chain_order()`, `generate_chain_summary()`
- [x] **Simulator (simulator.py)** — `Simulator` class with async `run_prompt()`, `run_batch()`, `inject_outage()`, latency profiles by model type, outage injection, fallback routing
- [x] **Config export (config_export.py)** — `export_litellm()`, `export_openrouter()`, `export_custom()`, `export_langchain()`, `export_haystack()` with file output support
- [x] **CLI wired up** — `test` command runs simulation with rich table output, `export` command uses all export functions, `serve` starts FastAPI server
- [x] **Real provider calls** — `fallbackrabbit/providers.py` with AsyncProviderClient supporting OpenAI, Anthropic, Azure, Ollama, and custom endpoints; `fallbackrabbit/config.py` for provider configuration from env vars; simulator.py updated with `use_real_calls` mode
- [x] **Rich CLI output** — `fallbackrabbit/rich_display.py` with Rich tables, panels, progress bars, styled output; `cli.py` updated to use rich_display for all commands
- [x] **FastAPI server** — REST API for chain CRUD, analysis, testing, and export (15 endpoints, 42 tests, `serve` CLI command)
- [x] **Retry/failover timing** — PromptResult tracks `retries_used` and `total_wait_ms`; WAIT rules accumulate simulated wait time
- [x] **Status code matching** — `condition_status_codes` in FallbackRule matched by simulator; `SimulatedOutage.status_code`; default status code mapping per error type; status-code-specific rules take priority
- [x] **More export formats** — LangChain router config and Haystack pipeline config added; CLI and server export endpoints updated
- [x] **CI pipeline** — GitHub Actions workflow for lint (ruff), type check (mypy), and test with coverage (pytest-cov) on Python 3.11 + 3.12

## 🔜 Next Steps

- [x] **Integration tests** — Full-stack workflows: create→test→export, import→validate→optimize, all-providers-down, cross-format consistency, file round-trips, apply-rules, server CRUD lifecycle, batch outage scenarios, status code matching; 33 tests
- [x] **Custom template-based export** — Jinja2 template rendering with built-in templates (Terraform, Docker Compose, K8s ConfigMap, .env), inline templates, file templates, extra variables, CLI + server support; 33+11 tests
- [x] **Persistent storage** — MemoryStorage + SqliteStorage backends with CRUD, `_ChainProxy` for backward compat, `create_app(storage_url=)` for config, thread-safe SQLite, 56 tests
- [x] **API key authentication** — Static keys, middleware + dependency, X-API-Key header, Bearer token, query param, skip paths, env var loading, labeled keys, 36 tests
- [x] **Rate limiting** — Token bucket, per-IP + global limits, burst, skip paths, X-RateLimit-* headers, Retry-After, cleanup, 28 tests
- [x] **Web dashboard** — Dark-themed SPA at /dashboard, chain CRUD, test runner, export, WebSocket live progress, 26 tests
- [x] **WebSocket support** — Real-time test progress via WebSocket, ConnectionManager, per-chain channels, event broadcasting, ProgressTracker, 34 tests

## 📦 Packaging

- [x] **Polish** — Lint cleanup (ruff all-pass), __init__.py public exports, type safety
- [x] **README.md** — Full project docs (features, install, CLI, API, WebSocket, dashboard)
- [x] **LICENSE** — MIT
- [x] **CHANGELOG.md** — Version history
- [x] **PyPI packaging** — pyproject.toml with metadata/classifiers/keywords, build verified (sdist + wheel)

## 🎯 MVP Complete!

FallbackRabbit v0.1.0 is feature-complete and ready for PyPI publishing.
# FallbackRabbit — NEXT-STEPS.md

## ✅ Completed

- [x] **Project scaffold** — `fallbackrabbit/` package with `__init__.py`, `cli.py`, `models.py`, `chain_builder.py`, `simulator.py`, `config_export.py`
- [x] **pyproject.toml** — project config with all deps
- [x] **Tests directory** — `tests/__init__.py`, `test_models.py`, `test_chain_schema.py`, `test_cli.py`
- [x] **.gitignore** — Python project ignores
- [x] **Core data models (models.py)** — Provider, FallbackRule, Chain, PromptSpec, PromptResult, ChainReport, SimulatedOutage + enums
- [x] **Chain schema (chain_schema.py)** — `load_chain()` and `load_outage_scenario()` with validation
- [x] **Example YAML configs** — `schemas/example_chain.yaml` and `schemas/example_outage.yaml`
- [x] **CLI bootstrapping (cli.py)** — `init`, `validate`, `test`, `export`, `serve` commands via Click
- [x] **Chain builder (chain_builder.py)** — `build_routing_chain()`, `apply_fallback_rules()`, `validate_chain()`, `optimize_chain_order()`, `generate_chain_summary()`
- [x] **Simulator (simulator.py)** — `Simulator` class with async `run_prompt()`, `run_batch()`, `inject_outage()`, latency profiles, outage injection, fallback routing
- [x] **Config export (config_export.py)** — `export_litellm()`, `export_openrouter()`, `export_custom()`, `export_langchain()`, `export_haystack()`
- [x] **CLI wired up** — all commands functional with Rich output
- [x] **Real provider calls** — `AsyncProviderClient` supporting OpenAI, Anthropic, Azure, Ollama, custom
- [x] **Rich CLI output** — tables, panels, progress bars
- [x] **FastAPI server** — 15 REST endpoints, WebSocket, dashboard
- [x] **Retry/failover timing** — `retries_used`, `total_wait_ms`, WAIT rules
- [x] **Status code matching** — `condition_status_codes` in FallbackRule
- [x] **More export formats** — LangChain, Haystack, OpenRouter
- [x] **CI pipeline** — GitHub Actions (lint, type check, test, coverage, Docker build)
- [x] **Integration tests** — 33 tests covering full-stack workflows
- [x] **Custom template-based export** — Jinja2 templates (Terraform, Docker, K8s, .env)
- [x] **Persistent storage** — MemoryStorage + SqliteStorage
- [x] **API key authentication** — Static keys, middleware, Bearer token, query param
- [x] **Rate limiting** — Token bucket, per-IP + global, burst, headers
- [x] **Web dashboard** — Dark-themed SPA with chain CRUD, test runner, export, WebSocket
- [x] **WebSocket support** — Real-time progress, ConnectionManager, per-chain channels
- [x] **Packaging** — Build verified (sdist + wheel), twine check pass
- [x] **README.md** — Full docs with badges, Docker, examples, API reference
- [x] **LICENSE** — MIT
- [x] **CHANGELOG.md** — Version history
- [x] **Dockerfile** — Multi-stage build (slim), healthcheck
- [x] **docker-compose.yml** — Self-hosting config
- [x] **Examples directory** — 5 example scripts
- [x] **CONTRIBUTING.md** — Development guide
- [x] **CODE_OF_CONDUCT.md** — Contributor Covenant
- [x] **SECURITY.md** — Vulnerability reporting
- [x] **GitHub issue/PR templates** — Bug report, feature request, PR template
- [x] **py.typed** — PEP 561 type info marker
- [x] **.gitattributes** — Consistent line endings
- [x] **Landing page** — Polished, open-source focused, no fake pricing
- [x] **Deploy directory** — Cloudflare Pages ready (landing + docs)
- [x] **wrangler.toml** — Cloudflare Pages config
- [x] **GitHub repo public** — https://github.com/MelaBuilt-AI/FallbackRabbit

## 📋 Remaining

- [x] **PyPI publish** — ✅ Live at https://pypi.org/project/fallbackrabbit/0.1.0/
- [x] **Cloudflare Pages deploy** — ✅ Live at fallbackrabbit.melabuilt.ai
- [x] **GitHub repo public** — https://github.com/MelaBuilt-AI/FallbackRabbit
- [x] **PyPI publish workflow** — .github/workflows/publish.yml (needs PYPI_API_TOKEN secret)
- [ ] **OG image** — Social sharing image for landing page
- [ ] **GitHub repo secret** — Add PYPI_API_TOKEN to repo settings for auto-publish workflow
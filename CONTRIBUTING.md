# Contributing to FallbackRabbit

Thanks for your interest in contributing! 🐇

## Getting Started

1. **Fork** the repo and clone your fork
2. **Install** dependencies with `uv sync`
3. **Run tests**: `uv run pytest tests/ -v`
4. **Lint**: `uv run ruff check fallbackrabbit/ tests/`
5. **Create a branch**: `git checkout -b feat/my-feature`

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/FallbackRabbit.git
cd FallbackRabbit

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"
```

## Running Tests

```bash
# Full test suite
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=fallbackrabbit --cov-report=term-missing

# Specific test file
uv run pytest tests/test_simulator.py -v

# Lint
uv run ruff check fallbackrabbit/ tests/

# Type check
uv run mypy fallbackrabbit/ --ignore-missing-imports
```

## Code Style

- **Line length**: 100 chars (enforced by ruff)
- **Type hints**: Required for all public functions
- **Docstrings**: Google style for all public functions and classes
- **Imports**: Sorted by ruff (isort-compatible)
- **Python**: 3.11+ (3.11 and 3.12 tested in CI)

## Pull Request Process

1. **Create an issue** first for significant changes (new features, breaking changes)
2. **Write tests** for any new functionality
3. **Update docs** if you change public API
4. **Ensure CI passes**: all tests, lint, and type checks must be green
5. **Keep PRs focused**: one feature/fix per PR

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new export format for Vercel AI SDK
fix: handle timeout edge case in simulator
docs: update README with Docker instructions
test: add integration test for chain import
refactor: simplify storage backend factory
```

## Project Structure

```
fallbackrabbit/          # Main package
├── models.py            # Pydantic data models
├── chain_builder.py     # Chain building & validation
├── simulator.py         # Test simulation engine
├── providers.py         # Real LLM provider client
├── config.py            # Provider configuration loader
├── config_export.py     # Export to LiteLLM/LangChain/etc
├── template_export.py   # Jinja2 template-based export
├── server.py            # FastAPI REST API
├── storage.py           # Memory & SQLite backends
├── auth.py              # API key authentication
├── ratelimit.py         # Rate limiting middleware
├── websocket.py         # WebSocket event streaming
├── dashboard.py         # Web dashboard mounting
├── dashboard.html        # Dashboard SPA (dark theme)
├── cli.py               # Click CLI commands
├── rich_display.py      # Rich terminal output
└── chain_schema.py      # YAML/JSON chain loading

tests/                   # Test suite (556 tests)
schemas/                 # Example YAML configs
docs/                    # MkDocs documentation
```

## Adding a New Export Format

1. Add the export function in `config_export.py` or `template_export.py`
2. Add the format to the `ExportFormat` enum in `models.py`
3. Wire it up in `server.py` export endpoint
4. Add CLI support in `cli.py`
5. Write tests
6. Update docs

## Adding a New Provider

1. Add provider defaults in `config.py` (`_PROVIDER_DEFAULTS`)
2. Add the API call method in `providers.py` (`AsyncProviderClient`)
3. Add latency profile in `simulator.py` (`_LATENCY_PROFILES`)
4. Write tests
5. Update docs

## Reporting Issues

- **Bugs**: Include reproduction steps, Python version, and OS
- **Features**: Explain the use case and proposed API
- **Security**: Email security@melabuilt.ai (do not open a public issue)

## Code of Conduct

Be kind. Be constructive. Be inclusive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the MIT License.
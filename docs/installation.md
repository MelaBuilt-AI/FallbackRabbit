# Installation

## Requirements

- Python 3.11+
- pip or uv

## Install

```bash
# From GitHub (private repo)
pip install git+https://github.com/MelaBuilt-AI/FallbackRabbit.git

# Or clone and install locally
git clone https://github.com/MelaBuilt-AI/FallbackRabbit.git
cd FallbackRabbit
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

## Verify

```bash
fallbackrabbit --version
fallbackrabbit --help
```

## Running the Server

```bash
# Start with in-memory storage (default)
fallbackrabbit serve

# Start with SQLite persistence
fallbackrabbit serve --storage sqlite:///data/frabbit.db

# Custom host/port
fallbackrabbit serve --host 0.0.0.0 --port 8080
```

## Running Tests

```bash
# Full test suite
pytest

# With coverage
pytest --cov=fallbackrabbit --cov-report=html

# Specific test file
pytest tests/test_simulator.py -v
```
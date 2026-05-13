# Quick Start

## 1. Create a Chain

```bash
fallbackrabbit init my-chain.yaml
```

This generates a starter chain config:

```yaml
name: my-chain
providers:
  - name: GPT-4
    model_id: gpt-4
    priority: 0
    latency_ms: 800
  - name: Claude
    model_id: claude-3-sonnet
    priority: 1
    latency_ms: 600
  - name: Gemini
    model_id: gemini-pro
    priority: 2
    latency_ms: 500

fallback_rules:
  - condition: rate_limit
    action: retry
    max_retries: 2
    wait_ms: 1000
  - condition: timeout
    action: failover
  - condition: server_error
    action: failover
  - condition: auth_error
    action: fail
```

## 2. Validate

```bash
fallbackrabbit validate my-chain.yaml
```

## 3. Test with Simulated Outages

```bash
# Basic test — all providers healthy
fallbackrabbit test my-chain.yaml

# Test with outages
fallbackrabbit test my-chain.yaml --outages outage-scenario.yaml

# Custom prompt count
fallbackrabbit test my-chain.yaml --prompts 20
```

## 4. Export

```bash
# Export to LiteLLM config
fallbackrabbit export my-chain.yaml --format litellm

# Export to LangChain router config
fallbackrabbit export my-chain.yaml --format langchain

# Export to custom template
fallbackrabbit export my-chain.yaml --format template --template terraform.j2

# All formats: litellm, openrouter, langchain, haystack, custom
```

## 5. Dashboard

```bash
fallbackrabbit serve
# Open http://localhost:8000/dashboard
```

The dashboard provides a full UI for creating chains, running tests with live progress, and exporting configs.

## 6. REST API

All functionality is available via the REST API:

```bash
# Create a chain
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d '{"name": "my-chain", "providers": [...], "fallback_rules": [...]}'

# List chains
curl http://localhost:8000/chains

# Run a test
curl -X POST http://localhost:8000/chains/{id}/test \
  -d '{"prompt_count": 5}'

# Export
curl http://localhost:8000/chains/{id}/export?format=litellm
```
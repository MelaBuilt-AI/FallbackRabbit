# Chain Configuration

A chain defines the order of LLM providers and the rules for handling failures.

## Minimal Chain

```yaml
name: my-chain
providers:
  - name: GPT-4
    model_id: gpt-4
    priority: 0
```

## Full Chain

```yaml
name: production-chain
description: "Primary production fallback chain"

providers:
  - name: GPT-4
    model_id: gpt-4
    priority: 0
    latency_ms: 800
    max_output_tokens: 4096
    cost_per_1k_tokens: 0.03
    metadata:
      team: platform
      environment: production

  - name: Claude
    model_id: claude-3-sonnet
    priority: 1
    latency_ms: 600
    max_output_tokens: 4096
    cost_per_1k_tokens: 0.015
    metadata:
      team: platform

  - name: Gemini
    model_id: gemini-pro
    priority: 2
    latency_ms: 500
    max_output_tokens: 2048

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
  - condition: connection_error
    action: failover
    max_retries: 1

test_prompts:
  - "Explain quantum computing in simple terms"
  - "Write a haiku about fallbacks"
  - "What is the capital of France?"
```

## Provider Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Display name |
| `model_id` | string | ✅ | Model identifier (e.g., `gpt-4`, `claude-3-sonnet`) |
| `priority` | int | ✅ | Lower = higher priority (0 = primary) |
| `latency_ms` | int | ❌ | Simulated latency in milliseconds |
| `max_output_tokens` | int | ❌ | Maximum output tokens |
| `cost_per_1k_tokens` | float | ❌ | Cost per 1K tokens (USD) |
| `metadata` | dict | ❌ | Arbitrary key-value metadata |

## Priority Ordering

Providers are tried in priority order (0 first). When a provider fails and the fallback rule says `failover`, the next provider in priority order is used.

## Importing Existing Chains

You can import chains via the REST API or dashboard:

```bash
# From a YAML file
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d @my-chain.yaml

# From JSON
curl -X POST http://localhost:8000/chains \
  -H "Content-Type: application/json" \
  -d '{"name": "...", "providers": [...]}'
```
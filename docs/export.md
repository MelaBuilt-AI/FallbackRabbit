# Export Formats

Export your chain configuration to various framework-specific formats.

## CLI Export

```bash
# LiteLLM config
fallbackrabbit export my-chain.yaml --format litellm

# OpenRouter config
fallbackrabbit export my-chain.yaml --format openrouter

# LangChain router config
fallbackrabbit export my-chain.yaml --format langchain

# Haystack pipeline config
fallbackrabbit export my-chain.yaml --format haystack

# Custom format
fallbackrabbit export my-chain.yaml --format custom

# Write to file
fallbackrabbit export my-chain.yaml --format litellm --output litellm_config.yaml
```

## API Export

```bash
curl http://localhost:8000/chains/{id}/export?format=litellm
```

## LiteLLM

Generates a LiteLLM-compatible config with model list and fallbacks:

```yaml
model_list:
  - model_name: production-chain
    litellm_params:
      model: gpt-4
  - model_name: production-chain
    litellm_params:
      model: claude-3-sonnet
  - model_name: production-chain
    litellm_params:
      model: gemini-pro
fallbacks:
  - production-chain
```

## OpenRouter

Generates an OpenRouter routing config:

```json
{
  "models": {
    "primary": "gpt-4",
    "fallbacks": ["claude-3-sonnet", "gemini-pro"]
  }
}
```

## LangChain

Generates a LangChain router config:

```json
{
  "model_router": {
    "models": [
      {"name": "GPT-4", "model": "gpt-4", "priority": 0},
      {"name": "Claude", "model": "claude-3-sonnet", "priority": 1}
    ],
    "default_fallback_action": "failover"
  }
}
```

## Haystack

Generates a Haystack pipeline config:

```yaml
components:
  gpt_4:
    type: OpenAIGenerator
    params:
      model: gpt-4
  claude:
    type: OpenAIGenerator
    params:
      model: claude-3-sonnet
pipelines:
  - name: production-chain
    nodes:
      - name: gpt_4
        inputs: [Query]
      - name: claude
        inputs: [gpt_4]
```

## Custom Templates

Use Jinja2 templates for any format:

```bash
fallbackrabbit export my-chain.yaml --format template --template terraform.j2
fallbackrabbit export my-chain.yaml --format template --template docker-compose.j2 --extra-vars env=prod
```

Built-in templates:
- `terraform` — Terraform provider configuration
- `docker` — Docker Compose with environment variables
- `k8s` — Kubernetes ConfigMap
- `env` — `.env` file
# Real Provider Calls

FallbackRabbit can make real API calls to LLM providers for integration testing.

## Setup

Set environment variables for each provider you want to use:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://xxx.openai.azure.com"
export OLLAMA_BASE_URL="http://localhost:11434"
```

## Running Real Tests

```bash
# Enable real provider calls
fallbackrabbit test my-chain.yaml --real

# With outage simulation
fallbackrabbit test my-chain.yaml --real --outages outage-scenario.yaml
```

## Provider Configuration

Each provider supports custom configuration:

```python
from fallbackrabbit.providers import AsyncProviderClient, ProviderConfig

config = ProviderConfig(
    provider="openai",
    model_id="gpt-4",
    api_key="sk-...",
    max_tokens=1000,
    temperature=0.7,
)

client = AsyncProviderClient(config)
result = await client.complete("Hello, world!")
```

## Supported Providers

| Provider | Environment Variable | Base URL |
|-----------|---------------------|----------|
| OpenAI | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` | Custom endpoint |
| Ollama | — | `http://localhost:11434` |
| Custom | — | Custom endpoint |

## Cost Tracking

Real calls track token usage and estimated cost per prompt in the chain report.

!!! warning "API Costs"
    Real provider calls consume tokens and incur costs. Use `--prompts 1` for quick verification, and reserve larger batch tests for staging environments.
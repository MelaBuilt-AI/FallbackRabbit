# Simulating Outages

Test how your chain handles failures before they happen in production.

## Basic Simulation

```bash
fallbackrabbit test my-chain.yaml
```

This runs 5 test prompts with all providers healthy, showing latency and success rates.

## Outage Scenarios

Create an outage scenario file to inject specific failures:

```yaml
# outage-scenario.yaml
outages:
  - provider: GPT-4
    error_type: rate_limit
    duration_prompts: 3
    status_code: 429

  - provider: Claude
    error_type: timeout
    duration_prompts: 2

  - provider: Gemini
    error_type: server_error
    duration_prompts: 5
    status_code: 503
```

Run with the scenario:

```bash
fallbackrabbit test my-chain.yaml --outages outage-scenario.yaml
```

## Outage Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | ✅ | Provider name to affect |
| `error_type` | string | ✅ | Error type to simulate |
| `duration_prompts` | int | ✅ | How many prompts the outage lasts |
| `status_code` | int | ❌ | Specific HTTP status code |
| `error_message` | string | ❌ | Custom error message |

## Simulation Output

The simulator reports:

- **Per-prompt results** — Which provider handled each prompt, latency, retries
- **Chain report** — Success rate, average latency, total tokens, provider usage breakdown
- **Fallback path** — Visual representation of which failovers occurred
- **Timing** — Retries used, total wait time per prompt

## Verbose Mode

```bash
fallbackrabbit test my-chain.yaml --outages outage-scenario.yaml --verbose
```

Shows detailed per-prompt breakdown including error messages and retry history.
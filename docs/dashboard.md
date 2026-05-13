# Web Dashboard

FallbackRabbit includes a dark-themed web dashboard for managing chains, running tests, and exporting configs.

## Access

```bash
fallbackrabbit serve
# Open http://localhost:8000/dashboard
```

## Pages

### Overview
- Chain statistics (total chains, providers, rules)
- Quick actions (create chain, run test)

### Chains
- Create, view, edit, and delete chains
- Provider list with priority ordering
- Fallback rules configuration
- Chain validation status

### Test Runner
- Select a chain and number of prompts
- Run tests with live progress via WebSocket
- View results: success rate, latency, provider usage
- Outage scenario testing

### Export
- Export chains to any supported format
- Built-in: LiteLLM, OpenRouter, LangChain, Haystack, custom
- Template-based: Terraform, Docker, K8s, .env
- Copy or download exported configs

## Features

- **Dark theme** — Easy on the eyes, matches the FallbackRabbit brand
- **Responsive** — Works on mobile and desktop
- **WebSocket** — Live test progress updates
- **Zero dependencies** — No external CSS/JS required
- **API-powered** — All data comes from the REST API
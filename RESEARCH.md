# FallbackRabbit — Research Notes

## Concept
AI tool that automatically generates and tests fallback/middleware chains for LLM-powered apps.

## Core Features
1. **Chain Builder** — Define ideal model pipeline (e.g., GPT-4o → Claude → local Llama)
2. **Routing Logic Generator** — Auto-writes fallback routing config
3. **Outage Simulator** — Synthetic prompts + simulated rate limits/outages to test chains
4. **Config Export** — Deploy-ready configs for LiteLLM, OpenRouter, or custom middleware
5. **Live Monitoring** — Monitors real traffic, auto-adjusts fallback order based on latency/error data

## Target Audience
- Startups building production LLM apps
- Agencies running multi-client AI workloads
- Enterprise AI teams who can't afford single-provider outages

## Revenue Model
- **Free:** 2 chains, 3 providers
- **Pro $29/mo:** Unlimited chains + live monitoring
- **Team $99/mo:** Shared dashboards + SSO

## Competitive Landscape
| Tool | What It Does | Gap |
|------|-------------|-----|
| LiteLLM | LLM routing only | No testing or optimization |
| OpenRouter | Model routing only | No chain simulation |
| Portkey | Gateway + caching | No fallback simulation or live optimization |

**Nobody combines fallback chain generation + simulation testing + live optimization.** Clear market gap.

## Why Now
- Multi-provider LLM routing becoming standard
- Recent Anthropic/GCP outages made the pain real
- Everyone hand-rolls fallback logic — no tool tests it pre-production

## Build Timeline
6-8 weeks for MVP:
1. Core: Chain builder + outage simulator + config export
2. Then: Live monitoring + auto-optimization

## Tech Stack (Initial Thoughts)
- Python backend (async, fast)
- FastAPI for API
- LiteLLM integration for multi-provider routing
- Synthetic test generation
- Config output: YAML/JSON for LiteLLM, OpenRouter, custom
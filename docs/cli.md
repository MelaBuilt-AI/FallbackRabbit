# CLI Reference

## `fallbackrabbit init <path>`

Generate a starter chain config file.

```bash
fallbackrabbit init my-chain.yaml
```

## `fallbackrabbit validate <path>`

Validate a chain config file.

```bash
fallbackrabbit validate my-chain.yaml
```

Options:
- `--strict` — Treat warnings as errors

## `fallbackrabbit test <path>`

Run a simulation test on a chain config.

```bash
fallbackrabbit test my-chain.yaml
```

Options:
- `--prompts N` — Number of test prompts (default: 5)
- `--outages <path>` — Outage scenario file
- `--verbose` — Show detailed per-prompt results

## `fallbackrabbit export <path>`

Export a chain config to various formats.

```bash
fallbackrabbit export my-chain.yaml --format litellm
```

Options:
- `--format FORMAT` — Export format: `litellm`, `openrouter`, `langchain`, `haystack`, `custom`, `template`
- `--output PATH` — Write to file instead of stdout
- `--template PATH` — Jinja2 template file (for `template` format)
- `--extra-vars KEY=VALUE` — Extra template variables (repeatable)

## `fallbackrabbit serve`

Start the REST API server and dashboard.

```bash
fallbackrabbit serve
```

Options:
- `--host HOST` — Bind address (default: `127.0.0.1`)
- `--port PORT` — Port number (default: `8000`)
- `--storage URL` — Storage backend URL (default: `memory://`, or `sqlite:///path.db`)
- `--reload` — Enable auto-reload for development

## `fallbackrabbit analyze <path>`

Analyze a chain config for issues and optimization opportunities.

```bash
fallbackrabbit analyze my-chain.yaml
```

## `fallbackrabbit --version`

Show the installed version.
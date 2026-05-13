"""CLI entry point for FallbackRabbit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import yaml

from . import __version__
from .chain_schema import load_chain, load_outage_scenario
from .models import ChainReport
from .rich_display import (
    console,
    display_chain_summary,
    display_chain_validation,
    display_error,
    display_export_success,
    display_init_skip,
    display_init_success,
    display_progress_spinner,
    display_test_results,
    display_validation_error,
    display_validation_success,
)

EXAMPLE_CHAIN_YAML = """\
name: my-llm-chain
providers:
  - name: GPT-4o
    model_id: gpt-4o
    api_base: https://api.openai.com/v1
    priority: 0
    max_tokens: 4096
    timeout: 30
  - name: Claude Sonnet
    model_id: claude-sonnet-4-20250514
    api_base: https://api.anthropic.com/v1
    priority: 1
    max_tokens: 4096
    timeout: 30
  - name: Local Llama
    model_id: llama3
    api_base: http://localhost:11434/v1
    priority: 2
    max_tokens: 2048
    timeout: 60
fallback_rules:
  - condition_error_type: rate_limit
    action: wait
    wait_seconds: 5
    retry_count: 3
  - condition_error_type: timeout
    action: failover
  - condition_error_type: server_error
    action: failover
metadata:
  description: "Example 3-provider fallback chain"
"""


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """FallbackRabbit — generate and test LLM fallback chains."""


@cli.command()
@click.option("--output", "-o", default="chain.yaml", help="Output file path")
def init(output: str) -> None:
    """Create a starter chain.yaml in the current directory."""
    path = Path(output)
    if path.exists():
        display_init_skip(str(path))
        return

    path.write_text(EXAMPLE_CHAIN_YAML, encoding="utf-8")
    display_init_success(str(path))


@cli.command()
@click.argument("chain_file")
def validate(chain_file: str) -> None:
    """Validate a chain config file."""
    try:
        chain = load_chain(chain_file)
    except (FileNotFoundError, ValueError) as exc:
        display_validation_error(str(exc))
        raise SystemExit(1) from exc

    display_validation_success(chain)


@cli.command()
@click.argument("chain_file")
@click.option(
    "--outages",
    "-O",
    default=None,
    help="Outage scenario YAML file",
)
@click.option(
    "--prompts",
    "-n",
    default=5,
    help="Number of test prompts to generate",
)
@click.option(
    "--seed",
    "-s",
    default=None,
    type=int,
    help="Random seed for reproducibility",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress bar",
)
def test(
    chain_file: str,
    outages: str | None,
    prompts: int,
    seed: int | None,
    no_progress: bool,
) -> None:
    """Test a chain configuration with simulated prompts and outages."""
    from .chain_builder import validate_chain
    from .simulator import Simulator, generate_test_prompts

    if seed is not None:
        import random

        random.seed(seed)

    try:
        chain = load_chain(chain_file)
    except (FileNotFoundError, ValueError) as exc:
        display_error(f"Failed to load chain: {exc}")
        raise SystemExit(1) from exc

    outage_scenario = []
    if outages:
        try:
            outage_scenario = load_outage_scenario(outages)
        except (FileNotFoundError, ValueError) as exc:
            display_error(f"Failed to load outages: {exc}")
            raise SystemExit(1) from exc

    # Validate chain
    issues = validate_chain(chain)
    if issues:
        display_chain_validation(issues)
    else:
        console.print()

    # Display chain summary
    display_chain_summary(chain)
    console.print()

    # Create simulator and prompts
    sim = Simulator(chain, outage_scenario)
    test_prompts = generate_test_prompts(prompts)

    # Run tests with optional progress bar
    if no_progress:
        console.print(f"🧪 Running {len(test_prompts)} test prompts...")
        report = asyncio.run(sim.run_batch(test_prompts))
    else:
        with display_progress_spinner(len(test_prompts), description="🧪 Testing") as progress:
            task = progress.add_task("Running prompts", total=len(test_prompts))
            results = []
            for prompt in test_prompts:
                result = asyncio.run(sim.run_prompt(prompt))
                results.append(result)
                progress.advance(task)

        # Build report from individually-tracked results
        total = len(results)
        successes = [r for r in results if r.success]
        success_latencies = [r.latency_ms for r in successes]
        report = ChainReport(
            chain_name=chain.name,
            total_prompts=total,
            results=results,
            success_rate=(len(successes) / total if total else 0.0),
            avg_latency_ms=(
                sum(success_latencies) / len(success_latencies) if success_latencies else 0.0
            ),
            fallback_rate=(
                sum(1 for r in results if r.fallback_triggered) / total if total else 0.0
            ),
        )

    console.print()
    display_test_results(report, prompts=test_prompts)


@cli.command()
@click.argument("chain_file")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["litellm", "openrouter", "custom", "langchain", "haystack", "template"]),
    default="custom",
    help="Export format",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output file path (default: stdout)",
)
@click.option(
    "--template",
    "-t",
    default=None,
    help="Jinja2 template string (for --format template)",
)
@click.option(
    "--template-file",
    "-T",
    default=None,
    help="Path to Jinja2 template file (for --format template)",
)
@click.option(
    "--builtin-template",
    "-b",
    type=click.Choice(["terraform", "docker", "k8s", "env"]),
    default=None,
    help="Built-in template name (for --format template)",
)
@click.option(
    "--var",
    "-v",
    multiple=True,
    help="Extra template variable (key=value), repeatable",
)
def export(
    chain_file: str,
    fmt: str,
    output: str | None,
    template: str | None,
    template_file: str | None,
    builtin_template: str | None,
    var: tuple[str, ...],
) -> None:
    """Export a chain config to another format."""
    import json as _json

    from rich.syntax import Syntax

    from .config_export import (
        export_custom,
        export_haystack,
        export_langchain,
        export_litellm,
        export_openrouter,
    )
    from .template_export import BUILTIN_TEMPLATES, render_template, render_template_file

    try:
        chain = load_chain(chain_file)
    except (FileNotFoundError, ValueError) as exc:
        display_error(f"Failed to load chain: {exc}")
        raise SystemExit(1) from exc

    # Parse extra vars
    extra_vars: dict[str, str] = {}
    for v in var:
        if "=" not in v:
            display_error(f"Invalid --var format: {v!r} (expected key=value)")
            raise SystemExit(1)
        key, value = v.split("=", 1)
        extra_vars[key] = value

    if fmt == "template":
        # Template-based export
        if builtin_template:
            template_str = BUILTIN_TEMPLATES[builtin_template]
            result = render_template(
                chain, template_str, output_path=output, extra_vars=extra_vars or None
            )
        elif template:
            result = render_template(
                chain, template, output_path=output, extra_vars=extra_vars or None
            )
        elif template_file:
            result = render_template_file(
                chain, template_file, output_path=output, extra_vars=extra_vars or None
            )
        else:
            display_error(
                "Template export requires one of: "
                "--template, --template-file, or --builtin-template"
            )
            raise SystemExit(1)
        if not output:
            # Guess syntax for highlighting
            lang = "text"
            if builtin_template == "terraform":
                lang = "hcl"
            elif builtin_template == "docker" or builtin_template == "k8s":
                lang = "yaml"
            elif builtin_template == "env":
                lang = "bash"
            syntax = Syntax(result, lang, theme="monokai")
            console.print(syntax)
    elif fmt == "litellm":
        result = export_litellm(chain, output_path=output)
        if not output:
            syntax = Syntax(str(result), "yaml", theme="monokai")
            console.print(syntax)
    elif fmt == "openrouter":
        result = export_openrouter(chain, output_path=output)
        if not output:
            syntax = Syntax(str(result), "json", theme="monokai")
            console.print(syntax)
    elif fmt == "custom":
        result = export_custom(chain, output_path=output)
        if not output:
            yaml_str = yaml.dump(result, default_flow_style=False, sort_keys=False)
            syntax = Syntax(yaml_str, "yaml", theme="monokai")
            console.print(syntax)
    elif fmt == "langchain":
        result = export_langchain(chain, output_path=output)
        if not output:
            json_str = _json.dumps(result, indent=2)
            syntax = Syntax(json_str, "json", theme="monokai")
            console.print(syntax)
    elif fmt == "haystack":
        result = export_haystack(chain, output_path=output)
        if not output:
            json_str = _json.dumps(result, indent=2)
            syntax = Syntax(json_str, "json", theme="monokai")
            console.print(syntax)
    else:
        display_error(f"Unsupported format: {fmt}")
        raise SystemExit(1)

    display_export_success(fmt, output)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--reload", "do_reload", is_flag=True, help="Enable auto-reload (dev mode)")
def serve(host: str, port: int, do_reload: bool) -> None:
    """Start the FallbackRabbit REST API server."""
    import uvicorn

    console.print(f"\n🐰 [bold]FallbackRabbit API[/bold] starting on {host}:{port}")
    console.print(f"   Docs: http://{host}:{port}/docs\n")
    uvicorn.run("fallbackrabbit.server:app", host=host, port=port, reload=do_reload)

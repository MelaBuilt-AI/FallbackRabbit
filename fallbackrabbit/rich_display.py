"""Rich display helpers for FallbackRabbit CLI output.

Provides formatted tables, panels, progress bars, and styled output
using the Rich library for terminal-friendly rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.tree import Tree

if TYPE_CHECKING:
    from .models import Chain, ChainReport


# ---------------------------------------------------------------------------
# Console singleton
# ---------------------------------------------------------------------------

console = Console()


# ---------------------------------------------------------------------------
# Chain display
# ---------------------------------------------------------------------------


def display_chain_summary(chain: Chain) -> None:
    """Display a rich panel with chain configuration summary.

    Args:
        chain: The chain to display.
    """
    # Provider tree
    tree = Tree("📦 [bold]Providers[/bold] (priority order)")
    for provider in sorted(chain.providers, key=lambda p: p.priority):
        if provider.priority == 0:
            priority_label = "[dim]primary[/dim]"
        else:
            priority_label = f"[dim]fallback #{provider.priority}[/dim]"
        tree.add(
            f"[cyan]{provider.name}[/cyan] — {provider.model_id} "
            f"[dim]({provider.api_base}, "
            f"{provider.timeout}s timeout)[/dim] "
            f"{priority_label}"
        )

    # Fallback rules
    rules_text = ""
    if chain.fallback_rules:
        for rule in chain.fallback_rules:
            action_style = "yellow" if rule.action.value == "wait" else "red"
            rules_text += (
                f"  • [dim]{rule.condition_error_type.value}[/dim] → "
                f"[{action_style}]{rule.action.value}[/{action_style}]"
            )
            if rule.action.value == "wait":
                rules_text += f" [dim]({rule.wait_seconds}s, {rule.retry_count} retries)[/dim]"
            rules_text += "\n"
    else:
        rules_text = "  [dim]No fallback rules defined[/dim]\n"

    panel = Panel(
        f"{tree}\n\n⚡ [bold]Fallback Rules[/bold]\n{rules_text}",
        title=f"🔗 [bold]{chain.name}[/bold]",
        subtitle=(f"{len(chain.providers)} providers · {len(chain.fallback_rules)} rules"),
        border_style="blue",
    )
    console.print(panel)


def display_chain_validation(issues: list[str]) -> None:
    """Display chain validation issues as a styled panel.

    Args:
        issues: List of validation issue strings.
    """
    if not issues:
        console.print("[green]✅ Chain validation passed — no issues found[/green]")
        return

    content = ""
    for issue in issues:
        content += f"  ⚠️  {issue}\n"

    panel = Panel(
        content.strip(),
        title="⚠️  [bold yellow]Chain Validation Issues[/bold yellow]",
        border_style="yellow",
    )
    console.print(panel)


# ---------------------------------------------------------------------------
# Test results display
# ---------------------------------------------------------------------------


def display_test_results(
    report: ChainReport,
    prompts: list | None = None,
) -> None:
    """Display test results as a rich table with styled output.

    Args:
        report: The chain report with aggregated results.
        prompts: Optional list of PromptSpec for category labels.
    """
    # Results table
    table = Table(
        title="🧪 Test Results",
        show_lines=True,
        border_style="bright_blue",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Provider", style="cyan", min_width=16)
    table.add_column("Category", style="magenta", width=12)
    table.add_column("Status", width=10)
    table.add_column("Latency", justify="right", width=12)
    table.add_column("Fallback", width=10)
    table.add_column("Error", style="red", max_width=30, no_wrap=False)

    for i, result in enumerate(report.results, 1):
        cat = "?"
        if prompts and i - 1 < len(prompts):
            cat = prompts[i - 1].category

        status = "[green]✅ OK[/green]" if result.success else "[red]❌ FAIL[/red]"
        latency = f"{result.latency_ms:.1f}ms"
        fallback = "[yellow]Yes[/yellow]" if result.fallback_triggered else "[dim]No[/dim]"
        error = result.error or "[dim]—[/dim]"

        table.add_row(
            str(i),
            result.provider_name,
            cat,
            status,
            latency,
            fallback,
            error,
        )

    console.print(table)

    # Summary panel
    if report.success_rate >= 0.8:
        success_style = "green"
    elif report.success_rate >= 0.5:
        success_style = "yellow"
    else:
        success_style = "red"

    fallback_style = "yellow" if report.fallback_rate > 0.3 else "dim"

    if report.success_rate >= 0.8:
        border_style = "green"
    elif report.success_rate >= 0.5:
        border_style = "yellow"
    else:
        border_style = "red"

    summary = Panel(
        f"[bold]Chain:[/bold]       {report.chain_name}\n"
        f"[bold]Total tests:[/bold] "
        f"{report.total_prompts}\n"
        f"[bold]Success rate:[/bold] "
        f"[{success_style}]"
        f"{report.success_rate:.1%}"
        f"[/{success_style}]\n"
        f"[bold]Avg latency:[/bold]  "
        f"{report.avg_latency_ms:.1f}ms\n"
        f"[bold]Fallback rate:[/bold] "
        f"[{fallback_style}]"
        f"{report.fallback_rate:.1%}"
        f"[/{fallback_style}]",
        title="📊 [bold]Summary[/bold]",
        border_style=border_style,
    )
    console.print(summary)


def display_progress_spinner(
    total: int,
    description: str = "Running tests",
) -> Progress:
    """Create a Rich progress bar for batch test execution.

    Args:
        total: Total number of prompts to process.
        description: Description text for the progress bar.

    Returns:
        A Rich Progress context manager.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


# ---------------------------------------------------------------------------
# Validation display
# ---------------------------------------------------------------------------


def display_validation_success(chain: Chain) -> None:
    """Display a success message for chain validation.

    Args:
        chain: The validated chain.
    """
    console.print(
        Panel(
            f"[green]✅ Valid chain:[/green] "
            f"[bold cyan]{chain.name}[/bold cyan]\n"
            f"   {len(chain.providers)} providers · "
            f"{len(chain.fallback_rules)} fallback rules",
            border_style="green",
        )
    )


def display_validation_error(error: str) -> None:
    """Display a validation error.

    Args:
        error: The error message.
    """
    console.print(
        Panel(
            f"[red]❌ Validation failed:[/red]\n   {error}",
            border_style="red",
        )
    )


# ---------------------------------------------------------------------------
# Export display
# ---------------------------------------------------------------------------


def display_export_success(fmt: str, output_path: str | None) -> None:
    """Display a success message for config export.

    Args:
        fmt: The export format name.
        output_path: The output file path, or None for stdout.
    """
    if output_path:
        console.print(
            f"[green]✅ Exported[/green] [bold]{fmt}[/bold] config to [cyan]{output_path}[/cyan]"
        )
    else:
        console.print(f"[green]✅ Exported[/green] [bold]{fmt}[/bold] config (stdout)")


# ---------------------------------------------------------------------------
# Init display
# ---------------------------------------------------------------------------


def display_init_success(path: str) -> None:
    """Display a success message for chain init.

    Args:
        path: The path where the starter config was created.
    """
    console.print(f"[green]✅ Created starter config at[/green] [cyan]{path}[/cyan]")


def display_init_skip(path: str) -> None:
    """Display a skip message when init target already exists.

    Args:
        path: The path that already exists.
    """
    console.print(f"[yellow]⚠️  {path} already exists — skipping to avoid overwrite[/yellow]")


# ---------------------------------------------------------------------------
# Error display
# ---------------------------------------------------------------------------


def display_error(message: str) -> None:
    """Display a general error message.

    Args:
        message: The error message.
    """
    console.print(f"[red bold]❌ {message}[/red bold]")

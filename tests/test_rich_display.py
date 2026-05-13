"""Tests for fallbackrabbit.rich_display — Rich CLI output helpers."""

from __future__ import annotations

import pytest

from fallbackrabbit.models import (
    Chain,
    ChainReport,
    ErrorType,
    FallbackAction,
    FallbackRule,
    PromptResult,
    Provider,
)
from fallbackrabbit.rich_display import (
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chain() -> Chain:
    """Create a sample chain for testing."""
    return Chain(
        name="test-chain",
        providers=[
            Provider(
                name="GPT-4o", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
            ),
            Provider(
                name="Claude",
                model_id="claude-sonnet-4",
                api_base="https://api.anthropic.com/v1",
                priority=1,
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
            FallbackRule(
                condition_error_type=ErrorType.TIMEOUT,
                action=FallbackAction.FAILOVER,
            ),
        ],
    )


@pytest.fixture
def sample_report() -> ChainReport:
    """Create a sample chain report for testing."""
    return ChainReport(
        chain_name="test-chain",
        total_prompts=5,
        results=[
            PromptResult(provider_name="GPT-4o", prompt_id="p1", success=True, latency_ms=1500.0),
            PromptResult(provider_name="GPT-4o", prompt_id="p2", success=True, latency_ms=1200.0),
            PromptResult(
                provider_name="Claude",
                prompt_id="p3",
                success=True,
                latency_ms=800.0,
                fallback_triggered=True,
            ),
            PromptResult(
                provider_name="Claude",
                prompt_id="p4",
                success=False,
                latency_ms=0.0,
                error="Simulated timeout",
                fallback_triggered=True,
            ),
            PromptResult(provider_name="GPT-4o", prompt_id="p5", success=True, latency_ms=1800.0),
        ],
        success_rate=0.8,
        avg_latency_ms=1325.0,
        fallback_rate=0.4,
    )


# ---------------------------------------------------------------------------
# display_chain_summary
# ---------------------------------------------------------------------------


class TestDisplayChainSummary:
    """Tests for display_chain_summary."""

    def test_renders_without_error(self, sample_chain: Chain) -> None:
        """display_chain_summary should render without raising."""
        display_chain_summary(sample_chain)

    def test_renders_chain_with_no_rules(self) -> None:
        """display_chain_summary should work with zero fallback rules."""
        chain = Chain(
            name="bare-chain",
            providers=[
                Provider(
                    name="Local",
                    model_id="llama3",
                    api_base="http://localhost:11434/v1",
                    priority=0,
                )
            ],
            fallback_rules=[],
        )
        display_chain_summary(chain)

    def test_renders_multiple_providers(self) -> None:
        """display_chain_summary should handle 5+ providers."""
        providers = [
            Provider(
                name=f"Provider-{i}",
                model_id=f"model-{i}",
                api_base=f"http://api-{i}.example.com/v1",
                priority=i,
            )
            for i in range(5)
        ]
        chain = Chain(name="big-chain", providers=providers, fallback_rules=[])
        display_chain_summary(chain)


# ---------------------------------------------------------------------------
# display_chain_validation
# ---------------------------------------------------------------------------


class TestDisplayChainValidation:
    """Tests for display_chain_validation."""

    def test_renders_issues(self) -> None:
        """display_chain_validation should render a list of issues."""
        display_chain_validation(["No fallback rules defined", "Provider timeout > 60s"])

    def test_renders_empty_issues(self) -> None:
        """display_chain_validation with no issues should show success."""
        display_chain_validation([])


# ---------------------------------------------------------------------------
# display_test_results
# ---------------------------------------------------------------------------


class TestDisplayTestResults:
    """Tests for display_test_results."""

    def test_renders_report(self, sample_report: ChainReport) -> None:
        """display_test_results should render a report table."""
        display_test_results(sample_report)

    def test_renders_report_with_prompts(self, sample_report: ChainReport) -> None:
        """display_test_results should include categories when prompts given."""
        from fallbackrabbit.models import PromptSpec

        prompts = [
            PromptSpec(prompt="test", category="general"),
            PromptSpec(prompt="test2", category="creative"),
            PromptSpec(prompt="test3", category="factual"),
            PromptSpec(prompt="test4", category="code"),
            PromptSpec(prompt="test5", category="complex"),
        ]
        display_test_results(sample_report, prompts=prompts)

    def test_renders_all_failures(self) -> None:
        """display_test_results should handle 0% success rate."""
        report = ChainReport(
            chain_name="fail-chain",
            total_prompts=3,
            results=[
                PromptResult(
                    provider_name="GPT-4o",
                    prompt_id="p1",
                    success=False,
                    latency_ms=0.0,
                    error="All providers failed",
                    fallback_triggered=True,
                ),
                PromptResult(
                    provider_name="GPT-4o",
                    prompt_id="p2",
                    success=False,
                    latency_ms=0.0,
                    error="Timeout",
                    fallback_triggered=True,
                ),
                PromptResult(
                    provider_name="GPT-4o",
                    prompt_id="p3",
                    success=False,
                    latency_ms=0.0,
                    error="Rate limit",
                    fallback_triggered=True,
                ),
            ],
            success_rate=0.0,
            avg_latency_ms=0.0,
            fallback_rate=1.0,
        )
        display_test_results(report)

    def test_renders_all_successes(self) -> None:
        """display_test_results should handle 100% success rate."""
        report = ChainReport(
            chain_name="perfect-chain",
            total_prompts=3,
            results=[
                PromptResult(
                    provider_name="GPT-4o", prompt_id="p1", success=True, latency_ms=1000.0
                ),
                PromptResult(
                    provider_name="GPT-4o", prompt_id="p2", success=True, latency_ms=1200.0
                ),
                PromptResult(
                    provider_name="GPT-4o", prompt_id="p3", success=True, latency_ms=800.0
                ),
            ],
            success_rate=1.0,
            avg_latency_ms=1000.0,
            fallback_rate=0.0,
        )
        display_test_results(report)


# ---------------------------------------------------------------------------
# display_validation_success / display_validation_error
# ---------------------------------------------------------------------------


class TestDisplayValidationMessages:
    """Tests for validation display helpers."""

    def test_success(self, sample_chain: Chain) -> None:
        """display_validation_success should render without error."""
        display_validation_success(sample_chain)

    def test_error(self) -> None:
        """display_validation_error should render without error."""
        display_validation_error("Invalid provider name")


# ---------------------------------------------------------------------------
# display_export_success
# ---------------------------------------------------------------------------


class TestDisplayExportSuccess:
    """Tests for display_export_success."""

    def test_with_file_path(self) -> None:
        """display_export_success should render with file path."""
        display_export_success("litellm", "output.yaml")

    def test_with_stdout(self) -> None:
        """display_export_success should render for stdout."""
        display_export_success("custom", None)


# ---------------------------------------------------------------------------
# display_init_success / display_init_skip
# ---------------------------------------------------------------------------


class TestDisplayInitMessages:
    """Tests for init display helpers."""

    def test_success(self) -> None:
        """display_init_success should render without error."""
        display_init_success("chain.yaml")

    def test_skip(self) -> None:
        """display_init_skip should render without error."""
        display_init_skip("chain.yaml")


# ---------------------------------------------------------------------------
# display_error
# ---------------------------------------------------------------------------


class TestDisplayError:
    """Tests for display_error."""

    def test_renders_error(self) -> None:
        """display_error should render an error message."""
        display_error("Something went wrong")


# ---------------------------------------------------------------------------
# display_progress_spinner
# ---------------------------------------------------------------------------


class TestDisplayProgressSpinner:
    """Tests for display_progress_spinner."""

    def test_creates_progress(self) -> None:
        """display_progress_spinner should return a Progress instance."""
        progress = display_progress_spinner(5, description="Testing")
        assert progress is not None

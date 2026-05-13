"""Tests for core data models."""

import pytest
from pydantic import ValidationError

from fallbackrabbit.models import (
    Chain,
    ChainReport,
    ErrorType,
    ExportFormat,
    FallbackAction,
    FallbackRule,
    PromptResult,
    PromptSpec,
    Provider,
    SimulatedOutage,
)

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class TestProvider:
    def test_basic_creation(self) -> None:
        p = Provider(name="OpenAI", model_id="gpt-4o", api_base="https://api.openai.com/v1")
        assert p.name == "OpenAI"
        assert p.priority == 0
        assert p.max_tokens == 4096

    def test_custom_fields(self) -> None:
        p = Provider(
            name="Local",
            model_id="llama3",
            api_base="http://localhost:11434/v1",
            priority=5,
            max_tokens=8192,
            timeout=120.0,
            metadata={"provider_type": "ollama"},
        )
        assert p.priority == 5
        assert p.timeout == 120.0
        assert p.metadata["provider_type"] == "ollama"

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            Provider(name="NoModel")  # type: ignore[call-arg]

    def test_invalid_max_tokens(self) -> None:
        with pytest.raises(ValidationError):
            Provider(
                name="Bad",
                model_id="bad",
                api_base="http://x",
                max_tokens=0,
            )


# ---------------------------------------------------------------------------
# FallbackRule
# ---------------------------------------------------------------------------


class TestFallbackRule:
    def test_basic_creation(self) -> None:
        rule = FallbackRule(
            condition_error_type=ErrorType.TIMEOUT,
            action=FallbackAction.FAILOVER,
        )
        assert rule.condition_error_type == ErrorType.TIMEOUT
        assert rule.action == FallbackAction.FAILOVER

    def test_with_all_fields(self) -> None:
        rule = FallbackRule(
            condition_error_type=ErrorType.RATE_LIMIT,
            condition_latency_threshold=5000.0,
            condition_status_codes=[429, 503],
            action=FallbackAction.WAIT,
            wait_seconds=10.0,
            retry_count=3,
        )
        assert rule.condition_status_codes == [429, 503]
        assert rule.wait_seconds == 10.0

    def test_invalid_error_type(self) -> None:
        with pytest.raises(ValidationError):
            FallbackRule(
                condition_error_type="invalid",  # type: ignore[arg-type]
                action=FallbackAction.FAILOVER,
            )


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------


class TestChain:
    def test_basic_creation(self) -> None:
        p1 = Provider(name="A", model_id="a", api_base="http://a")
        p2 = Provider(name="B", model_id="b", api_base="http://b")
        chain = Chain(name="test-chain", providers=[p1, p2])
        assert len(chain.providers) == 2
        assert chain.name == "test-chain"

    def test_duplicate_provider_names_rejected(self) -> None:
        p1 = Provider(name="Same", model_id="a", api_base="http://a")
        p2 = Provider(name="Same", model_id="b", api_base="http://b")
        with pytest.raises(ValidationError, match="unique"):
            Chain(name="bad", providers=[p1, p2])

    def test_empty_providers_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Chain(name="empty", providers=[])


# ---------------------------------------------------------------------------
# TestPrompt / TestResult / ChainTestReport
# ---------------------------------------------------------------------------


class TestPromptSpec:
    def test_defaults(self) -> None:
        tp = PromptSpec(prompt="Hello")
        assert tp.category == "general"
        assert tp.expected_behavior == "returns a valid response"


class TestPromptResult:
    def test_basic(self) -> None:
        tr = PromptResult(provider_name="OpenAI", success=True, latency_ms=150.0)
        assert tr.success is True
        assert tr.error is None
        assert tr.fallback_triggered is False


class TestChainReport:
    def test_defaults(self) -> None:
        report = ChainReport(chain_name="test", total_prompts=10)
        assert report.success_rate == 0.0
        assert report.avg_latency_ms == 0.0
        assert report.fallback_rate == 0.0


# ---------------------------------------------------------------------------
# SimulatedOutage
# ---------------------------------------------------------------------------


class TestSimulatedOutage:
    def test_basic(self) -> None:
        outage = SimulatedOutage(
            provider_name="OpenAI",
            error_type=ErrorType.RATE_LIMIT,
        )
        assert outage.probability == 1.0
        assert outage.duration_seconds == 60.0

    def test_invalid_probability(self) -> None:
        with pytest.raises(ValidationError):
            SimulatedOutage(
                provider_name="X",
                error_type=ErrorType.TIMEOUT,
                probability=1.5,
            )


# ---------------------------------------------------------------------------
# ExportFormat enum
# ---------------------------------------------------------------------------


class TestExportFormat:
    def test_values(self) -> None:
        assert ExportFormat.LITELLM.value == "litellm"
        assert ExportFormat.OPENROUTER.value == "openrouter"
        assert ExportFormat.CUSTOM.value == "custom"

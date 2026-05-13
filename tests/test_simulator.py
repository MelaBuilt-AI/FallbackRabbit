"""Tests for simulator module."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fallbackrabbit.models import (
    Chain,
    ErrorType,
    FallbackAction,
    FallbackRule,
    PromptSpec,
    Provider,
    SimulatedOutage,
)
from fallbackrabbit.simulator import Simulator, generate_test_prompts

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
EXAMPLE_CHAIN = SCHEMAS_DIR / "example_chain.yaml"
EXAMPLE_OUTAGE = SCHEMAS_DIR / "example_outage.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_provider(
    name: str = "TestProvider", model_id: str = "test-model", priority: int = 0
) -> Provider:
    return Provider(
        name=name, model_id=model_id, api_base="https://api.test.com/v1", priority=priority
    )


def _make_chain(names: list[str] | None = None, rules: list[FallbackRule] | None = None) -> Chain:
    if names is None:
        names = ["Alpha", "Beta", "Gamma"]
    providers = [_make_provider(name=name, priority=i) for i, name in enumerate(names)]
    return Chain(name="test-chain", providers=providers, fallback_rules=rules or [])


def _make_example_chain() -> Chain:
    return Chain(
        name="example-chain",
        providers=[
            Provider(
                name="GPT-4o",
                model_id="gpt-4o",
                api_base="https://api.openai.com/v1",
                priority=0,
                max_tokens=4096,
                timeout=30,
                metadata={"provider_type": "openai"},
            ),
            Provider(
                name="Claude Sonnet",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com/v1",
                priority=1,
                max_tokens=4096,
                timeout=30,
                metadata={"provider_type": "anthropic"},
            ),
            Provider(
                name="Local Llama",
                model_id="llama3",
                api_base="http://localhost:11434/v1",
                priority=2,
                max_tokens=2048,
                timeout=60,
                metadata={"provider_type": "ollama"},
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type="rate_limit",
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
            FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
            FallbackRule(
                condition_error_type="server_error",
                condition_status_codes=[500, 502, 503],
                action=FallbackAction.FAILOVER,
            ),
            FallbackRule(condition_error_type="connection_error", action=FallbackAction.FAILOVER),
        ],
    )


# ---------------------------------------------------------------------------
# Simulator initialization
# ---------------------------------------------------------------------------


class TestSimulatorInit:
    def test_create_with_no_outages(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        assert sim.chain.name == "test-chain"
        assert sim.outages == {}

    def test_create_with_outages(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(
                provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=0.8
            ),
        ]
        sim = Simulator(chain, outages)
        assert "Alpha" in sim.outages
        assert len(sim.outages["Alpha"]) == 1

    def test_inject_outage(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        outage = SimulatedOutage(
            provider_name="Beta", error_type=ErrorType.TIMEOUT, probability=1.0
        )
        sim.inject_outage("Beta", outage)
        assert "Beta" in sim.outages
        assert sim.outages["Beta"][0].error_type == ErrorType.TIMEOUT

    def test_multiple_outages_same_provider(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        sim.inject_outage(
            "Alpha",
            SimulatedOutage(
                provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=0.5
            ),
        )
        sim.inject_outage(
            "Alpha",
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.TIMEOUT, probability=0.3),
        )
        assert len(sim.outages["Alpha"]) == 2


# ---------------------------------------------------------------------------
# _should_trigger_outage
# ---------------------------------------------------------------------------


class TestShouldTriggerOutage:
    def test_no_outages_always_false(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        assert sim._should_trigger_outage("Alpha") is False

    def test_probability_1_always_true(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=1.0)
        ]
        sim = Simulator(chain, outages)
        assert sim._should_trigger_outage("Alpha") is True

    def test_probability_0_always_false(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=0.0)
        ]
        sim = Simulator(chain, outages)
        assert sim._should_trigger_outage("Alpha") is False

    def test_different_provider_not_affected(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=1.0)
        ]
        sim = Simulator(chain, outages)
        assert sim._should_trigger_outage("Beta") is False


# ---------------------------------------------------------------------------
# _simulate_provider_call
# ---------------------------------------------------------------------------


class TestSimulateProviderCall:
    def test_successful_call(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        prompt = PromptSpec(prompt="Hello")
        provider = chain.providers[0]

        result = sim._simulate_provider_call(provider, prompt)
        assert result.success is True
        assert result.latency_ms > 0
        assert result.error is None
        assert result.fallback_triggered is False

    def test_outage_causes_failure(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=1.0)
        ]
        sim = Simulator(chain, outages)
        prompt = PromptSpec(prompt="Hello")
        provider = chain.providers[0]

        result = sim._simulate_provider_call(provider, prompt)
        assert result.success is False
        assert result.fallback_triggered is True
        assert "rate_limit" in result.error

    def test_latency_ranges(self) -> None:
        """Test that latency falls within expected ranges for different model types."""
        chain = _make_example_chain()
        sim = Simulator(chain)

        # GPT-4 class: 1-3 seconds
        gpt_result = sim._simulate_provider_call(chain.providers[0], PromptSpec(prompt="test"))
        if gpt_result.success:
            assert gpt_result.latency_ms >= 1000.0
            assert gpt_result.latency_ms <= 3000.0

        # Claude class: 0.5-2 seconds
        claude_result = sim._simulate_provider_call(chain.providers[1], PromptSpec(prompt="test"))
        if claude_result.success:
            assert claude_result.latency_ms >= 500.0
            assert claude_result.latency_ms <= 2000.0

        # Local model: 0.2-1 second
        llama_result = sim._simulate_provider_call(chain.providers[2], PromptSpec(prompt="test"))
        if llama_result.success:
            assert llama_result.latency_ms >= 200.0
            assert llama_result.latency_ms <= 1000.0


# ---------------------------------------------------------------------------
# _apply_fallback
# ---------------------------------------------------------------------------


class TestApplyFallback:
    def test_returns_next_provider(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        result = sim._apply_fallback(chain, "Alpha", "Simulated timeout")
        assert result == "Beta"

    def test_returns_none_for_last_provider(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        result = sim._apply_fallback(chain, "Gamma", "Simulated timeout")
        assert result is None

    def test_returns_none_for_unknown_provider(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        result = sim._apply_fallback(chain, "Unknown", "Simulated timeout")
        assert result is None

    def test_middle_provider_falls_to_next(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        result = sim._apply_fallback(chain, "Beta", "Simulated timeout")
        assert result == "Gamma"


# ---------------------------------------------------------------------------
# run_prompt
# ---------------------------------------------------------------------------


class TestRunPrompt:
    def test_successful_prompt_no_outages(self) -> None:
        """With no outages, prompt should succeed on the first provider."""
        chain = _make_chain()
        sim = Simulator(chain)
        prompt = PromptSpec(prompt="Hello, world!")

        result = asyncio.run(sim.run_prompt(prompt))
        assert result.success is True
        assert result.provider_name == "Alpha"
        assert result.latency_ms > 0

    def test_outage_causes_fallback(self) -> None:
        """If first provider has 100% outage, prompt should succeed on second provider."""
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.TIMEOUT, probability=1.0)
        ]
        sim = Simulator(chain, outages)
        prompt = PromptSpec(prompt="Test fallback")

        result = asyncio.run(sim.run_prompt(prompt))
        assert result.success is True
        assert result.provider_name == "Beta"
        assert result.fallback_triggered is True

    def test_all_providers_down(self) -> None:
        """If all providers have 100% outage, prompt should fail."""
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.TIMEOUT, probability=1.0),
            SimulatedOutage(
                provider_name="Beta", error_type=ErrorType.SERVER_ERROR, probability=1.0
            ),
            SimulatedOutage(
                provider_name="Gamma", error_type=ErrorType.CONNECTION_ERROR, probability=1.0
            ),
        ]
        sim = Simulator(chain, outages)
        prompt = PromptSpec(prompt="Test all down")

        result = asyncio.run(sim.run_prompt(prompt))
        assert result.success is False
        assert result.fallback_triggered is True
        assert "failed" in result.error.lower() or "All" in result.error

    def test_partial_outage(self) -> None:
        """First two providers down, third should succeed."""
        chain = _make_chain()
        outages = [
            SimulatedOutage(
                provider_name="Alpha", error_type=ErrorType.RATE_LIMIT, probability=1.0
            ),
            SimulatedOutage(provider_name="Beta", error_type=ErrorType.TIMEOUT, probability=1.0),
        ]
        sim = Simulator(chain, outages)
        prompt = PromptSpec(prompt="Test partial outage")

        result = asyncio.run(sim.run_prompt(prompt))
        assert result.success is True
        assert result.provider_name == "Gamma"
        assert result.fallback_triggered is True

    def test_prompt_result_fields(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        prompt = PromptSpec(prompt="Field check", category="test", expected_behavior="works")

        result = asyncio.run(sim.run_prompt(prompt))
        assert result.prompt_id  # Non-empty
        assert result.provider_name in ["Alpha", "Beta", "Gamma"]


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------


class TestRunBatch:
    def test_batch_all_succeed(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        prompts = [PromptSpec(prompt=f"Test {i}") for i in range(5)]

        report = asyncio.run(sim.run_batch(prompts))
        assert report.chain_name == "test-chain"
        assert report.total_prompts == 5
        assert report.success_rate > 0
        assert len(report.results) == 5

    def test_batch_with_outages(self) -> None:
        chain = _make_chain()
        outages = [
            SimulatedOutage(provider_name="Alpha", error_type=ErrorType.TIMEOUT, probability=1.0)
        ]
        sim = Simulator(chain, outages)
        prompts = [PromptSpec(prompt=f"Test {i}") for i in range(3)]

        report = asyncio.run(sim.run_batch(prompts))
        assert report.total_prompts == 3
        # Should still have some successes from fallback providers
        assert report.success_rate > 0

    def test_batch_empty_prompts(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)

        report = asyncio.run(sim.run_batch([]))
        assert report.total_prompts == 0
        assert report.success_rate == 0.0
        assert report.avg_latency_ms == 0.0

    def test_batch_report_metrics(self) -> None:
        chain = _make_chain()
        sim = Simulator(chain)
        prompts = [PromptSpec(prompt="Metric test")]

        report = asyncio.run(sim.run_batch(prompts))
        assert 0 <= report.success_rate <= 1
        assert report.avg_latency_ms >= 0
        assert 0 <= report.fallback_rate <= 1


# ---------------------------------------------------------------------------
# generate_test_prompts
# ---------------------------------------------------------------------------


class TestGenerateTestPrompts:
    def test_default_count(self) -> None:
        prompts = generate_test_prompts()
        assert len(prompts) == 5

    def test_custom_count(self) -> None:
        prompts = generate_test_prompts(10)
        assert len(prompts) == 10

    def test_minimum_count(self) -> None:
        prompts = generate_test_prompts(3)
        assert len(prompts) >= 5  # minimum 5 for category coverage

    def test_prompt_categories(self) -> None:
        prompts = generate_test_prompts()
        categories = {p.category for p in prompts}
        assert "general" in categories
        assert "creative" in categories
        assert "factual" in categories
        assert "code" in categories
        assert "complex" in categories

    def test_prompt_fields(self) -> None:
        prompts = generate_test_prompts()
        for p in prompts:
            assert p.prompt  # Non-empty
            assert p.category
            assert p.expected_behavior


# ---------------------------------------------------------------------------
# Integration with example chain
# ---------------------------------------------------------------------------


class TestSimulatorWithExampleChain:
    def test_example_chain_no_outages(self) -> None:
        from fallbackrabbit.chain_schema import load_chain

        chain = load_chain(EXAMPLE_CHAIN)
        sim = Simulator(chain)
        prompts = [PromptSpec(prompt="Integration test")]

        result = asyncio.run(sim.run_prompt(prompts[0]))
        assert result.success is True
        assert result.provider_name == "GPT-4o"

    def test_example_chain_with_outages(self) -> None:
        from fallbackrabbit.chain_schema import load_chain, load_outage_scenario

        chain = load_chain(EXAMPLE_CHAIN)
        load_outage_scenario(EXAMPLE_OUTAGE)
        # Force outage on first provider
        forced_outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=1.0
            ),
        ]
        sim = Simulator(chain, forced_outages)
        prompts = [PromptSpec(prompt="Outage test")]

        result = asyncio.run(sim.run_prompt(prompts[0]))
        assert result.success is True
        assert result.provider_name != "GPT-4o"

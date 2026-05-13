"""Tests for chain_builder module."""

from fallbackrabbit.chain_builder import (
    apply_fallback_rules,
    build_routing_chain,
    generate_chain_summary,
    optimize_chain_order,
    validate_chain,
)
from fallbackrabbit.models import Chain, FallbackAction, FallbackRule, Provider

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
    """Recreate the example chain from schemas/example_chain.yaml."""
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
# build_routing_chain
# ---------------------------------------------------------------------------


class TestBuildRoutingChain:
    def test_basic_routing(self) -> None:
        chain = _make_chain()
        result = build_routing_chain(chain)

        assert result["chain_name"] == "test-chain"
        assert result["total_providers"] == 3
        assert len(result["routing"]) == 3

        # First provider has failover to the other two
        assert result["routing"][0]["provider_name"] == "Alpha"
        assert result["routing"][0]["failover_targets"] == ["Beta", "Gamma"]
        assert result["routing"][1]["failover_targets"] == ["Gamma"]
        assert result["routing"][2]["failover_targets"] == []

    def test_routing_with_rules(self) -> None:
        rules = [
            FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
            FallbackRule(
                condition_error_type="rate_limit",
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
        ]
        chain = _make_chain(rules=rules)
        result = build_routing_chain(chain)

        assert "timeout" in result["fallback_rules"]
        assert "rate_limit" in result["fallback_rules"]
        assert result["fallback_rules"]["timeout"][0]["action"] == "failover"
        assert result["fallback_rules"]["rate_limit"][0]["action"] == "wait"

    def test_empty_rules(self) -> None:
        chain = _make_chain(rules=[])
        result = build_routing_chain(chain)
        assert result["fallback_rules"] == {}

    def test_priority_ordering(self) -> None:
        # Providers with non-sequential priorities should be sorted by priority
        providers = [
            _make_provider(name="High", priority=0),
            _make_provider(name="Low", priority=10),
            _make_provider(name="Mid", priority=5),
        ]
        chain = Chain(name="priority-test", providers=providers)
        result = build_routing_chain(chain)

        assert result["routing"][0]["provider_name"] == "High"
        assert result["routing"][1]["provider_name"] == "Mid"
        assert result["routing"][2]["provider_name"] == "Low"

    def test_single_provider(self) -> None:
        chain = _make_chain(names=["Solo"])
        result = build_routing_chain(chain)
        assert result["total_providers"] == 1
        assert result["routing"][0]["failover_targets"] == []

    def test_example_chain(self) -> None:
        chain = _make_example_chain()
        result = build_routing_chain(chain)

        assert result["chain_name"] == "example-chain"
        assert result["total_providers"] == 3
        assert result["routing"][0]["model_id"] == "gpt-4o"
        assert result["routing"][0]["timeout_seconds"] == 30
        assert result["routing"][1]["model_id"] == "claude-sonnet-4-20250514"
        assert result["routing"][2]["model_id"] == "llama3"
        assert "rate_limit" in result["fallback_rules"]
        assert "timeout" in result["fallback_rules"]


# ---------------------------------------------------------------------------
# apply_fallback_rules
# ---------------------------------------------------------------------------


class TestApplyFallbackRules:
    def test_default_rules(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
                FallbackRule(
                    condition_error_type="rate_limit",
                    action=FallbackAction.WAIT,
                    wait_seconds=5,
                    retry_count=3,
                ),
            ]
        )
        result = apply_fallback_rules(chain, [])

        assert "timeout" in result
        assert result["timeout"]["action"] == "failover"
        assert "rate_limit" in result
        assert result["rate_limit"]["action"] == "wait"
        assert result["rate_limit"]["wait_seconds"] == 5
        assert result["rate_limit"]["retry_count"] == 3

    def test_extra_rules_override(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
            ]
        )
        extra = [
            FallbackRule(
                condition_error_type="timeout",
                action=FallbackAction.WAIT,
                wait_seconds=2,
                retry_count=2,
            ),
        ]
        result = apply_fallback_rules(chain, extra)

        # Extra rule should override chain rule for same error type
        assert result["timeout"]["action"] == "wait"
        assert result["timeout"]["wait_seconds"] == 2

    def test_new_error_type(self) -> None:
        chain = _make_chain(rules=[])
        extra = [
            FallbackRule(condition_error_type="server_error", action=FallbackAction.FAILOVER),
        ]
        result = apply_fallback_rules(chain, extra)

        assert "server_error" in result
        assert result["server_error"]["action"] == "failover"

    def test_latency_threshold(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(
                    condition_error_type="timeout",
                    action=FallbackAction.FAILOVER,
                    condition_latency_threshold=5000.0,
                ),
            ]
        )
        result = apply_fallback_rules(chain, [])
        assert result["timeout"]["latency_threshold_ms"] == 5000.0

    def test_status_codes(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(
                    condition_error_type="server_error",
                    action=FallbackAction.FAILOVER,
                    condition_status_codes=[500, 502, 503],
                ),
            ]
        )
        result = apply_fallback_rules(chain, [])
        assert result["server_error"]["status_codes"] == [500, 502, 503]


# ---------------------------------------------------------------------------
# validate_chain
# ---------------------------------------------------------------------------


class TestValidateChain:
    def test_valid_chain(self) -> None:
        chain = _make_chain()
        issues = validate_chain(chain)
        assert issues == []

    def test_single_provider_valid(self) -> None:
        chain = _make_chain(names=["Solo"])
        issues = validate_chain(chain)
        assert issues == []

    def test_duplicate_priorities(self) -> None:
        providers = [
            _make_provider(name="A", priority=0),
            _make_provider(name="B", priority=0),
        ]
        chain = Chain(name="dup-priority", providers=providers)
        issues = validate_chain(chain)
        assert any("priority" in i.lower() for i in issues)

    def test_priority_gap(self) -> None:
        providers = [
            _make_provider(name="A", priority=0),
            _make_provider(name="B", priority=5),
        ]
        chain = Chain(name="gap", providers=providers)
        issues = validate_chain(chain)
        assert any("gap" in i.lower() for i in issues)

    def test_wait_rule_with_zero_seconds(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(
                    condition_error_type="rate_limit",
                    action=FallbackAction.WAIT,
                    wait_seconds=0,
                    retry_count=3,
                ),
            ]
        )
        issues = validate_chain(chain)
        assert any("wait_seconds" in i for i in issues)

    def test_retry_rule_with_low_count(self) -> None:
        # retry_count=0 is rejected by Pydantic (min=1), so test with count=1
        # which is technically valid but worth documenting
        chain = _make_chain(
            rules=[
                FallbackRule(
                    condition_error_type="rate_limit", action=FallbackAction.RETRY, retry_count=1
                ),
            ]
        )
        issues = validate_chain(chain)
        # No issues expected — retry_count=1 is valid
        assert issues == []

    def test_example_chain_valid(self) -> None:
        chain = _make_example_chain()
        issues = validate_chain(chain)
        assert issues == []


# ---------------------------------------------------------------------------
# optimize_chain_order
# ---------------------------------------------------------------------------


class TestOptimizeChainOrder:
    def test_default_ordering_by_priority(self) -> None:
        providers = [
            _make_provider(name="Low", priority=2),
            _make_provider(name="High", priority=0),
            _make_provider(name="Mid", priority=1),
        ]
        chain = Chain(name="opt-test", providers=providers)
        optimized = optimize_chain_order(chain)

        assert optimized.providers[0].name == "High"
        assert optimized.providers[1].name == "Mid"
        assert optimized.providers[2].name == "Low"
        # Should have sequential priorities
        assert optimized.providers[0].priority == 0
        assert optimized.providers[1].priority == 1
        assert optimized.providers[2].priority == 2

    def test_ordering_by_latency(self) -> None:
        providers = [
            _make_provider(name="Slow", priority=0),
            _make_provider(name="Fast", priority=1),
            _make_provider(name="Medium", priority=2),
        ]
        chain = Chain(name="lat-test", providers=providers)
        latency_data = {"Slow": 3000.0, "Fast": 200.0, "Medium": 1000.0}

        optimized = optimize_chain_order(chain, latency_data)
        assert optimized.providers[0].name == "Fast"
        assert optimized.providers[1].name == "Medium"
        assert optimized.providers[2].name == "Slow"

    def test_latency_with_missing_data(self) -> None:
        providers = [
            _make_provider(name="Known", priority=0),
            _make_provider(name="Unknown", priority=1),
        ]
        chain = Chain(name="partial", providers=providers)
        latency_data = {"Known": 500.0}

        optimized = optimize_chain_order(chain, latency_data)
        # Known should come first (500ms), Unknown goes last (inf)
        assert optimized.providers[0].name == "Known"
        assert optimized.providers[1].name == "Unknown"

    def test_preserves_rules_and_metadata(self) -> None:
        rules = [FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER)]
        chain = Chain(
            name="preserve-test",
            providers=[_make_provider(name="A", priority=0), _make_provider(name="B", priority=1)],
            fallback_rules=rules,
            metadata={"key": "value"},
        )
        optimized = optimize_chain_order(chain)

        assert len(optimized.fallback_rules) == 1
        assert optimized.metadata == {"key": "value"}
        assert optimized.name == "preserve-test"

    def test_single_provider(self) -> None:
        chain = _make_chain(names=["Solo"])
        optimized = optimize_chain_order(chain)
        assert len(optimized.providers) == 1
        assert optimized.providers[0].name == "Solo"


# ---------------------------------------------------------------------------
# generate_chain_summary
# ---------------------------------------------------------------------------


class TestGenerateChainSummary:
    def test_basic_summary(self) -> None:
        chain = _make_chain()
        summary = generate_chain_summary(chain)

        assert "test-chain" in summary
        assert "Providers: 3" in summary
        assert "Alpha" in summary
        assert "Beta" in summary
        assert "Gamma" in summary

    def test_summary_with_rules(self) -> None:
        rules = [
            FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
            FallbackRule(
                condition_error_type="rate_limit",
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
        ]
        chain = _make_chain(rules=rules)
        summary = generate_chain_summary(chain)

        assert "Fallback rules: 2" in summary
        assert "timeout" in summary
        assert "rate_limit" in summary
        assert "wait" in summary
        assert "5" in summary
        assert "×3" in summary

    def test_summary_with_metadata(self) -> None:
        chain = Chain(
            name="meta-chain",
            providers=[_make_provider()],
            metadata={"description": "test chain", "version": "1.0"},
        )
        summary = generate_chain_summary(chain)
        assert "description" in summary

    def test_example_chain_summary(self) -> None:
        chain = _make_example_chain()
        summary = generate_chain_summary(chain)

        assert "example-chain" in summary
        assert "GPT-4o" in summary
        assert "Claude Sonnet" in summary
        assert "Local Llama" in summary
        assert "Fallback rules: 4" in summary

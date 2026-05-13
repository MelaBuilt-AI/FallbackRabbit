"""Tests for status code matching and retry/failover timing features."""

import asyncio

import pytest

from fallbackrabbit.models import (
    Chain,
    ErrorType,
    FallbackAction,
    FallbackRule,
    PromptSpec,
    Provider,
    SimulatedOutage,
)
from fallbackrabbit.simulator import _ERROR_STATUS_CODES, SimulatedProviderResponse, Simulator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_provider_chain() -> Chain:
    """Chain with two providers and fallback rules."""
    return Chain(
        name="test-chain",
        providers=[
            Provider(
                name="Primary", model_id="gpt-4o", api_base="https://api.openai.com", priority=0
            ),
            Provider(
                name="Backup",
                model_id="claude-sonnet",
                api_base="https://api.anthropic.com",
                priority=1,
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=2.0,
                retry_count=3,
            ),
            FallbackRule(
                condition_error_type=ErrorType.TIMEOUT,
                action=FallbackAction.FAILOVER,
            ),
            FallbackRule(
                condition_error_type=ErrorType.SERVER_ERROR,
                action=FallbackAction.RETRY,
                retry_count=2,
            ),
        ],
    )


@pytest.fixture
def three_provider_chain() -> Chain:
    """Chain with three providers."""
    return Chain(
        name="three-tier",
        providers=[
            Provider(name="Fast", model_id="gpt-4o", api_base="https://fast.test", priority=0),
            Provider(
                name="Medium", model_id="claude-sonnet", api_base="https://medium.test", priority=1
            ),
            Provider(name="Slow", model_id="llama-3", api_base="https://slow.test", priority=2),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=5.0,
                retry_count=2,
            ),
            FallbackRule(
                condition_error_type=ErrorType.CONNECTION_ERROR,
                action=FallbackAction.FAILOVER,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# SimulatedProviderResponse status codes
# ---------------------------------------------------------------------------


class TestSimulatedResponseStatusCodes:
    """Verify SimulatedProviderResponse carries status codes and error types."""

    def test_success_with_explicit_status_code(self):
        resp = SimulatedProviderResponse(success=True, latency_ms=100.0, status_code=200)
        assert resp.status_code == 200
        assert resp.error_type is None

    def test_error_carries_status_code(self):
        resp = SimulatedProviderResponse(
            success=False,
            latency_ms=0,
            error="Simulated rate_limit",
            status_code=429,
            error_type="rate_limit",
        )
        assert resp.status_code == 429
        assert resp.error_type == "rate_limit"

    def test_error_type_default_none(self):
        resp = SimulatedProviderResponse(success=True, latency_ms=100.0)
        assert resp.error_type is None

    def test_status_code_default_none(self):
        resp = SimulatedProviderResponse(success=True, latency_ms=100.0)
        assert resp.status_code is None


# ---------------------------------------------------------------------------
# Error-type → default status code mapping
# ---------------------------------------------------------------------------


class TestErrorStatusCodeMapping:
    """Verify the default status code mapping for error types."""

    def test_rate_limit_maps_to_429(self):
        assert _ERROR_STATUS_CODES["rate_limit"] == 429

    def test_timeout_maps_to_408(self):
        assert _ERROR_STATUS_CODES["timeout"] == 408

    def test_server_error_maps_to_500(self):
        assert _ERROR_STATUS_CODES["server_error"] == 500

    def test_connection_error_maps_to_503(self):
        assert _ERROR_STATUS_CODES["connection_error"] == 503


# ---------------------------------------------------------------------------
# Status code matching in fallback rules
# ---------------------------------------------------------------------------


class TestStatusCodeMatching:
    """Verify fallback rules match on status codes when specified."""

    def test_status_code_specific_rule_matches(self, two_provider_chain):
        """Rules with condition_status_codes should match when status code matches."""
        # Add a rule: 429 specifically → failover (overrides the generic rate_limit WAIT rule)
        two_provider_chain.fallback_rules.append(
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                condition_status_codes=[429],
                action=FallbackAction.FAILOVER,
            )
        )
        sim = Simulator(two_provider_chain)
        result = sim._determine_action(two_provider_chain, "rate_limit", status_code=429)
        assert result == FallbackAction.FAILOVER

    def test_no_status_code_rule_uses_error_type_only(self, two_provider_chain):
        """Without status code, the generic error-type rule should match."""
        sim = Simulator(two_provider_chain)
        # rate_limit → WAIT (no status code filter)
        result = sim._determine_action(two_provider_chain, "rate_limit")
        assert result == FallbackAction.WAIT

    def test_status_code_mismatch_falls_through(self, two_provider_chain):
        """If status code doesn't match the rule's codes, fall through to error-type-only rule."""
        # Add a rule: 503 → failover
        two_provider_chain.fallback_rules.append(
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                condition_status_codes=[503],
                action=FallbackAction.FAILOVER,
            )
        )
        sim = Simulator(two_provider_chain)
        # 429 doesn't match [503], so fall through to generic rate_limit → WAIT
        result = sim._determine_action(two_provider_chain, "rate_limit", status_code=429)
        assert result == FallbackAction.WAIT

    def test_no_matching_rule_returns_none(self, two_provider_chain):
        """Unknown error type with no matching rule returns None."""
        sim = Simulator(two_provider_chain)
        result = sim._determine_action(two_provider_chain, "unknown_error")
        assert result is None


# ---------------------------------------------------------------------------
# _get_wait_config
# ---------------------------------------------------------------------------


class TestGetWaitConfig:
    """Verify wait_seconds and retry_count lookup."""

    def test_rate_limit_wait_config(self, two_provider_chain):
        sim = Simulator(two_provider_chain)
        wait, retries = sim._get_wait_config(two_provider_chain, "rate_limit")
        assert wait == 2.0
        assert retries == 3

    def test_timeout_has_no_wait_config(self, two_provider_chain):
        sim = Simulator(two_provider_chain)
        wait, retries = sim._get_wait_config(two_provider_chain, "timeout")
        # timeout rule is FAILOVER, not WAIT — default is (0, 1)
        assert wait == 0.0
        assert retries == 1

    def test_status_code_specific_wait(self, two_provider_chain):
        """Status-code-specific rule takes priority over generic rule."""
        two_provider_chain.fallback_rules.append(
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                condition_status_codes=[429],
                action=FallbackAction.WAIT,
                wait_seconds=1.0,
                retry_count=5,
            )
        )
        sim = Simulator(two_provider_chain)
        wait, retries = sim._get_wait_config(two_provider_chain, "rate_limit", status_code=429)
        assert wait == 1.0
        assert retries == 5

    def test_status_code_mismatch_uses_generic(self, two_provider_chain):
        """Status code that doesn't match specific rule falls back to generic."""
        two_provider_chain.fallback_rules.append(
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                condition_status_codes=[429],
                action=FallbackAction.WAIT,
                wait_seconds=1.0,
                retry_count=5,
            )
        )
        sim = Simulator(two_provider_chain)
        # 503 doesn't match [429], so falls back to generic rate_limit → WAIT 2.0s × 3
        wait, retries = sim._get_wait_config(two_provider_chain, "rate_limit", status_code=503)
        assert wait == 2.0
        assert retries == 3


# ---------------------------------------------------------------------------
# Retry timing in PromptResult
# ---------------------------------------------------------------------------


class TestRetryTiming:
    """Verify PromptResult tracks retries_used and total_wait_ms."""

    def test_successful_result_has_zero_retries(self, two_provider_chain):
        sim = Simulator(two_provider_chain)
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        assert result.retries_used == 0
        assert result.total_wait_ms == 0.0

    def test_rate_limit_outage_with_wait_rule_tracks_retries(self, two_provider_chain):
        """When primary hits rate_limit (WAIT rule with retry_count=3),
        retries_used and total_wait_ms should be tracked."""
        sim = Simulator(
            two_provider_chain,
            outages=[
                SimulatedOutage(
                    provider_name="Primary",
                    error_type=ErrorType.RATE_LIMIT,
                    probability=1.0,
                ),
            ],
        )
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        # Primary fails (rate_limit), wait rule retries 3 times
        # All retries also fail (prob=1), then fails over to Backup
        assert result.fallback_triggered is True
        # 3 retries on Primary = 3 retries_used
        assert result.retries_used == 3
        # 3 retries × 2.0s wait = 6000ms
        assert result.total_wait_ms == 6000.0

    def test_all_providers_down_tracks_retries(self, three_provider_chain):
        """When all providers are down, retries are tracked in the final result."""
        sim = Simulator(
            three_provider_chain,
            outages=[
                SimulatedOutage(
                    provider_name="Fast", error_type=ErrorType.RATE_LIMIT, probability=1.0
                ),
                SimulatedOutage(
                    provider_name="Medium", error_type=ErrorType.CONNECTION_ERROR, probability=1.0
                ),
                SimulatedOutage(
                    provider_name="Slow", error_type=ErrorType.SERVER_ERROR, probability=1.0
                ),
            ],
        )
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        assert result.success is False
        # Fast: rate_limit → WAIT (2 retries) → 2 retries, 2×5.0s = 10000ms
        # Medium: connection_error → FAILOVER (no retries)
        # Slow: server_error → RETRY but no WAIT rule → defaults to (0, 1)
        # Total retries: 2 (from Fast)
        assert result.retries_used == 2
        assert result.total_wait_ms == 10000.0

    def test_failover_no_retries_no_wait(self, two_provider_chain):
        """Timeout → FAILOVER should have 0 retries and 0 wait."""
        sim = Simulator(
            two_provider_chain,
            outages=[
                SimulatedOutage(
                    provider_name="Primary",
                    error_type=ErrorType.TIMEOUT,
                    probability=1.0,
                ),
            ],
        )
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        # Timeout → FAILOVER to Backup
        assert result.success is True
        assert result.provider_name == "Backup"
        assert result.retries_used == 0
        assert result.total_wait_ms == 0.0


# ---------------------------------------------------------------------------
# Outage with custom status code
# ---------------------------------------------------------------------------


class TestOutageWithStatusCode:
    """Verify SimulatedOutage status_code field flows through simulation."""

    def test_custom_status_code_in_outage(self, two_provider_chain):
        """Outage with custom status_code should appear in the simulated response."""
        outage = SimulatedOutage(
            provider_name="Primary",
            error_type=ErrorType.RATE_LIMIT,
            probability=1.0,
            status_code=429,
        )
        sim = Simulator(two_provider_chain, outages=[outage])
        resp = sim._simulate_provider_call(
            two_provider_chain.providers[0],
            PromptSpec(prompt="test"),
        )
        assert resp.status_code == 429
        assert resp.error_type == "rate_limit"

    def test_default_status_code_for_error_type(self, two_provider_chain):
        """Outage without explicit status_code gets the default for its error type."""
        outage = SimulatedOutage(
            provider_name="Primary",
            error_type=ErrorType.TIMEOUT,
            probability=1.0,
        )
        sim = Simulator(two_provider_chain, outages=[outage])
        resp = sim._simulate_provider_call(
            two_provider_chain.providers[0],
            PromptSpec(prompt="test"),
        )
        assert resp.status_code == 408  # Default for timeout
        assert resp.error_type == "timeout"

    def test_custom_status_code_overrides_default(self, two_provider_chain):
        """Explicit status_code on outage overrides the error-type default."""
        outage = SimulatedOutage(
            provider_name="Primary",
            error_type=ErrorType.RATE_LIMIT,
            probability=1.0,
            status_code=503,  # Custom: normally rate_limit → 429
        )
        sim = Simulator(two_provider_chain, outages=[outage])
        resp = sim._simulate_provider_call(
            two_provider_chain.providers[0],
            PromptSpec(prompt="test"),
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Full integration: status code matching + retry/failover timing
# ---------------------------------------------------------------------------


class TestStatusCodeIntegration:
    """End-to-end tests combining status code matching with retry/failover timing."""

    def test_status_code_429_specific_rule_overrides(self):
        """A 429-specific FAILOVER rule should override generic rate_limit WAIT rule."""
        chain = Chain(
            name="status-code-test",
            providers=[
                Provider(name="P1", model_id="gpt-4o", api_base="https://p1.test", priority=0),
                Provider(name="P2", model_id="claude", api_base="https://p2.test", priority=1),
            ],
            fallback_rules=[
                # Generic: rate_limit → WAIT
                FallbackRule(
                    condition_error_type=ErrorType.RATE_LIMIT,
                    action=FallbackAction.WAIT,
                    wait_seconds=5.0,
                    retry_count=3,
                ),
                # Specific: 429 → FAILOVER (should take priority)
                FallbackRule(
                    condition_error_type=ErrorType.RATE_LIMIT,
                    condition_status_codes=[429],
                    action=FallbackAction.FAILOVER,
                ),
            ],
        )
        sim = Simulator(
            chain,
            outages=[
                SimulatedOutage(
                    provider_name="P1",
                    error_type=ErrorType.RATE_LIMIT,
                    probability=1.0,
                    status_code=429,
                ),
            ],
        )
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        # P1 fails with 429 → FAILOVER (not WAIT) → P2 succeeds
        assert result.success is True
        assert result.provider_name == "P2"
        # No retries should have been attempted (FAILOVER, not WAIT)
        assert result.retries_used == 0
        assert result.total_wait_ms == 0.0

    def test_result_has_status_code_on_success(self, two_provider_chain):
        """Successful result should include status_code=200."""
        sim = Simulator(two_provider_chain)
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        assert result.success is True
        assert result.status_code == 200

    def test_rate_limit_503_triggers_generic_wait(self):
        """A 503 status code on rate_limit should use generic WAIT rule (no specific 429 match)."""
        chain = Chain(
            name="status-code-generic",
            providers=[
                Provider(name="P1", model_id="gpt-4o", api_base="https://p1.test", priority=0),
                Provider(name="P2", model_id="claude", api_base="https://p2.test", priority=1),
            ],
            fallback_rules=[
                # Generic: rate_limit → WAIT 1s × 2
                FallbackRule(
                    condition_error_type=ErrorType.RATE_LIMIT,
                    action=FallbackAction.WAIT,
                    wait_seconds=1.0,
                    retry_count=2,
                ),
                # Specific: 429 → FAILOVER
                FallbackRule(
                    condition_error_type=ErrorType.RATE_LIMIT,
                    condition_status_codes=[429],
                    action=FallbackAction.FAILOVER,
                ),
            ],
        )
        sim = Simulator(
            chain,
            outages=[
                SimulatedOutage(
                    provider_name="P1",
                    error_type=ErrorType.RATE_LIMIT,
                    probability=1.0,
                    status_code=503,  # Not 429, so generic rule applies
                ),
            ],
        )
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="Hello")))
        # P1 fails with 503 → generic rate_limit WAIT rule → 2 retries × 1s → then FAILOVER to P2
        assert result.success is True
        assert result.provider_name == "P2"
        # 2 retries on P1, 2000ms total wait
        assert result.retries_used == 2
        assert result.total_wait_ms == 2000.0

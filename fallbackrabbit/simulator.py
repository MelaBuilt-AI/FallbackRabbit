"""Simulator — simulate LLM provider behavior with outage injection and fallback routing.

Supports two modes:
- **Simulated** (default): Uses mock latency profiles and outage injection.
- **Real**: Uses AsyncProviderClient to make actual API calls.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import (
    Chain,
    ChainReport,
    FallbackAction,
    PromptResult,
    PromptSpec,
    Provider,
    SimulatedOutage,
)

if TYPE_CHECKING:
    from .providers import AsyncProviderClient, ProviderResponse


# ---------------------------------------------------------------------------
# Latency profiles by model type
# ---------------------------------------------------------------------------

_LATENCY_PROFILES: dict[str, tuple[float, float]] = {
    # GPT-4 class: 1-3 seconds
    "gpt": (1000.0, 3000.0),
    "gpt-4": (1000.0, 3000.0),
    "gpt-4o": (1000.0, 3000.0),
    # Claude class: 0.5-2 seconds
    "claude": (500.0, 2000.0),
    "claude-sonnet": (500.0, 2000.0),
    # Local models: 0.2-1 second
    "llama": (200.0, 1000.0),
    "ollama": (200.0, 1000.0),
    "local": (200.0, 1000.0),
}

_DEFAULT_LATENCY: tuple[float, float] = (500.0, 2000.0)

# Default HTTP status codes for each error type
_ERROR_STATUS_CODES: dict[str, int] = {
    "rate_limit": 429,
    "timeout": 408,
    "server_error": 500,
    "connection_error": 503,
}


def _get_latency_range(provider: Provider) -> tuple[float, float]:
    """Return (min_ms, max_ms) latency range based on provider model_id."""
    model_id = provider.model_id.lower()
    for key, latency_range in _LATENCY_PROFILES.items():
        if key in model_id:
            return latency_range
    return _DEFAULT_LATENCY


@dataclass
class SimulatedProviderResponse:
    """A simulated response from a provider."""

    success: bool
    latency_ms: float
    error: str | None = None
    fallback_triggered: bool = False
    status_code: int | None = None
    error_type: str | None = None


class Simulator:
    """Simulate or execute LLM provider calls with configurable fallback chains.

    Args:
        chain: The fallback chain configuration.
        outages: Simulated outage configurations (simulated mode only).
        use_real_calls: When True, make real API calls via AsyncProviderClient.
            When False (default), use simulated latency profiles.
        provider_client: Optional pre-configured AsyncProviderClient.
            If not provided and use_real_calls=True, one will be created
            automatically and closed when the simulator is closed.

    Usage:
        chain = load_chain("schemas/example_chain.yaml")
        outages = load_outage_scenario("schemas/example_outage.yaml")

        # Simulated mode (default)
        sim = Simulator(chain, outages)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))

        # Real calls mode
        sim = Simulator(chain, use_real_calls=True)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
    """

    def __init__(
        self,
        chain: Chain,
        outages: list[SimulatedOutage] | None = None,
        use_real_calls: bool = False,
        provider_client: AsyncProviderClient | None = None,
    ) -> None:
        self.chain = chain
        self.outages: dict[str, list[SimulatedOutage]] = {}
        self.use_real_calls = use_real_calls
        self._external_client = provider_client is not None
        self._client = provider_client
        if outages:
            for outage in outages:
                self.inject_outage(outage.provider_name, outage)

    def inject_outage(self, provider_name: str, outage: SimulatedOutage) -> None:
        """Configure outage simulation for a provider.

        Args:
            provider_name: The provider to apply the outage to.
            outage: The outage configuration.
        """
        self.outages.setdefault(provider_name, []).append(outage)

    def _should_trigger_outage(self, provider_name: str) -> bool:
        """Check if an outage should be triggered for a provider (probability-based).

        Args:
            provider_name: The provider to check.

        Returns:
            True if an outage should be triggered.
        """
        provider_outages = self.outages.get(provider_name, [])
        return any(random.random() < outage.probability for outage in provider_outages)

    def _simulate_provider_call(
        self, provider: Provider, prompt: PromptSpec
    ) -> SimulatedProviderResponse:
        """Mock a provider call with configurable latency and outage injection.

        Args:
            provider: The provider to simulate calling.
            prompt: The prompt being sent.

        Returns:
            A SimulatedProviderResponse with success/error info and latency.
        """
        # Check for outage
        if self._should_trigger_outage(provider.name):
            # Pick a random matching outage
            provider_outages = self.outages.get(provider.name, [])
            active_outage = random.choice(provider_outages)
            error_type = active_outage.error_type.value
            # Use outage status code, or default for the error type
            status_code = active_outage.status_code or _ERROR_STATUS_CODES.get(error_type, 500)
            return SimulatedProviderResponse(
                success=False,
                latency_ms=0.0,
                error=f"Simulated {error_type}",
                fallback_triggered=True,
                status_code=status_code,
                error_type=error_type,
            )

        # Simulate normal response latency with jitter
        min_ms, max_ms = _get_latency_range(provider)
        latency_ms = random.uniform(min_ms, max_ms)

        # Small chance of random failure (1%)
        if random.random() < 0.01:
            return SimulatedProviderResponse(
                success=False,
                latency_ms=latency_ms,
                error="Simulated server_error",
                fallback_triggered=True,
                status_code=500,
                error_type="server_error",
            )

        return SimulatedProviderResponse(
            success=True,
            latency_ms=latency_ms,
            status_code=200,
        )

    def _apply_fallback(self, chain: Chain, failed_provider: str, error: str) -> str | None:
        """Determine next provider in the fallback chain.

        Args:
            chain: The chain configuration.
            failed_provider: Name of the provider that failed.
            error: The error message.

        Returns:
            Name of the next provider to try, or None if no fallback available.
        """
        sorted_providers = sorted(chain.providers, key=lambda p: p.priority)
        provider_names = [p.name for p in sorted_providers]

        if failed_provider not in provider_names:
            return None

        idx = provider_names.index(failed_provider)
        if idx + 1 < len(provider_names):
            return provider_names[idx + 1]
        return None

    def _determine_action(
        self, chain: Chain, error_type_str: str, status_code: int | None = None
    ) -> FallbackAction | None:
        """Look up the fallback action for an error type and optional status code.

        Status-code matching takes priority: if a rule specifies condition_status_codes
        and the response status code matches, that rule wins. Otherwise falls back to
        error-type-only matching.

        Args:
            chain: The chain configuration.
            error_type_str: The error type string (e.g. 'rate_limit').
            status_code: Optional HTTP status code from the response.

        Returns:
            The FallbackAction to take, or None if no rule matches.
        """
        # First: try status-code-specific match
        if status_code is not None:
            for rule in chain.fallback_rules:
                if (
                    rule.condition_error_type.value == error_type_str
                    and rule.condition_status_codes
                    and status_code in rule.condition_status_codes
                ):
                    return rule.action

        # Then: error-type-only match (rules without status codes, or no code provided)
        for rule in chain.fallback_rules:
            if (
                rule.condition_error_type.value == error_type_str
                and not rule.condition_status_codes
            ):
                return rule.action

        return None

    def _get_wait_config(
        self, chain: Chain, error_type_str: str, status_code: int | None = None
    ) -> tuple[float, int]:
        """Get wait_seconds and retry_count for a matching rule.

        Status-code-specific rules take priority. Falls back to error-type-only rules.

        Returns:
            (wait_seconds, retry_count) — defaults to (0, 1) if no rule matches.
        """
        # First: status-code-specific match
        if status_code is not None:
            for rule in chain.fallback_rules:
                if (
                    rule.condition_error_type.value == error_type_str
                    and rule.condition_status_codes
                    and status_code in rule.condition_status_codes
                ):
                    return rule.wait_seconds, rule.retry_count

        # Then: error-type-only (no status codes)
        for rule in chain.fallback_rules:
            if (
                rule.condition_error_type.value == error_type_str
                and not rule.condition_status_codes
            ):
                return rule.wait_seconds, rule.retry_count

        return 0.0, 1

    def _convert_real_response(
        self, response: ProviderResponse, prompt_id: str, fell_back: bool
    ) -> PromptResult:
        """Convert a real ProviderResponse to a PromptResult."""
        return PromptResult(
            provider_name=response.model or "unknown",
            prompt_id=prompt_id,
            success=response.success,
            latency_ms=response.latency_ms,
            error=response.error,
            fallback_triggered=fell_back,
        )

    async def _get_client(self) -> AsyncProviderClient:
        """Get or create the AsyncProviderClient."""
        if self._client is None:
            from .providers import AsyncProviderClient

            self._client = AsyncProviderClient()
        return self._client

    async def close(self) -> None:
        """Close the provider client if we own it."""
        if self._client and not self._external_client:
            await self._client.close()

    async def run_prompt(self, prompt: PromptSpec) -> PromptResult:
        """Send a prompt through the chain, respecting fallback order.

        In simulated mode, uses mock latency profiles and outage injection.
        In real mode, makes actual API calls via AsyncProviderClient.

        Args:
            prompt: The prompt specification to test.

        Returns:
            A PromptResult for the final outcome (success or all-failed).
        """
        prompt_id = str(uuid.uuid4())[:8]
        sorted_providers = sorted(self.chain.providers, key=lambda p: p.priority)

        if self.use_real_calls:
            return await self._run_prompt_real(prompt, prompt_id, sorted_providers)
        return await self._run_prompt_simulated(prompt, prompt_id, sorted_providers)

    async def _run_prompt_real(
        self,
        prompt: PromptSpec,
        prompt_id: str,
        sorted_providers: list[Provider],
    ) -> PromptResult:
        """Execute prompt using real provider calls."""
        client = await self._get_client()
        fell_back = False
        total_retries = 0
        total_wait_ms = 0.0

        for provider in sorted_providers:
            response = await client.call_provider(provider, prompt.prompt)
            status_code = getattr(response, "status_code", None)

            if response.success:
                return PromptResult(
                    provider_name=provider.name,
                    prompt_id=prompt_id,
                    success=True,
                    latency_ms=response.latency_ms,
                    error=None,
                    fallback_triggered=fell_back,
                    status_code=status_code or 200,
                    retries_used=total_retries,
                    total_wait_ms=total_wait_ms,
                )

            # Provider failed
            fell_back = True
            error_type_str = response.error_type.value if response.error_type else "server_error"

            action = self._determine_action(self.chain, error_type_str, status_code)

            if action == FallbackAction.WAIT:
                wait_seconds, retry_count = self._get_wait_config(
                    self.chain, error_type_str, status_code
                )
                for _ in range(retry_count):
                    import asyncio as _asyncio

                    await _asyncio.sleep(wait_seconds)
                    total_wait_ms += wait_seconds * 1000
                    total_retries += 1
                    response2 = await client.call_provider(provider, prompt.prompt)
                    if response2.success:
                        return PromptResult(
                            provider_name=provider.name,
                            prompt_id=prompt_id,
                            success=True,
                            latency_ms=response2.latency_ms,
                            error=None,
                            fallback_triggered=True,
                            status_code=getattr(response2, "status_code", None) or 200,
                            retries_used=total_retries,
                            total_wait_ms=total_wait_ms,
                        )

            # Fall through to next provider (failover)
            continue

        # All providers failed
        last_provider = sorted_providers[-1]
        return PromptResult(
            provider_name=last_provider.name,
            prompt_id=prompt_id,
            success=False,
            latency_ms=0.0,
            error="All providers in chain failed",
            fallback_triggered=True,
            retries_used=total_retries,
            total_wait_ms=total_wait_ms,
        )

    async def _run_prompt_simulated(
        self,
        prompt: PromptSpec,
        prompt_id: str,
        sorted_providers: list[Provider],
    ) -> PromptResult:
        """Simulate prompt using mock latency profiles."""
        fell_back = False
        total_retries = 0
        total_wait_ms = 0.0

        for provider in sorted_providers:
            resp = self._simulate_provider_call(provider, prompt)

            if resp.success:
                return PromptResult(
                    provider_name=provider.name,
                    prompt_id=prompt_id,
                    success=True,
                    latency_ms=resp.latency_ms,
                    error=None,
                    fallback_triggered=fell_back or resp.fallback_triggered,
                    status_code=resp.status_code or 200,
                    retries_used=total_retries,
                    total_wait_ms=total_wait_ms,
                )

            # Provider failed — we're falling back
            fell_back = True
            error_type_str = resp.error_type or (resp.error or "").replace("Simulated ", "").strip()

            action = self._determine_action(self.chain, error_type_str, resp.status_code)

            if action == FallbackAction.WAIT:
                wait_seconds, retry_count = self._get_wait_config(
                    self.chain, error_type_str, resp.status_code
                )
                for _ in range(retry_count):
                    # Simulate wait (track time but don't actually sleep)
                    total_wait_ms += wait_seconds * 1000
                    total_retries += 1
                    fell_back = True
                    resp2 = self._simulate_provider_call(provider, prompt)
                    if resp2.success:
                        return PromptResult(
                            provider_name=provider.name,
                            prompt_id=prompt_id,
                            success=True,
                            latency_ms=resp2.latency_ms,
                            error=None,
                            fallback_triggered=True,
                            status_code=resp2.status_code or 200,
                            retries_used=total_retries,
                            total_wait_ms=total_wait_ms,
                        )

            # Fall through to next provider (failover)
            continue

        # All providers failed
        last_provider = sorted_providers[-1]
        return PromptResult(
            provider_name=last_provider.name,
            prompt_id=prompt_id,
            success=False,
            latency_ms=0.0,
            error="All providers in chain failed",
            fallback_triggered=True,
            retries_used=total_retries,
            total_wait_ms=total_wait_ms,
        )

    async def run_batch(self, prompts: list[PromptSpec]) -> ChainReport:
        """Run multiple prompts and aggregate results.

        Args:
            prompts: List of prompts to test.

        Returns:
            A ChainReport with aggregated results.
        """
        results: list[PromptResult] = []
        for prompt in prompts:
            result = await self.run_prompt(prompt)
            results.append(result)

        total = len(prompts)
        successes = [r for r in results if r.success]
        fallbacks = [r for r in results if r.fallback_triggered]
        success_latencies = [r.latency_ms for r in successes]

        return ChainReport(
            chain_name=self.chain.name,
            total_prompts=total,
            results=results,
            success_rate=len(successes) / total if total else 0.0,
            avg_latency_ms=sum(success_latencies) / len(success_latencies)
            if success_latencies
            else 0.0,
            fallback_rate=len(fallbacks) / len(results) if results else 0.0,
        )


def generate_test_prompts(n: int = 5) -> list[PromptSpec]:
    """Generate a set of default test prompts covering different categories.

    Args:
        n: Number of prompts to generate (minimum 5 for category coverage).

    Returns:
        A list of PromptSpec instances.
    """
    categories: list[tuple[str, str, str]] = [
        ("general", "What is the capital of France?", "returns a valid response"),
        ("creative", "Write a haiku about programming.", "returns creative content"),
        ("factual", "What is 2 + 2?", "returns a factual answer"),
        ("code", "Write a Python function that reverses a string.", "returns code"),
        (
            "complex",
            "Explain the difference between TCP and UDP protocols.",
            "returns a detailed explanation",
        ),
    ]

    prompts: list[PromptSpec] = []
    for i in range(max(n, 5)):
        cat, prompt_text, expected = categories[i % len(categories)]
        prompts.append(
            PromptSpec(
                prompt=prompt_text,
                category=cat,
                expected_behavior=expected,
            )
        )

    return prompts

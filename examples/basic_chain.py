"""Example: Create a simple fallback chain and simulate an outage."""

from fallbackrabbit.models import Chain, Provider, FallbackRule, ErrorType, FallbackAction
from fallbackrabbit.chain_builder import validate_chain, optimize_chain_order
from fallbackrabbit.simulator import Simulator, generate_test_prompts
import asyncio


async def main():
    # Define a 3-provider chain
    chain = Chain(
        name="production-chain",
        providers=[
            Provider(name="GPT-4", model_id="gpt-4", api_base="https://api.openai.com/v1", priority=0),
            Provider(name="Claude", model_id="claude-3-sonnet", api_base="https://api.anthropic.com", priority=1),
            Provider(name="Llama3", model_id="llama3", api_base="http://localhost:11434", priority=2),
        ],
        fallback_rules=[
            FallbackRule(
                condition=ErrorType.RATE_LIMIT,
                action=FallbackAction.RETRY,
                max_retries=2,
                wait_seconds=1.0,
            ),
            FallbackRule(
                condition=ErrorType.TIMEOUT,
                action=FallbackAction.FAILOVER,
            ),
            FallbackRule(
                condition=ErrorType.SERVER_ERROR,
                action=FallbackAction.FAILOVER,
            ),
        ],
    )

    # Validate
    issues = validate_chain(chain)
    if issues:
        print(f"Validation issues: {issues}")
    else:
        print("✓ Chain is valid")

    # Optimize
    optimized = optimize_chain_order(chain)
    print(f"✓ Optimized order: {[p.name for p in optimized.providers]}")

    # Simulate with test prompts
    prompts = generate_test_prompts(5)
    sim = Simulator(chain=chain)
    report = await sim.run_batch(prompts)

    print(f"\n{'='*50}")
    print(f"Test Report: {report.total_prompts} prompts")
    print(f"Successful: {report.successful}/{report.total_prompts}")
    print(f"Failed: {report.failed}/{report.total_prompts}")
    print(f"Success rate: {report.success_rate:.1%}")
    print(f"Avg latency: {report.avg_latency_ms:.0f}ms")
    print(f"{'='*50}")

    for r in report.results:
        status = "✅" if r.success else "❌"
        print(f"  {status} {r.prompt_id}: {r.provider} ({r.latency_ms:.0f}ms)")


if __name__ == "__main__":
    asyncio.run(main())
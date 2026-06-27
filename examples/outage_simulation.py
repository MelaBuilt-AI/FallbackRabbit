"""Example: Simulate outages to test chain resilience."""

from fallbackrabbit.models import Chain, Provider, SimulatedOutage, ErrorType
from fallbackrabbit.simulator import Simulator, generate_test_prompts
import asyncio


async def main():
    chain = Chain(
        name="resilience-test",
        providers=[
            Provider(name="Primary-GPT4", model_id="gpt-4", api_base="https://api.openai.com/v1", priority=0),
            Provider(name="Backup-Claude", model_id="claude-3-sonnet", api_base="https://api.anthropic.com", priority=1),
            Provider(name="Fallback-Ollama", model_id="llama3", api_base="http://localhost:11434", priority=2),
        ],
    )

    # Simulate primary provider timeout
    print("🔴 Simulating primary provider timeout...")
    sim = Simulator(chain=chain)
    sim.inject_outage("Primary-GPT4", SimulatedOutage(
        provider="Primary-GPT4",
        error_type=ErrorType.TIMEOUT,
        probability=1.0,  # Always fail
    ))

    prompts = generate_test_prompts(10)
    report = await sim.run_batch(prompts)

    print(f"Results with primary down:")
    print(f"  Success rate: {report.success_rate:.1%}")
    print(f"  Avg latency: {report.avg_latency_ms:.0f}ms")
    print(f"  Failed: {report.failed}")

    # Simulate ALL providers down
    print("\n🔴 Simulating total outage...")
    sim2 = Simulator(chain=chain)
    sim2.inject_outage("Primary-GPT4", SimulatedOutage(provider="Primary-GPT4", error_type=ErrorType.SERVER_ERROR, probability=1.0))
    sim2.inject_outage("Backup-Claude", SimulatedOutage(provider="Backup-Claude", error_type=ErrorType.SERVER_ERROR, probability=1.0))
    sim2.inject_outage("Fallback-Ollama", SimulatedOutage(provider="Fallback-Ollama", error_type=ErrorType.SERVER_ERROR, probability=1.0))

    report2 = await sim2.run_batch(prompts)
    print(f"Results with all providers down:")
    print(f"  Success rate: {report2.success_rate:.1%}")
    print(f"  Failed: {report2.failed}")

    # Simulate rate limiting on primary
    print("\n🟡 Simulating rate limit on primary...")
    sim3 = Simulator(chain=chain)
    sim3.inject_outage("Primary-GPT4", SimulatedOutage(
        provider="Primary-GPT4",
        error_type=ErrorType.RATE_LIMIT,
        probability=0.5,  # 50% of requests get rate limited
    ))

    report3 = await sim3.run_batch(prompts)
    print(f"Results with intermittent rate limiting:")
    print(f"  Success rate: {report3.success_rate:.1%}")
    print(f"  Avg latency: {report3.avg_latency_ms:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
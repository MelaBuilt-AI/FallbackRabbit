"""Example: Use the FallbackRabbit REST API from Python."""

import httpx
import asyncio


async def main():
    base = "http://localhost:8000"

    async with httpx.AsyncClient() as client:
        # Health check
        resp = await client.get(f"{base}/health")
        print(f"Health: {resp.json()}")

        # Create a chain
        resp = await client.post(f"{base}/chains", json={
            "name": "api-example-chain",
            "providers": [
                {"name": "GPT-4", "model_id": "gpt-4", "api_base": "https://api.openai.com/v1", "priority": 0},
                {"name": "Claude", "model_id": "claude-3-sonnet", "api_base": "https://api.anthropic.com", "priority": 1},
            ],
            "fallback_rules": [
                {"condition": "timeout", "action": "failover"},
                {"condition": "rate_limit", "action": "retry", "max_retries": 2, "wait_seconds": 1.0},
            ],
        })
        chain = resp.json()
        chain_id = chain["chain_id"]
        print(f"Created chain: {chain_id}")

        # List chains
        resp = await client.get(f"{base}/chains")
        print(f"All chains: {len(resp.json())} found")

        # Test the chain
        resp = await client.post(f"{base}/chains/{chain_id}/test", json={"prompts": 3})
        report = resp.json()
        print(f"Test results: {report['successful']}/{report['total_prompts']} successful")

        # Export to LiteLLM
        resp = await client.post(f"{base}/chains/{chain_id}/export", json={"format": "litellm"})
        print(f"LiteLLM export: {resp.json()}")

        # Validate
        resp = await client.get(f"{base}/chains/{chain_id}/validate")
        print(f"Validation: {resp.json()}")

        # Clean up
        await client.delete(f"{base}/chains/{chain_id}")
        print(f"Deleted chain: {chain_id}")


if __name__ == "__main__":
    asyncio.run(main())
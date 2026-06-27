"""Example: Load a chain from YAML config."""

from fallbackrabbit.chain_schema import load_chain
from fallbackrabbit.chain_builder import validate_chain, generate_chain_summary
from fallbackrabbit.config_export import export_litellm
import asyncio
from fallbackrabbit.simulator import Simulator, generate_test_prompts


def main():
    # Load from YAML
    chain = load_chain("schemas/example_chain.yaml")
    print(f"Loaded chain: {chain.name}")
    print(f"Providers: {[p.name for p in chain.providers]}")

    # Validate
    issues = validate_chain(chain)
    if issues:
        print(f"Issues: {issues}")
    else:
        print("✓ Chain is valid")

    # Summary
    summary = generate_chain_summary(chain)
    print(f"\n{summary}")

    # Export
    litellm_config = export_litellm(chain, output_path="my-chain-litellm.yaml")
    print(f"\nExported LiteLLM config to my-chain-litellm.yaml")


if __name__ == "__main__":
    main()
"""Example: Export a chain config to multiple formats."""

from fallbackrabbit.models import Chain, Provider, ExportFormat
from fallbackrabbit.config_export import export_litellm, export_langchain, export_haystack
from fallbackrabbit.template_export import render_template, BUILTIN_TEMPLATES


def main():
    chain = Chain(
        name="my-app-chain",
        providers=[
            Provider(name="GPT-4o", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0),
            Provider(name="Claude", model_id="claude-3-sonnet", api_base="https://api.anthropic.com", priority=1),
            Provider(name="Ollama", model_id="llama3", api_base="http://localhost:11434", priority=2),
        ],
    )

    # Export to LiteLLM
    litellm_config = export_litellm(chain)
    print("=== LiteLLM Config ===")
    print(litellm_config)

    # Export to LangChain
    langchain_config = export_langchain(chain)
    print("\n=== LangChain Config ===")
    print(langchain_config)

    # Export to Haystack
    haystack_config = export_haystack(chain)
    print("\n=== Haystack Config ===")
    print(haystack_config)

    # Export using built-in templates
    for name in BUILTIN_TEMPLATES:
        output = render_template(chain, BUILTIN_TEMPLATES[name])
        print(f"\n=== {name.title()} Template ===")
        print(output)


if __name__ == "__main__":
    main()
"""Config export — export chains to deploy-ready formats (LiteLLM, OpenRouter, Custom)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import Chain, ExportFormat


def export_litellm(chain: Chain, output_path: str | None = None) -> str:
    """Export a Chain to LiteLLM proxy config YAML format.

    Produces a model_list with model_name, litellm_params (api_base, api_key, model),
    and fallback routing configuration.

    Args:
        chain: The chain to export.
        output_path: Optional file path to write the output. If None, returns string.

    Returns:
        YAML string of the LiteLLM configuration.
    """
    model_list = []
    for provider in chain.providers:
        entry: dict = {
            "model_name": chain.name,
            "litellm_params": {
                "model": provider.model_id,
                "api_base": provider.api_base,
                "timeout": provider.timeout,
                "max_tokens": provider.max_tokens,
            },
        }
        # Include metadata keys that map to litellm params
        if provider.metadata:
            if "api_key" in provider.metadata:
                entry["litellm_params"]["api_key"] = provider.metadata["api_key"]
            if "provider_type" in provider.metadata:
                entry["litellm_params"]["custom_llm_provider"] = provider.metadata["provider_type"]
        model_list.append(entry)

    # Build fallback configuration
    # LiteLLM uses fallbacks as a list of model_name groups
    fallbacks: list[list[str]] = []
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)
    for _i in range(len(sorted_providers) - 1):
        fallbacks.append([chain.name])

    # Build router config with timeout and retry settings
    router_config: dict = {
        "model_list": model_list,
    }
    if fallbacks:
        router_config["fallbacks"] = fallbacks

    # Add timeout and retry config from chain metadata
    router_config["router_settings"] = {
        "num_retries": 3,
        "timeout": max(p.timeout for p in chain.providers),
        "retry_after_time": 5,
    }

    # Add fallback rule configuration
    if chain.fallback_rules:
        router_config["fallback_rules"] = [
            {
                "error_type": rule.condition_error_type.value,
                "action": rule.action.value,
                "wait_seconds": rule.wait_seconds,
                "retry_count": rule.retry_count,
            }
            for rule in chain.fallback_rules
        ]

    output = yaml.dump(router_config, default_flow_style=False, sort_keys=False)

    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")

    return output


def export_openrouter(chain: Chain, output_path: str | None = None) -> str:
    """Export a Chain to OpenRouter config JSON format.

    Produces a configuration with model priorities, routing, and fallback settings.

    Args:
        chain: The chain to export.
        output_path: Optional file path to write the output. If None, returns string.

    Returns:
        JSON string of the OpenRouter configuration.
    """
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    models = []
    for provider in sorted_providers:
        model_entry: dict = {
            "model": provider.model_id,
            "priority": provider.priority,
            "max_tokens": provider.max_tokens,
            "timeout": provider.timeout,
        }
        if provider.metadata:
            model_entry["metadata"] = provider.metadata
        models.append(model_entry)

    config: dict = {
        "models": models,
        "fallback_order": [p.model_id for p in sorted_providers],
        "routing": {
            "strategy": "priority",
            "failover_on": [rule.condition_error_type.value for rule in chain.fallback_rules],
        },
    }

    # Add fallback rules as routing configuration
    if chain.fallback_rules:
        config["fallback_rules"] = [
            {
                "error_type": rule.condition_error_type.value,
                "action": rule.action.value,
                "wait_seconds": rule.wait_seconds,
                "retry_count": rule.retry_count,
            }
            for rule in chain.fallback_rules
        ]

    output = json.dumps(config, indent=2)

    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")

    return output


def export_custom(chain: Chain, output_path: str | None = None) -> dict:
    """Export a Chain as a generic Python dict with routing logic,
    provider configs, and fallback rules.

    This is the FallbackRabbit native format — a complete, self-contained configuration.

    Args:
        chain: The chain to export.
        output_path: Optional file path to write the output (as JSON). If None, returns dict only.

    Returns:
        A dict with full chain configuration including routing logic.
    """
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    # Build routing table
    routing_table = []
    for idx, provider in enumerate(sorted_providers):
        failover_targets = [p.name for p in sorted_providers[idx + 1 :]]
        routing_table.append(
            {
                "provider_name": provider.name,
                "model_id": provider.model_id,
                "api_base": provider.api_base,
                "priority": provider.priority,
                "timeout_seconds": provider.timeout,
                "max_tokens": provider.max_tokens,
                "failover_targets": failover_targets,
                "metadata": provider.metadata,
            }
        )

    # Build fallback rules
    fallback_rules = []
    for rule in chain.fallback_rules:
        rule_dict: dict = {
            "error_type": rule.condition_error_type.value,
            "action": rule.action.value,
            "wait_seconds": rule.wait_seconds,
            "retry_count": rule.retry_count,
        }
        if rule.condition_latency_threshold is not None:
            rule_dict["latency_threshold_ms"] = rule.condition_latency_threshold
        if rule.condition_status_codes:
            rule_dict["status_codes"] = list(rule.condition_status_codes)
        fallback_rules.append(rule_dict)

    config: dict = {
        "chain_name": chain.name,
        "providers": [p.model_dump(mode="json") for p in sorted_providers],
        "routing": routing_table,
        "fallback_rules": fallback_rules,
        "metadata": chain.metadata,
    }

    if output_path:
        import json as _json

        Path(output_path).write_text(_json.dumps(config, indent=2), encoding="utf-8")

    return config


def export_langchain(chain: Chain, output_path: str | None = None) -> dict:
    """Export a Chain to LangChain router configuration format.

    Produces a config compatible with langchain's RouterRunnable or
    with_router config. Maps providers to LangChain LLM entries with
    fallbacks specified as a chain of model names.

    Args:
        chain: The chain to export.
        output_path: Optional file path to write the output (as JSON).

    Returns:
        A dict in LangChain router config format.
    """
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    # Build LLM entries
    llm_entries = []
    for provider in sorted_providers:
        entry: dict = {
            "name": provider.name,
            "model": provider.model_id,
            "api_base": provider.api_base,
            "max_tokens": provider.max_tokens,
            "timeout": provider.timeout,
            "priority": provider.priority,
        }
        # Map metadata to LangChain-specific params
        if provider.metadata:
            if "api_key" in provider.metadata:
                entry["api_key"] = provider.metadata["api_key"]
            if "temperature" in provider.metadata:
                entry["temperature"] = provider.metadata["temperature"]
            if "provider_type" in provider.metadata:
                entry["provider_type"] = provider.metadata["provider_type"]
        llm_entries.append(entry)

    # Build fallback chain (ordered list of model names after each provider)
    fallback_map: dict[str, list[str]] = {}
    for idx, provider in enumerate(sorted_providers):
        fallback_names = [p.name for p in sorted_providers[idx + 1 :]]
        if fallback_names:
            fallback_map[provider.name] = fallback_names

    # Build error-handling rules
    error_handlers = []
    for rule in chain.fallback_rules:
        handler: dict = {
            "error_type": rule.condition_error_type.value,
            "action": rule.action.value,
        }
        if rule.action.value == "wait":
            handler["wait_seconds"] = rule.wait_seconds
            handler["retry_count"] = rule.retry_count
        elif rule.action.value == "retry":
            handler["retry_count"] = rule.retry_count
        if rule.condition_status_codes:
            handler["status_codes"] = list(rule.condition_status_codes)
        error_handlers.append(handler)

    config: dict = {
        "type": "langchain_router",
        "chain_name": chain.name,
        "llms": llm_entries,
        "fallbacks": fallback_map,
        "error_handling": error_handlers,
        "default_max_retries": 3,
    }

    if chain.metadata:
        config["metadata"] = chain.metadata

    if output_path:
        Path(output_path).write_text(json.dumps(config, indent=2), encoding="utf-8")

    return config


def export_haystack(chain: Chain, output_path: str | None = None) -> dict:
    """Export a Chain to Haystack pipeline configuration format.

    Produces a YAML/JSON-compatible config for Haystack's PromptNode
    and fallback pipeline setup. Maps providers to Haystack LLM
    generators with failover configuration.

    Args:
        chain: The chain to export.
        output_path: Optional file path to write the output (as JSON).

    Returns:
        A dict in Haystack pipeline config format.
    """
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    # Build generator entries (Haystack style)
    generators = []
    for provider in sorted_providers:
        entry: dict = {
            "name": provider.name,
            "type": "PromptNode",
            "params": {
                "model_name_or_path": provider.model_id,
                "api_base": provider.api_base,
                "max_length": provider.max_tokens,
                "model_kwargs": {
                    "timeout": provider.timeout,
                },
            },
        }
        # Map metadata to Haystack params
        if provider.metadata:
            if "api_key" in provider.metadata:
                entry["params"]["api_key"] = provider.metadata["api_key"]
            if "temperature" in provider.metadata:
                entry["params"]["model_kwargs"]["temperature"] = provider.metadata["temperature"]
            if "provider_type" in provider.metadata:
                entry["params"]["custom_llm_provider"] = provider.metadata["provider_type"]
        generators.append(entry)

    # Build fallback pipeline (join-style)
    # Haystack uses a pipeline graph where nodes are connected by edges
    edges = []
    for idx in range(len(sorted_providers) - 1):
        edges.append(
            {
                "from_": sorted_providers[idx].name,
                "to_": sorted_providers[idx + 1].name,
                "condition": "fallback",
            }
        )

    # Build error-handling rules as Haystack-style conditions
    error_conditions = []
    for rule in chain.fallback_rules:
        condition: dict = {
            "error_type": rule.condition_error_type.value,
            "action": rule.action.value,
        }
        if rule.action.value == "wait":
            condition["wait_seconds"] = rule.wait_seconds
            condition["retry_count"] = rule.retry_count
        elif rule.action.value == "retry":
            condition["retry_count"] = rule.retry_count
        if rule.condition_status_codes:
            condition["status_codes"] = list(rule.condition_status_codes)
        error_conditions.append(condition)

    config: dict = {
        "type": "haystack_pipeline",
        "chain_name": chain.name,
        "version": "1.0",
        "components": generators,
        "edges": edges,
        "error_handling": error_conditions,
    }

    if chain.metadata:
        config["metadata"] = chain.metadata

    if output_path:
        Path(output_path).write_text(json.dumps(config, indent=2), encoding="utf-8")

    return config


# Backwards-compatible wrapper
def export_chain(chain: Chain, fmt: ExportFormat) -> dict:
    """Export a chain to a supported format (backwards-compatible wrapper).

    Args:
        chain: The chain to export.
        fmt: Target export format.

    Returns:
        A dict representing the exported configuration.
    """
    if fmt == ExportFormat.LITELLM:
        result = yaml.safe_load(export_litellm(chain))
        return result if isinstance(result, dict) else {}
    if fmt == ExportFormat.OPENROUTER:
        import json as _json

        return _json.loads(export_openrouter(chain))
    if fmt == ExportFormat.CUSTOM:
        return export_custom(chain)
    if fmt == ExportFormat.LANGCHAIN:
        return export_langchain(chain)
    if fmt == ExportFormat.HAYSTACK:
        return export_haystack(chain)

    raise ValueError(f"Unsupported export format: {fmt}")

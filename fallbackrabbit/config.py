"""Configuration loader for real LLM provider calls.

Reads API keys and provider settings from environment variables.
Never hardcodes secrets — all credentials come from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Per-provider default configuration
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "timeout": 30.0,
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "timeout": 30.0,
        "default_model": "claude-sonnet-4-20250514",
    },
    "azure": {
        "base_url": "",  # Must be set via env
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "timeout": 30.0,
        "default_model": "gpt-4o",
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "api_key_env": "",  # Ollama needs no key
        "timeout": 60.0,
        "default_model": "llama3",
    },
    "custom": {
        "base_url": "",  # Must be set explicitly
        "api_key_env": "CUSTOM_LLM_API_KEY",
        "timeout": 30.0,
        "default_model": "",
    },
}


@dataclass
class ProviderConfig:
    """Resolved configuration for a single LLM provider."""

    name: str
    provider_type: str  # openai, anthropic, azure, ollama, custom
    base_url: str
    api_key: str | None
    timeout: float
    default_model: str
    extra: dict[str, Any] = field(default_factory=dict)


class ConfigError(Exception):
    """Raised when provider configuration is invalid or missing."""


def load_provider_config(
    provider_type: str,
    *,
    base_url: str | None = None,
    api_key_env: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    default_model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ProviderConfig:
    """Load and resolve configuration for a single provider.

    Resolution order for each field:
      1. Explicit argument (highest priority)
      2. Environment variable (for api_key)
      3. _PROVIDER_DEFAULTS fallback
      4. ConfigError if required and still missing

    Args:
        provider_type: One of 'openai', 'anthropic', 'azure', 'ollama', 'custom'.
        base_url: Override base URL for the provider API.
        api_key_env: Override environment variable name for the API key.
        api_key: Explicit API key (skips env var lookup).
        timeout: Override request timeout in seconds.
        default_model: Override default model identifier.
        extra: Additional provider-specific settings.

    Returns:
        A fully resolved ProviderConfig.

    Raises:
        ConfigError: If the provider_type is unknown or a required key is missing.
    """
    if provider_type not in _PROVIDER_DEFAULTS:
        raise ConfigError(
            f"Unknown provider type '{provider_type}'. Supported: {', '.join(_PROVIDER_DEFAULTS)}"
        )

    defaults = _PROVIDER_DEFAULTS[provider_type]

    # Resolve base_url
    resolved_base_url = base_url or defaults["base_url"]
    if not resolved_base_url and provider_type != "custom":
        # For custom, empty base_url is allowed (user must set it)
        raise ConfigError(
            f"base_url is required for provider type '{provider_type}'. "
            f"Set the base_url argument or the appropriate environment variable."
        )

    # Resolve API key
    resolved_key: str | None = None
    if api_key is not None:
        resolved_key = api_key
    else:
        env_var = api_key_env or defaults.get("api_key_env", "")
        if env_var:
            resolved_key = os.environ.get(env_var)

    # Resolve timeout
    resolved_timeout = timeout if timeout is not None else defaults["timeout"]

    # Resolve default_model
    resolved_model = default_model or defaults["default_model"]

    return ProviderConfig(
        name=provider_type,
        provider_type=provider_type,
        base_url=resolved_base_url,
        api_key=resolved_key,
        timeout=resolved_timeout,
        default_model=resolved_model,
        extra=extra or {},
    )


def validate_config(config: ProviderConfig) -> None:
    """Validate a provider configuration before making API calls.

    Args:
        config: The provider configuration to validate.

    Raises:
        ConfigError: If the configuration is invalid.
    """
    if not config.base_url:
        raise ConfigError(f"Provider '{config.name}' requires a base_url")

    # Providers that require an API key
    key_required = config.provider_type in ("openai", "anthropic", "azure")
    if key_required and not config.api_key:
        defaults = _PROVIDER_DEFAULTS.get(config.provider_type, {})
        env_var = defaults.get("api_key_env", "")
        raise ConfigError(
            f"Provider '{config.name}' requires an API key. "
            f"Set the {env_var} environment variable or pass api_key explicitly."
        )

    if config.timeout <= 0:
        raise ConfigError(
            f"Provider '{config.name}' timeout must be positive, got {config.timeout}"
        )


def config_from_provider_model(
    provider_name: str,
    model_id: str,
    api_base: str,
    timeout: float = 30.0,
    metadata: dict[str, Any] | None = None,
) -> ProviderConfig:
    """Create a ProviderConfig from Chain Provider model fields.

    Inspects the api_base and model_id to infer provider_type, then
    delegates to load_provider_config for full resolution.

    Args:
        provider_name: Human-readable name from the Chain.
        model_id: Model identifier (e.g. 'gpt-4o', 'claude-sonnet-4-20250514').
        api_base: Base URL for the provider API.
        timeout: Request timeout in seconds.
        metadata: Extra provider-specific settings.

    Returns:
        A resolved ProviderConfig.
    """
    metadata = metadata or {}

    # Infer provider type from api_base and model_id
    provider_type = metadata.get("provider_type", _infer_provider_type(api_base, model_id))

    # Extract any overrides from metadata
    api_key_env = metadata.get("api_key_env")
    api_key = metadata.get("api_key")
    default_model = model_id

    config = load_provider_config(
        provider_type,
        base_url=api_base,
        api_key_env=api_key_env,
        api_key=api_key,
        timeout=timeout,
        default_model=default_model,
        extra=metadata,
    )
    # Override name with the chain provider name
    config.name = provider_name
    return config


def _infer_provider_type(api_base: str, model_id: str) -> str:
    """Infer the provider type from the base URL and model identifier.

    Args:
        api_base: The API base URL.
        model_id: The model identifier string.

    Returns:
        One of 'openai', 'anthropic', 'azure', 'ollama', or 'custom'.
    """
    api_lower = api_base.lower()
    model_lower = model_id.lower()

    if "anthropic" in api_lower or model_lower.startswith("claude"):
        return "anthropic"
    if "azure" in api_lower:
        return "azure"
    if "ollama" in api_lower or "localhost:11434" in api_lower:
        return "ollama"
    if "openai" in api_lower or model_lower.startswith("gpt-"):
        return "openai"
    # Default to openai-compatible for unknown endpoints
    return "custom"

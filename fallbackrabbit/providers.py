"""Real LLM provider HTTP clients.

Provides AsyncProviderClient for making actual API calls to LLM providers
(OpenAI, Anthropic, Azure OpenAI, Ollama, and any OpenAI-compatible endpoint).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import ConfigError, ProviderConfig, config_from_provider_model, validate_config
from .models import ErrorType, Provider

# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


@dataclass
class ProviderResponse:
    """Result of a real LLM provider call."""

    success: bool
    content: str = ""
    latency_ms: float = 0.0
    token_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    error_type: ErrorType | None = None
    status_code: int | None = None
    model: str = ""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def classify_error(status_code: int | None, error_message: str) -> ErrorType:
    """Classify an error into a standard ErrorType.

    Args:
        status_code: HTTP status code, if available.
        error_message: The error message string.

    Returns:
        The classified ErrorType.
    """
    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if status_code in (401, 403):
        return ErrorType.CONNECTION_ERROR  # Auth failure treated as connection error
    if status_code is not None and status_code >= 500:
        return ErrorType.SERVER_ERROR

    msg_lower = error_message.lower()
    if "timeout" in msg_lower or "timed out" in msg_lower:
        return ErrorType.TIMEOUT
    if "rate" in msg_lower and "limit" in msg_lower:
        return ErrorType.RATE_LIMIT
    if "connection" in msg_lower or "connect" in msg_lower or "network" in msg_lower:
        return ErrorType.CONNECTION_ERROR
    if "auth" in msg_lower or "unauthorized" in msg_lower or "forbidden" in msg_lower:
        return ErrorType.CONNECTION_ERROR

    # Default to server_error for unrecognized errors with status codes
    if status_code is not None:
        return ErrorType.SERVER_ERROR

    return ErrorType.CONNECTION_ERROR


# ---------------------------------------------------------------------------
# AsyncProviderClient
# ---------------------------------------------------------------------------


class AsyncProviderClient:
    """Async HTTP client for calling real LLM provider APIs.

    Supports OpenAI-compatible endpoints (including Azure, Ollama, vLLM)
    and the Anthropic Messages API.

    Usage:
        client = AsyncProviderClient()
        config = load_provider_config("openai")
        response = await client.call(config, "Hello, world!")
        print(response.content, response.latency_ms)
    """

    def __init__(self, timeout: float | None = None) -> None:
        """Initialize the async provider client.

        Args:
            timeout: Default timeout in seconds for all requests.
                Can be overridden per-call via ProviderConfig.timeout.
        """
        self._default_timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the underlying httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._default_timeout or 60.0)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncProviderClient:
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def call(
        self,
        config: ProviderConfig,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> ProviderResponse:
        """Send a prompt to a provider and return the response.

        Routes to the appropriate API format based on config.provider_type.

        Args:
            config: Resolved provider configuration.
            prompt: The user prompt text.
            model: Override model identifier (defaults to config.default_model).
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0.0-2.0).
            system: Optional system prompt.

        Returns:
            A ProviderResponse with content, latency, tokens, and error info.
        """
        model = model or config.default_model

        start = time.monotonic()
        try:
            validate_config(config)
        except ConfigError as exc:
            return ProviderResponse(
                success=False,
                error=str(exc),
                error_type=ErrorType.CONNECTION_ERROR,
            )

        try:
            if config.provider_type == "anthropic":
                result = await self._call_anthropic(
                    config,
                    prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                )
            else:
                # OpenAI-compatible covers: openai, azure, ollama, custom
                result = await self._call_openai_compatible(
                    config,
                    prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                )
            result.latency_ms = (time.monotonic() - start) * 1000
            return result

        except httpx.TimeoutException as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderResponse(
                success=False,
                latency_ms=elapsed,
                error=str(exc),
                error_type=ErrorType.TIMEOUT,
            )
        except httpx.ConnectError as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderResponse(
                success=False,
                latency_ms=elapsed,
                error=str(exc),
                error_type=ErrorType.CONNECTION_ERROR,
            )
        except ConfigError as exc:
            return ProviderResponse(
                success=False,
                error=str(exc),
                error_type=ErrorType.CONNECTION_ERROR,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderResponse(
                success=False,
                latency_ms=elapsed,
                error=str(exc),
                error_type=classify_error(None, str(exc)),
            )

    async def _call_openai_compatible(
        self,
        config: ProviderConfig,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> ProviderResponse:
        """Call an OpenAI-compatible chat completions endpoint.

        Works with OpenAI, Azure OpenAI, Ollama, vLLM, and any
        endpoint that implements the /v1/chat/completions interface.
        """
        client = await self._get_client()

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        url = f"{config.base_url.rstrip('/')}/v1/chat/completions"

        # Handle different auth schemes
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        # Azure uses api-key header
        if config.provider_type == "azure" and config.api_key:
            headers.pop("Authorization", None)
            headers["api-key"] = config.api_key

        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=config.timeout,
            )
        except httpx.TimeoutException:
            raise
        except httpx.ConnectError:
            raise

        if response.status_code != 200:
            error_body = response.text[:500]
            error_type = classify_error(response.status_code, error_body)
            return ProviderResponse(
                success=False,
                error=f"HTTP {response.status_code}: {error_body}",
                error_type=error_type,
                status_code=response.status_code,
            )

        data = response.json()
        content = ""
        token_count = 0
        prompt_tokens = 0
        completion_tokens = 0
        resp_model = model

        # Extract content from choices
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            resp_model = data.get("model", model)

        # Extract token usage
        usage = data.get("usage", {})
        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            token_count = prompt_tokens + completion_tokens

        return ProviderResponse(
            success=True,
            content=content,
            token_count=token_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=resp_model,
        )

    async def _call_anthropic(
        self,
        config: ProviderConfig,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> ProviderResponse:
        """Call the Anthropic Messages API."""
        client = await self._get_client()

        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        url = f"{config.base_url.rstrip('/')}/v1/messages"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if config.api_key:
            headers["x-api-key"] = config.api_key

        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=config.timeout,
            )
        except httpx.TimeoutException:
            raise
        except httpx.ConnectError:
            raise

        if response.status_code != 200:
            error_body = response.text[:500]
            error_type = classify_error(response.status_code, error_body)
            return ProviderResponse(
                success=False,
                error=f"HTTP {response.status_code}: {error_body}",
                error_type=error_type,
                status_code=response.status_code,
            )

        data = response.json()
        content = ""
        token_count = 0
        prompt_tokens = 0
        completion_tokens = 0
        resp_model = model

        # Extract content from Anthropic response
        content_blocks = data.get("content", [])
        if content_blocks:
            # Concatenate all text blocks
            parts = [
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            ]
            content = "".join(parts)
            resp_model = data.get("model", model)

        # Extract token usage
        usage = data.get("usage", {})
        if usage:
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
            token_count = prompt_tokens + completion_tokens

        return ProviderResponse(
            success=True,
            content=content,
            token_count=token_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=resp_model,
        )

    async def call_provider(
        self,
        provider: Provider,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> ProviderResponse:
        """Convenience method: call a Provider model object directly.

        Converts a Chain Provider to a ProviderConfig and calls it.

        Args:
            provider: A Provider model from a Chain.
            prompt: The user prompt text.
            system: Optional system prompt.
            temperature: Sampling temperature.

        Returns:
            A ProviderResponse.
        """
        config = config_from_provider_model(
            provider_name=provider.name,
            model_id=provider.model_id,
            api_base=provider.api_base,
            timeout=provider.timeout,
            metadata=provider.metadata,
        )
        return await self.call(
            config,
            prompt,
            max_tokens=provider.max_tokens,
            temperature=temperature,
            system=system,
        )

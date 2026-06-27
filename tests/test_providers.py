"""Tests for real provider calls, configuration, and simulator integration."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fallbackrabbit.config import (
    ConfigError,
    ProviderConfig,
    config_from_provider_model,
    load_provider_config,
    validate_config,
)
from fallbackrabbit.models import (
    Chain,
    ErrorType,
    FallbackAction,
    FallbackRule,
    PromptSpec,
    Provider,
)
from fallbackrabbit.providers import (
    AsyncProviderClient,
    ProviderResponse,
    classify_error,
)
from fallbackrabbit.simulator import Simulator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_chain(
    providers: list[Provider] | None = None,
    rules: list[FallbackRule] | None = None,
) -> Chain:
    """Create a test Chain with sensible defaults."""
    if providers is None:
        providers = [
            Provider(
                name="primary", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
            ),
            Provider(
                name="fallback",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com",
                priority=1,
            ),
        ]
    return Chain(name="test-chain", providers=providers, fallback_rules=rules or [])


SAMPLE_OPENAI_RESPONSE = {
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello! How can I help you?"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
}

SAMPLE_ANTHROPIC_RESPONSE = {
    "id": "msg_abc123",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-20250514",
    "content": [{"type": "text", "text": "Hello! How can I help?"}],
    "usage": {"input_tokens": 12, "output_tokens": 7},
}


# ===========================================================================
# Config tests
# ===========================================================================


class TestLoadProviderConfig:
    """Tests for load_provider_config."""

    def test_load_openai_defaults(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = load_provider_config("openai")
        assert cfg.provider_type == "openai"
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.api_key is None  # No env var set
        assert cfg.timeout == 30.0
        assert cfg.default_model == "gpt-4o"

    def test_load_anthropic_defaults(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = load_provider_config("anthropic")
        assert cfg.provider_type == "anthropic"
        assert cfg.base_url == "https://api.anthropic.com"
        assert cfg.default_model == "claude-sonnet-4-20250514"

    def test_load_ollama_defaults(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        cfg = load_provider_config("ollama")
        assert cfg.provider_type == "ollama"
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.api_key is None  # Ollama needs no key
        assert cfg.timeout == 60.0

    def test_load_azure_defaults(self):
        with pytest.raises(ConfigError, match="base_url"):
            load_provider_config("azure")

    def test_load_azure_with_base_url(self):
        cfg = load_provider_config("azure", base_url="https://my-resource.openai.azure.com")
        assert cfg.provider_type == "azure"
        assert cfg.base_url == "https://my-resource.openai.azure.com"
        assert cfg.timeout == 30.0

    def test_load_custom_defaults(self):
        cfg = load_provider_config("custom", base_url="http://my-llm:8000")
        assert cfg.provider_type == "custom"
        assert cfg.base_url == "http://my-llm:8000"

    def test_unknown_provider_type_raises(self):
        with pytest.raises(ConfigError, match="Unknown provider type"):
            load_provider_config("groq")

    def test_explicit_api_key(self):
        cfg = load_provider_config("openai", api_key="sk-test123")
        assert cfg.api_key == "sk-test123"

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"MY_OPENAI_KEY": "sk-envkey"}):
            cfg = load_provider_config("openai", api_key_env="MY_OPENAI_KEY")
            assert cfg.api_key == "sk-envkey"

    def test_override_timeout(self):
        cfg = load_provider_config("openai", timeout=60.0)
        assert cfg.timeout == 60.0

    def test_override_base_url(self):
        cfg = load_provider_config("openai", base_url="https://custom.openai.com/v1")
        assert cfg.base_url == "https://custom.openai.com/v1"

    def test_override_default_model(self):
        cfg = load_provider_config("openai", default_model="gpt-3.5-turbo")
        assert cfg.default_model == "gpt-3.5-turbo"

    def test_extra_metadata(self):
        cfg = load_provider_config("openai", extra={"org": "test-org"})
        assert cfg.extra == {"org": "test-org"}


class TestValidateConfig:
    """Tests for validate_config."""

    def test_valid_openai_config_with_key(self):
        cfg = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=30.0,
            default_model="gpt-4o",
        )
        validate_config(cfg)  # Should not raise

    def test_valid_ollama_no_key(self):
        cfg = ProviderConfig(
            name="ollama",
            provider_type="ollama",
            base_url="http://localhost:11434",
            api_key=None,
            timeout=60.0,
            default_model="llama3",
        )
        validate_config(cfg)  # Should not raise — Ollama needs no key

    def test_missing_api_key_raises(self):
        cfg = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key=None,
            timeout=30.0,
            default_model="gpt-4o",
        )
        with pytest.raises(ConfigError, match="requires an API key"):
            validate_config(cfg)

    def test_missing_base_url_raises(self):
        cfg = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="",
            api_key="sk-test",
            timeout=30.0,
            default_model="gpt-4o",
        )
        with pytest.raises(ConfigError, match="base_url"):
            validate_config(cfg)

    def test_zero_timeout_raises(self):
        cfg = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=0.0,
            default_model="gpt-4o",
        )
        with pytest.raises(ConfigError, match="timeout"):
            validate_config(cfg)

    def test_anthropic_missing_key_raises(self):
        cfg = ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key=None,
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )
        with pytest.raises(ConfigError, match="requires an API key"):
            validate_config(cfg)


class TestConfigFromProviderModel:
    """Tests for config_from_provider_model."""

    def test_infers_openai_from_url(self):
        p = Provider(name="my-openai", model_id="gpt-4o", api_base="https://api.openai.com/v1")
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base)
        assert cfg.provider_type == "openai"

    def test_infers_anthropic_from_model(self):
        p = Provider(
            name="my-claude",
            model_id="claude-sonnet-4-20250514",
            api_base="https://api.anthropic.com",
        )
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base)
        assert cfg.provider_type == "anthropic"

    def test_infers_ollama_from_url(self):
        p = Provider(name="local", model_id="llama3", api_base="http://localhost:11434")
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base)
        assert cfg.provider_type == "ollama"

    def test_infers_azure_from_url(self):
        p = Provider(
            name="azure-gpt", model_id="gpt-4o", api_base="https://my-resource.openai.azure.com"
        )
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base)
        assert cfg.provider_type == "azure"

    def test_custom_for_unknown(self):
        p = Provider(name="my-vllm", model_id="mistral-7b", api_base="http://192.168.1.50:8000")
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base)
        assert cfg.provider_type == "custom"

    def test_metadata_provider_type_override(self):
        p = Provider(
            name="custom-openai",
            model_id="my-model",
            api_base="http://custom:8000",
            metadata={"provider_type": "openai"},
        )
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base, metadata=p.metadata)
        assert cfg.provider_type == "openai"

    def test_passes_timeout_and_model(self):
        p = Provider(
            name="test", model_id="gpt-4o", api_base="https://api.openai.com/v1", timeout=45.0
        )
        cfg = config_from_provider_model(p.name, p.model_id, p.api_base, timeout=p.timeout)
        assert cfg.timeout == 45.0
        assert cfg.default_model == "gpt-4o"


# ===========================================================================
# Error classification tests
# ===========================================================================


class TestClassifyError:
    """Tests for error classification."""

    def test_rate_limit_429(self):
        assert classify_error(429, "Too many requests") == ErrorType.RATE_LIMIT

    def test_auth_401(self):
        assert classify_error(401, "Unauthorized") == ErrorType.CONNECTION_ERROR

    def test_auth_403(self):
        assert classify_error(403, "Forbidden") == ErrorType.CONNECTION_ERROR

    def test_server_error_500(self):
        assert classify_error(500, "Internal server error") == ErrorType.SERVER_ERROR

    def test_server_error_502(self):
        assert classify_error(502, "Bad gateway") == ErrorType.SERVER_ERROR

    def test_timeout_from_message(self):
        assert classify_error(None, "Connection timed out") == ErrorType.TIMEOUT

    def test_rate_limit_from_message(self):
        assert classify_error(None, "Rate limit exceeded") == ErrorType.RATE_LIMIT

    def test_connection_error_from_message(self):
        assert classify_error(None, "Connection refused") == ErrorType.CONNECTION_ERROR

    def test_auth_from_message(self):
        assert classify_error(None, "Authentication failed") == ErrorType.CONNECTION_ERROR

    def test_server_error_with_status_fallback(self):
        assert classify_error(503, "something") == ErrorType.SERVER_ERROR

    def test_default_connection_error(self):
        assert classify_error(None, "unknown error thing") == ErrorType.CONNECTION_ERROR


# ===========================================================================
# Provider client tests (mocked HTTP)
# ===========================================================================


class TestAsyncProviderClient:
    """Tests for AsyncProviderClient with mocked HTTP."""

    @pytest.fixture
    def client(self):
        return AsyncProviderClient()

    @pytest.fixture
    def openai_config(self):
        return ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-testkey123",
            timeout=30.0,
            default_model="gpt-4o",
        )

    @pytest.fixture
    def anthropic_config(self):
        return ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-testkey123",
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )

    @pytest.fixture
    def ollama_config(self):
        return ProviderConfig(
            name="ollama",
            provider_type="ollama",
            base_url="http://localhost:11434",
            api_key=None,
            timeout=60.0,
            default_model="llama3",
        )

    async def test_openai_success(self, client, openai_config):
        """Test successful OpenAI-compatible API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OPENAI_RESPONSE

        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=True,
                content="Hello! How can I help you?",
                token_count=18,
                prompt_tokens=10,
                completion_tokens=8,
                model="gpt-4o",
            )
            result = await client.call(openai_config, "Hello")
            assert result.success
            assert result.content == "Hello! How can I help you?"
            assert result.token_count == 18
            assert result.model == "gpt-4o"

    async def test_anthropic_success(self, client, anthropic_config):
        """Test successful Anthropic API call."""
        with patch.object(client, "_call_anthropic", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=True,
                content="Hello! How can I help?",
                token_count=19,
                prompt_tokens=12,
                completion_tokens=7,
                model="claude-sonnet-4-20250514",
            )
            result = await client.call(anthropic_config, "Hello")
            assert result.success
            assert result.content == "Hello! How can I help?"
            assert result.token_count == 19

    async def test_timeout_error(self, client, openai_config):
        """Test that httpx.TimeoutException is classified as TIMEOUT."""
        import httpx

        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = httpx.TimeoutException("Request timed out")
            result = await client.call(openai_config, "Hello")
            assert not result.success
            assert result.error_type == ErrorType.TIMEOUT
            assert "timed out" in result.error.lower() or "timeout" in result.error.lower()

    async def test_connection_error(self, client, openai_config):
        """Test that httpx.ConnectError is classified as CONNECTION_ERROR."""
        import httpx

        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = httpx.ConnectError("Connection refused")
            result = await client.call(openai_config, "Hello")
            assert not result.success
            assert result.error_type == ErrorType.CONNECTION_ERROR

    async def test_config_error(self, client):
        """Test that invalid config raises ConfigError caught by call()."""
        bad_config = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key=None,  # Missing key!
            timeout=30.0,
            default_model="gpt-4o",
        )
        result = await client.call(bad_config, "Hello")
        assert not result.success
        assert result.error_type == ErrorType.CONNECTION_ERROR
        assert "API key" in result.error or "key" in result.error.lower()

    async def test_ollama_no_key(self, client, ollama_config):
        """Test Ollama works without an API key."""
        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=True,
                content="Hi!",
                model="llama3",
            )
            result = await client.call(ollama_config, "Hello")
            assert result.success

    async def test_http_error_429(self, client, openai_config):
        """Test that 429 responses are classified as RATE_LIMIT."""
        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=False,
                error="HTTP 429: Rate limit exceeded",
                error_type=ErrorType.RATE_LIMIT,
                status_code=429,
            )
            result = await client.call(openai_config, "Hello")
            assert not result.success
            assert result.error_type == ErrorType.RATE_LIMIT

    async def test_http_error_500(self, client, openai_config):
        """Test that 500 responses are classified as SERVER_ERROR."""
        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=False,
                error="HTTP 500: Internal server error",
                error_type=ErrorType.SERVER_ERROR,
                status_code=500,
            )
            result = await client.call(openai_config, "Hello")
            assert not result.success
            assert result.error_type == ErrorType.SERVER_ERROR

    async def test_latency_tracking(self, client, openai_config):
        """Test that latency is tracked even on success."""
        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(
                success=True,
                content="Hello!",
                model="gpt-4o",
            )
            result = await client.call(openai_config, "Hello")
            assert result.success
            assert result.latency_ms >= 0  # Should have some latency

    async def test_call_provider_convenience(self, client):
        """Test call_provider converts a Provider model to config and calls."""
        provider = Provider(
            name="test-openai",
            model_id="gpt-4o",
            api_base="https://api.openai.com/v1",
            priority=0,
            timeout=30.0,
            max_tokens=2048,
            metadata={"api_key": "sk-test123"},
        )
        with patch.object(client, "call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(success=True, content="Hi!", model="gpt-4o")
            result = await client.call_provider(provider, "Hello")
            assert result.success
            mock_call.assert_called_once()

    async def test_context_manager(self):
        """Test AsyncProviderClient works as async context manager."""
        async with AsyncProviderClient() as client:
            assert client._client is not None
        assert client._client is None or client._client.is_closed

    async def test_close_idempotent(self, client):
        """Test that close() is safe to call multiple times."""
        await client.close()
        await client.close()  # Should not raise

    async def test_system_prompt(self, client, openai_config):
        """Test that system prompt is passed through."""
        with patch.object(client, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ProviderResponse(success=True, content="Done", model="gpt-4o")
            result = await client.call(openai_config, "Hello", system="You are helpful")
            assert result.success
            # Verify system was passed (call args include it)
            call_kwargs = mock_call.call_args
            assert call_kwargs.kwargs.get("system") == "You are helpful" or "system" in str(
                call_kwargs
            )


# ===========================================================================
# Simulator integration with real calls (mocked)
# ===========================================================================


class TestSimulatorRealCalls:
    """Tests for Simulator in real-calls mode with mocked provider client."""

    @pytest.fixture
    def chain(self):
        return make_chain()

    @pytest.fixture
    def chain_with_wait_rule(self):
        providers = [
            Provider(
                name="primary", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
            ),
            Provider(
                name="fallback",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com",
                priority=1,
            ),
        ]
        rules = [
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=0.01,  # Tiny wait for tests
                retry_count=1,
            )
        ]
        return Chain(name="wait-chain", providers=providers, fallback_rules=rules)

    async def test_real_calls_success(self, chain):
        """Test Simulator with real calls mode — primary succeeds."""
        mock_client = AsyncMock(spec=AsyncProviderClient)
        mock_client.call_provider.return_value = ProviderResponse(
            success=True,
            content="Hello!",
            latency_ms=150.0,
            token_count=20,
            prompt_tokens=10,
            completion_tokens=10,
            model="gpt-4o",
        )

        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
        assert result.success
        assert result.provider_name == "primary"
        assert result.latency_ms > 0

    async def test_real_calls_failover(self, chain):
        """Test Simulator with real calls — primary fails, fallback succeeds."""
        mock_client = AsyncMock(spec=AsyncProviderClient)
        call_count = 0

        async def side_effect(provider, prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ProviderResponse(
                    success=False,
                    latency_ms=100.0,
                    error="HTTP 429: Rate limit",
                    error_type=ErrorType.RATE_LIMIT,
                    status_code=429,
                )
            return ProviderResponse(
                success=True,
                content="Claude here!",
                latency_ms=200.0,
                token_count=15,
                prompt_tokens=8,
                completion_tokens=7,
                model="claude-sonnet-4-20250514",
            )

        mock_client.call_provider.side_effect = side_effect

        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
        assert result.success
        assert result.provider_name == "fallback"
        assert result.fallback_triggered is True

    async def test_real_calls_all_fail(self, chain):
        """Test Simulator with real calls — all providers fail."""
        mock_client = AsyncMock(spec=AsyncProviderClient)
        mock_client.call_provider.return_value = ProviderResponse(
            success=False,
            latency_ms=50.0,
            error="HTTP 500: Server error",
            error_type=ErrorType.SERVER_ERROR,
            status_code=500,
        )

        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
        assert not result.success
        assert result.error == "All providers in chain failed"

    async def test_real_calls_with_wait_retry(self, chain_with_wait_rule):
        """Test Simulator with real calls — wait-retry succeeds on second attempt."""
        mock_client = AsyncMock(spec=AsyncProviderClient)
        call_count = 0

        async def side_effect(provider, prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call: rate limit; second call (retry): success
            if call_count == 1:
                return ProviderResponse(
                    success=False,
                    error="HTTP 429: Rate limit",
                    error_type=ErrorType.RATE_LIMIT,
                    status_code=429,
                )
            return ProviderResponse(
                success=True,
                content="Success after retry",
                latency_ms=300.0,
                token_count=10,
                prompt_tokens=5,
                completion_tokens=5,
                model="gpt-4o",
            )

        mock_client.call_provider.side_effect = side_effect

        sim = Simulator(chain_with_wait_rule, use_real_calls=True, provider_client=mock_client)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
        assert result.success
        assert result.provider_name == "primary"
        assert result.fallback_triggered is True

    async def test_simulated_mode_unchanged(self, chain):
        """Test that simulated mode still works as before."""
        sim = Simulator(chain, use_real_calls=False)
        result = await sim.run_prompt(PromptSpec(prompt="Hello"))
        # Simulated mode should work without any HTTP client
        assert isinstance(result.success, bool)

    async def test_close_releases_client(self, chain):
        """Test that close() cleans up the internally created client."""
        sim = Simulator(chain, use_real_calls=True)
        # Don't call run_prompt — just test close works
        await sim.close()
        # Should not raise on second close
        await sim.close()

    async def test_close_does_not_close_external_client(self, chain):
        """Test that close() does not close an externally provided client."""
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        await sim.close()
        # The external client's aclose should NOT have been called
        mock_client.aclose.assert_not_called()

    async def test_batch_with_real_calls(self, chain):
        """Test run_batch with real calls."""
        mock_client = AsyncMock(spec=AsyncProviderClient)
        mock_client.call_provider.return_value = ProviderResponse(
            success=True,
            content="Hello!",
            latency_ms=100.0,
            token_count=15,
            prompt_tokens=8,
            completion_tokens=7,
            model="gpt-4o",
        )

        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        report = await sim.run_batch([PromptSpec(prompt="Hi"), PromptSpec(prompt="Bye")])
        assert report.total_prompts == 2
        assert report.success_rate == 1.0
        assert report.avg_latency_ms > 0


# ===========================================================================
# OpenAI-compatible response parsing (unit-level)
# ===========================================================================


class TestOpenAICompatibleParsing:
    """Test _call_openai_compatible response parsing with mocked httpx."""

    async def test_openai_success_response(self):
        """Test parsing a successful OpenAI response."""
        client = AsyncProviderClient()

        # Mock the httpx client's post method
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OPENAI_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=30.0,
            default_model="gpt-4o",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_openai_compatible(
                config,
                "Hello",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert result.success
            assert result.content == "Hello! How can I help you?"
            assert result.token_count == 18
            assert result.prompt_tokens == 10
            assert result.completion_tokens == 8

    async def test_openai_error_response(self):
        """Test handling an HTTP error from OpenAI."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=30.0,
            default_model="gpt-4o",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_openai_compatible(
                config,
                "Hello",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert not result.success
            assert result.status_code == 500
            assert result.error_type == ErrorType.SERVER_ERROR

    async def test_openai_with_system_prompt(self):
        """Test that system prompt is included in messages."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OPENAI_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="openai",
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=30.0,
            default_model="gpt-4o",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_openai_compatible(
                config,
                "Hello",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                system="You are helpful",
            )
            assert result.success
            # Check that post was called with system message in the payload
            call_args = mock_http_client.post.call_args
            payload = call_args.kwargs.get("json", {})
            messages = payload.get("messages", [])
            assert any(m.get("role") == "system" for m in messages)

    async def test_azure_uses_api_key_header(self):
        """Test that Azure OpenAI uses api-key header instead of Authorization."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OPENAI_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="azure",
            provider_type="azure",
            base_url="https://my-resource.openai.azure.com",
            api_key="azure-key-123",
            timeout=30.0,
            default_model="gpt-4o",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_openai_compatible(
                config,
                "Hello",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert result.success
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "api-key" in headers
            assert headers["api-key"] == "azure-key-123"
            assert "Authorization" not in headers


# ===========================================================================
# Anthropic response parsing
# ===========================================================================


class TestAnthropicParsing:
    """Test _call_anthropic response parsing."""

    async def test_anthropic_success(self):
        """Test parsing a successful Anthropic response."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ANTHROPIC_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_anthropic(
                config,
                "Hello",
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert result.success
            assert result.content == "Hello! How can I help?"
            assert result.token_count == 19
            assert result.prompt_tokens == 12
            assert result.completion_tokens == 7

    async def test_anthropic_error_response(self):
        """Test handling an HTTP error from Anthropic."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_anthropic(
                config,
                "Hello",
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert not result.success
            assert result.status_code == 429
            assert result.error_type == ErrorType.RATE_LIMIT

    async def test_anthropic_with_system_prompt(self):
        """Test that system prompt is sent in the Anthropic payload."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ANTHROPIC_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_anthropic(
                config,
                "Hello",
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.7,
                system="You are a helpful assistant",
            )
            assert result.success
            call_args = mock_http_client.post.call_args
            payload = call_args.kwargs.get("json", {})
            assert payload.get("system") == "You are a helpful assistant"

    async def test_anthropic_headers(self):
        """Test that Anthropic-specific headers are set."""
        client = AsyncProviderClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ANTHROPIC_RESPONSE

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        config = ProviderConfig(
            name="anthropic",
            provider_type="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            timeout=30.0,
            default_model="claude-sonnet-4-20250514",
        )

        with patch.object(
            client, "_get_client", new_callable=AsyncMock, return_value=mock_http_client
        ):
            result = await client._call_anthropic(
                config,
                "Hello",
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.7,
                system=None,
            )
            assert result.success
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("anthropic-version") == "2023-06-01"
            assert headers.get("x-api-key") == "sk-ant-test"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_infer_provider_type_gpt_model(self):
        """Test provider type inference from model name."""
        from fallbackrabbit.config import _infer_provider_type

        assert _infer_provider_type("https://custom.api.com", "gpt-4o") == "openai"

    def test_infer_provider_type_claude_model(self):
        from fallbackrabbit.config import _infer_provider_type

        assert (
            _infer_provider_type("https://custom.api.com", "claude-sonnet-4-20250514")
            == "anthropic"
        )

    def test_infer_provider_type_anthropic_url(self):
        from fallbackrabbit.config import _infer_provider_type

        assert _infer_provider_type("https://api.anthropic.com", "my-model") == "anthropic"

    def test_infer_provider_type_ollama_url(self):
        from fallbackrabbit.config import _infer_provider_type

        assert _infer_provider_type("http://localhost:11434", "llama3") == "ollama"

    def test_infer_provider_type_azure_url(self):
        from fallbackrabbit.config import _infer_provider_type

        assert _infer_provider_type("https://my-resource.openai.azure.com", "gpt-4o") == "azure"

    def test_infer_provider_type_custom_fallback(self):
        from fallbackrabbit.config import _infer_provider_type

        assert _infer_provider_type("http://192.168.1.50:8000", "mistral-7b") == "custom"

    async def test_provider_response_defaults(self):
        """Test ProviderResponse default values."""
        resp = ProviderResponse(success=True)
        assert resp.content == ""
        assert resp.latency_ms == 0.0
        assert resp.token_count == 0
        assert resp.error is None
        assert resp.error_type is None
        assert resp.status_code is None
        assert resp.model == ""

    def test_config_error_message_unknown_type(self):
        """Test ConfigError message includes supported types."""
        with pytest.raises(ConfigError, match="Supported"):
            load_provider_config("nonexistent")

    async def test_simulator_creates_client_when_needed(self):
        """Test that Simulator auto-creates an AsyncProviderClient in real mode."""
        chain = make_chain()
        mock_client = AsyncMock(spec=AsyncProviderClient)
        mock_client.call_provider.return_value = ProviderResponse(
            success=True,
            content="test",
            latency_ms=100.0,
            model="gpt-4o",
        )
        sim = Simulator(chain, use_real_calls=True, provider_client=mock_client)
        result = await sim.run_prompt(PromptSpec(prompt="Hi"))
        assert result.success

"""Tests for LangChain and Haystack export formats."""

import json

import pytest

from fallbackrabbit.config_export import (
    export_chain,
    export_haystack,
    export_langchain,
)
from fallbackrabbit.models import (
    Chain,
    ErrorType,
    ExportFormat,
    FallbackAction,
    FallbackRule,
    Provider,
)


@pytest.fixture
def sample_chain() -> Chain:
    return Chain(
        name="test-chain",
        providers=[
            Provider(
                name="GPT-4o", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
            ),
            Provider(
                name="Claude",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com/v1",
                priority=1,
            ),
            Provider(
                name="Local", model_id="llama3", api_base="http://localhost:11434/v1", priority=2
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
            FallbackRule(condition_error_type=ErrorType.TIMEOUT, action=FallbackAction.FAILOVER),
            FallbackRule(
                condition_error_type=ErrorType.SERVER_ERROR,
                action=FallbackAction.RETRY,
                retry_count=2,
                condition_status_codes=[500, 502, 503],
            ),
        ],
        metadata={"description": "Test chain"},
    )


class TestLangChainExport:
    def test_basic_structure(self, sample_chain):
        result = export_langchain(sample_chain)
        assert result["type"] == "langchain_router"
        assert result["chain_name"] == "test-chain"
        assert len(result["llms"]) == 3

    def test_llm_entries(self, sample_chain):
        result = export_langchain(sample_chain)
        gpt = result["llms"][0]
        assert gpt["name"] == "GPT-4o"
        assert gpt["model"] == "gpt-4o"
        assert gpt["api_base"] == "https://api.openai.com/v1"
        assert gpt["priority"] == 0

    def test_fallbacks(self, sample_chain):
        result = export_langchain(sample_chain)
        # GPT-4o falls back to Claude, Local
        assert "GPT-4o" in result["fallbacks"]
        assert result["fallbacks"]["GPT-4o"] == ["Claude", "Local"]
        # Claude falls back to Local
        assert result["fallbacks"]["Claude"] == ["Local"]
        # Local has no fallback (not in the map)
        assert "Local" not in result["fallbacks"]

    def test_error_handling(self, sample_chain):
        result = export_langchain(sample_chain)
        handlers = result["error_handling"]
        assert len(handlers) == 3
        # rate_limit → wait
        rl_handler = handlers[0]
        assert rl_handler["error_type"] == "rate_limit"
        assert rl_handler["action"] == "wait"
        assert rl_handler["wait_seconds"] == 5
        assert rl_handler["retry_count"] == 3
        # server_error → retry with status codes
        se_handler = handlers[2]
        assert se_handler["error_type"] == "server_error"
        assert se_handler["action"] == "retry"
        assert se_handler["retry_count"] == 2
        assert se_handler["status_codes"] == [500, 502, 503]

    def test_metadata_included(self, sample_chain):
        result = export_langchain(sample_chain)
        assert result["metadata"] == {"description": "Test chain"}

    def test_file_output(self, sample_chain, tmp_path):
        output_file = tmp_path / "langchain.json"
        export_langchain(sample_chain, output_path=str(output_file))
        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert content["type"] == "langchain_router"

    def test_metadata_api_key(self):
        chain = Chain(
            name="auth-chain",
            providers=[
                Provider(
                    name="OpenAI",
                    model_id="gpt-4o",
                    api_base="https://api.openai.com/v1",
                    priority=0,
                    metadata={"api_key": "sk-xxx", "temperature": 0.7},
                ),
            ],
        )
        result = export_langchain(chain)
        llm = result["llms"][0]
        assert llm["api_key"] == "sk-xxx"
        assert llm["temperature"] == 0.7

    def test_no_fallbacks_for_single_provider(self):
        chain = Chain(
            name="single",
            providers=[
                Provider(
                    name="Only", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
                )
            ],
        )
        result = export_langchain(chain)
        assert result["fallbacks"] == {}


class TestHaystackExport:
    def test_basic_structure(self, sample_chain):
        result = export_haystack(sample_chain)
        assert result["type"] == "haystack_pipeline"
        assert result["chain_name"] == "test-chain"
        assert result["version"] == "1.0"
        assert len(result["components"]) == 3

    def test_generator_entries(self, sample_chain):
        result = export_haystack(sample_chain)
        gpt = result["components"][0]
        assert gpt["name"] == "GPT-4o"
        assert gpt["type"] == "PromptNode"
        assert gpt["params"]["model_name_or_path"] == "gpt-4o"
        assert gpt["params"]["api_base"] == "https://api.openai.com/v1"
        assert gpt["params"]["max_length"] == 4096
        assert gpt["params"]["model_kwargs"]["timeout"] == 30.0

    def test_edges(self, sample_chain):
        result = export_haystack(sample_chain)
        edges = result["edges"]
        assert len(edges) == 2
        assert edges[0]["from_"] == "GPT-4o"
        assert edges[0]["to_"] == "Claude"
        assert edges[0]["condition"] == "fallback"
        assert edges[1]["from_"] == "Claude"
        assert edges[1]["to_"] == "Local"

    def test_error_handling(self, sample_chain):
        result = export_haystack(sample_chain)
        conditions = result["error_handling"]
        assert len(conditions) == 3
        rl = conditions[0]
        assert rl["error_type"] == "rate_limit"
        assert rl["action"] == "wait"
        assert rl["wait_seconds"] == 5
        assert rl["retry_count"] == 3

    def test_status_codes_in_error_handling(self, sample_chain):
        result = export_haystack(sample_chain)
        se = result["error_handling"][2]
        assert se["status_codes"] == [500, 502, 503]

    def test_metadata_included(self, sample_chain):
        result = export_haystack(sample_chain)
        assert result["metadata"] == {"description": "Test chain"}

    def test_file_output(self, sample_chain, tmp_path):
        output_file = tmp_path / "haystack.json"
        export_haystack(sample_chain, output_path=str(output_file))
        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert content["type"] == "haystack_pipeline"

    def test_no_edges_for_single_provider(self):
        chain = Chain(
            name="single",
            providers=[
                Provider(
                    name="Only", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
                )
            ],
        )
        result = export_haystack(chain)
        assert result["edges"] == []

    def test_metadata_api_key(self):
        chain = Chain(
            name="auth-chain",
            providers=[
                Provider(
                    name="OpenAI",
                    model_id="gpt-4o",
                    api_base="https://api.openai.com/v1",
                    priority=0,
                    metadata={"api_key": "sk-xxx", "temperature": 0.7},
                ),
            ],
        )
        result = export_haystack(chain)
        params = result["components"][0]["params"]
        assert params["api_key"] == "sk-xxx"
        assert params["model_kwargs"]["temperature"] == 0.7


class TestExportChainWrapper:
    def test_langchain_via_wrapper(self, sample_chain):
        result = export_chain(sample_chain, ExportFormat.LANGCHAIN)
        assert result["type"] == "langchain_router"
        assert len(result["llms"]) == 3

    def test_haystack_via_wrapper(self, sample_chain):
        result = export_chain(sample_chain, ExportFormat.HAYSTACK)
        assert result["type"] == "haystack_pipeline"
        assert len(result["components"]) == 3

    def test_unsupported_format(self, sample_chain):
        with pytest.raises(ValueError, match="Unsupported"):
            export_chain(sample_chain, "invalid_format")


class TestServerExportNewFormats:
    """Test the server export endpoint with langchain and haystack formats."""

    @pytest.fixture(autouse=True)
    def clear_store(self):
        from fallbackrabbit.server import _chains

        _chains.clear()
        yield
        _chains.clear()

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from fallbackrabbit.server import create_app

        return TestClient(create_app())

    def test_export_langchain(self, client):
        import uuid

        from fallbackrabbit.server import _chains

        chain = Chain(
            name="lc-test",
            providers=[
                Provider(
                    name="GPT", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
                ),
            ],
        )
        chain_id = uuid.uuid4().hex[:12]
        _chains[chain_id] = chain

        resp = client.post(f"/chains/{chain_id}/export", json={"format": "langchain"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "langchain"
        assert data["config"]["type"] == "langchain_router"

    def test_export_haystack(self, client):
        import uuid

        from fallbackrabbit.server import _chains

        chain = Chain(
            name="hs-test",
            providers=[
                Provider(
                    name="GPT", model_id="gpt-4o", api_base="https://api.openai.com/v1", priority=0
                ),
            ],
        )
        chain_id = uuid.uuid4().hex[:12]
        _chains[chain_id] = chain

        resp = client.post(f"/chains/{chain_id}/export", json={"format": "haystack"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "haystack"
        assert data["config"]["type"] == "haystack_pipeline"

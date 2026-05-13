"""Tests for config_export module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fallbackrabbit.config_export import (
    export_chain,
    export_custom,
    export_litellm,
    export_openrouter,
)
from fallbackrabbit.models import Chain, ExportFormat, FallbackAction, FallbackRule, Provider

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
EXAMPLE_CHAIN = SCHEMAS_DIR / "example_chain.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_provider(
    name: str = "TestProvider", model_id: str = "test-model", priority: int = 0
) -> Provider:
    return Provider(
        name=name, model_id=model_id, api_base="https://api.test.com/v1", priority=priority
    )


def _make_chain(names: list[str] | None = None, rules: list[FallbackRule] | None = None) -> Chain:
    if names is None:
        names = ["Alpha", "Beta", "Gamma"]
    providers = [_make_provider(name=name, priority=i) for i, name in enumerate(names)]
    return Chain(name="test-chain", providers=providers, fallback_rules=rules or [])


def _make_example_chain() -> Chain:
    return Chain(
        name="example-chain",
        providers=[
            Provider(
                name="GPT-4o",
                model_id="gpt-4o",
                api_base="https://api.openai.com/v1",
                priority=0,
                max_tokens=4096,
                timeout=30,
                metadata={"provider_type": "openai"},
            ),
            Provider(
                name="Claude Sonnet",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com/v1",
                priority=1,
                max_tokens=4096,
                timeout=30,
                metadata={"provider_type": "anthropic"},
            ),
            Provider(
                name="Local Llama",
                model_id="llama3",
                api_base="http://localhost:11434/v1",
                priority=2,
                max_tokens=2048,
                timeout=60,
                metadata={"provider_type": "ollama"},
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type="rate_limit",
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
            FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
        ],
    )


# ---------------------------------------------------------------------------
# export_litellm
# ---------------------------------------------------------------------------


class TestExportLitellm:
    def test_basic_structure(self) -> None:
        chain = _make_chain()
        result = yaml.safe_load(export_litellm(chain))

        assert "model_list" in result
        assert len(result["model_list"]) == 3
        assert "router_settings" in result

    def test_model_entries(self) -> None:
        chain = _make_chain()
        result = yaml.safe_load(export_litellm(chain))

        for entry in result["model_list"]:
            assert "model_name" in entry
            assert "litellm_params" in entry
            assert "model" in entry["litellm_params"]
            assert "api_base" in entry["litellm_params"]
            assert "timeout" in entry["litellm_params"]
            assert "max_tokens" in entry["litellm_params"]

    def test_fallbacks(self) -> None:
        chain = _make_chain()
        result = yaml.safe_load(export_litellm(chain))

        # 3 providers → 2 fallback entries
        assert "fallbacks" in result
        assert len(result["fallbacks"]) == 2

    def test_with_rules(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(condition_error_type="timeout", action=FallbackAction.FAILOVER),
            ]
        )
        result = yaml.safe_load(export_litellm(chain))

        assert "fallback_rules" in result
        assert len(result["fallback_rules"]) == 1
        assert result["fallback_rules"][0]["error_type"] == "timeout"

    def test_example_chain(self) -> None:
        from fallbackrabbit.chain_schema import load_chain

        chain = load_chain(EXAMPLE_CHAIN)
        result = yaml.safe_load(export_litellm(chain))

        assert len(result["model_list"]) == 3
        assert result["model_list"][0]["litellm_params"]["model"] == "gpt-4o"

    def test_write_to_file(self, tmp_path: Path) -> None:
        chain = _make_chain()
        output_file = str(tmp_path / "litellm.yaml")
        export_litellm(chain, output_path=output_file)

        assert Path(output_file).exists()
        content = yaml.safe_load(Path(output_file).read_text())
        assert "model_list" in content


# ---------------------------------------------------------------------------
# export_openrouter
# ---------------------------------------------------------------------------


class TestExportOpenrouter:
    def test_basic_structure(self) -> None:
        chain = _make_chain()
        result = json.loads(export_openrouter(chain))

        assert "models" in result
        assert "fallback_order" in result
        assert "routing" in result

    def test_model_entries(self) -> None:
        chain = _make_chain()
        result = json.loads(export_openrouter(chain))

        assert len(result["models"]) == 3
        for model in result["models"]:
            assert "model" in model
            assert "priority" in model
            assert "max_tokens" in model

    def test_fallback_order(self) -> None:
        chain = _make_chain()
        result = json.loads(export_openrouter(chain))

        # fallback_order contains all model IDs
        assert result["fallback_order"] == ["test-model", "test-model", "test-model"]

    def test_routing_strategy(self) -> None:
        chain = _make_chain()
        result = json.loads(export_openrouter(chain))

        assert result["routing"]["strategy"] == "priority"

    def test_with_rules(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(condition_error_type="server_error", action=FallbackAction.FAILOVER),
            ]
        )
        result = json.loads(export_openrouter(chain))

        assert "fallback_rules" in result
        assert result["fallback_rules"][0]["error_type"] == "server_error"

    def test_example_chain(self) -> None:
        from fallbackrabbit.chain_schema import load_chain

        chain = load_chain(EXAMPLE_CHAIN)
        result = json.loads(export_openrouter(chain))

        assert len(result["models"]) == 3
        assert result["models"][0]["model"] == "gpt-4o"

    def test_write_to_file(self, tmp_path: Path) -> None:
        chain = _make_chain()
        output_file = str(tmp_path / "openrouter.json")
        export_openrouter(chain, output_path=output_file)

        assert Path(output_file).exists()
        content = json.loads(Path(output_file).read_text())
        assert "models" in content


# ---------------------------------------------------------------------------
# export_custom
# ---------------------------------------------------------------------------


class TestExportCustom:
    def test_basic_structure(self) -> None:
        chain = _make_chain()
        result = export_custom(chain)

        assert "chain_name" in result
        assert "providers" in result
        assert "routing" in result
        assert "fallback_rules" in result
        assert "metadata" in result

    def test_routing_table(self) -> None:
        chain = _make_chain()
        result = export_custom(chain)

        assert len(result["routing"]) == 3
        assert result["routing"][0]["provider_name"] == "Alpha"
        assert result["routing"][0]["failover_targets"] == ["Beta", "Gamma"]
        assert result["routing"][2]["failover_targets"] == []

    def test_provider_ordering(self) -> None:
        chain = _make_chain()
        result = export_custom(chain)

        # Should be sorted by priority
        priorities = [r["priority"] for r in result["routing"]]
        assert priorities == sorted(priorities)

    def test_with_rules(self) -> None:
        chain = _make_chain(
            rules=[
                FallbackRule(
                    condition_error_type="rate_limit",
                    action=FallbackAction.WAIT,
                    wait_seconds=5,
                    retry_count=3,
                ),
            ]
        )
        result = export_custom(chain)

        assert len(result["fallback_rules"]) == 1
        assert result["fallback_rules"][0]["error_type"] == "rate_limit"
        assert result["fallback_rules"][0]["action"] == "wait"

    def test_example_chain(self) -> None:
        from fallbackrabbit.chain_schema import load_chain

        chain = load_chain(EXAMPLE_CHAIN)
        result = export_custom(chain)

        assert result["chain_name"] == "example-chain"
        assert len(result["providers"]) == 3
        assert len(result["routing"]) == 3

    def test_write_to_file(self, tmp_path: Path) -> None:
        chain = _make_chain()
        output_file = str(tmp_path / "custom.json")
        export_custom(chain, output_path=output_file)

        assert Path(output_file).exists()
        content = json.loads(Path(output_file).read_text())
        assert content["chain_name"] == "test-chain"


# ---------------------------------------------------------------------------
# Backwards-compatible export_chain wrapper
# ---------------------------------------------------------------------------


class TestExportChainWrapper:
    def test_litellm_format(self) -> None:
        chain = _make_chain()
        result = export_chain(chain, ExportFormat.LITELLM)
        assert "model_list" in result

    def test_openrouter_format(self) -> None:
        chain = _make_chain()
        result = export_chain(chain, ExportFormat.OPENROUTER)
        assert "models" in result

    def test_custom_format(self) -> None:
        chain = _make_chain()
        result = export_chain(chain, ExportFormat.CUSTOM)
        assert "chain_name" in result

    def test_unsupported_format(self) -> None:
        chain = _make_chain()
        # Enum doesn't allow invalid values, but test the fallback
        with pytest.raises(ValueError):
            export_chain(chain, "invalid")  # type: ignore

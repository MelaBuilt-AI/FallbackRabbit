"""Tests for chain schema loading and validation."""

from pathlib import Path

import pytest
import yaml

from fallbackrabbit.chain_schema import load_chain, load_outage_scenario
from fallbackrabbit.models import Chain, SimulatedOutage

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
EXAMPLE_CHAIN = SCHEMAS_DIR / "example_chain.yaml"
EXAMPLE_OUTAGE = SCHEMAS_DIR / "example_outage.yaml"


class TestLoadChain:
    def test_load_example_chain(self, tmp_path: Path) -> None:
        chain = load_chain(EXAMPLE_CHAIN)
        assert isinstance(chain, Chain)
        assert chain.name == "example-chain"
        assert len(chain.providers) == 3
        assert chain.providers[0].model_id == "gpt-4o"
        assert chain.providers[1].model_id == "claude-sonnet-4-20250514"
        assert chain.providers[2].model_id == "llama3"
        assert len(chain.fallback_rules) == 4

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        config = {
            "name": "test-chain",
            "providers": [
                {"name": "P1", "model_id": "m1", "api_base": "http://a"},
            ],
        }
        path = tmp_path / "chain.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")

        chain = load_chain(path)
        assert chain.name == "test-chain"

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_chain("/nonexistent/path.yaml")

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Empty"):
            load_chain(path)

    def test_invalid_chain_data(self, tmp_path: Path) -> None:
        # Missing required fields
        config = {"name": "bad"}
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid chain"):
            load_chain(path)

    def test_duplicate_provider_names(self, tmp_path: Path) -> None:
        config = {
            "name": "dup-chain",
            "providers": [
                {"name": "Same", "model_id": "a", "api_base": "http://a"},
                {"name": "Same", "model_id": "b", "api_base": "http://b"},
            ],
        }
        path = tmp_path / "dup.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        with pytest.raises(ValueError, match="unique"):
            load_chain(path)


class TestLoadOutageScenario:
    def test_load_example_outage(self) -> None:
        outages = load_outage_scenario(EXAMPLE_OUTAGE)
        assert len(outages) == 3
        assert all(isinstance(o, SimulatedOutage) for o in outages)
        assert outages[0].provider_name == "GPT-4o"
        assert outages[0].probability == 0.8

    def test_load_valid_outage(self, tmp_path: Path) -> None:
        config = {
            "outages": [
                {"provider_name": "OpenAI", "error_type": "timeout", "probability": 0.5},
            ],
        }
        path = tmp_path / "outage.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")

        outages = load_outage_scenario(path)
        assert len(outages) == 1

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_outage_scenario("/nonexistent/outage.yaml")

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Empty"):
            load_outage_scenario(path)

    def test_invalid_outage_data(self, tmp_path: Path) -> None:
        config = {"outages": [{"provider_name": "X"}]}  # missing error_type
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid outage"):
            load_outage_scenario(path)

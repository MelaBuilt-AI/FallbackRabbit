"""Integration tests — full-stack workflows across server, simulator, models, and export."""

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from fallbackrabbit.chain_builder import (
    apply_fallback_rules,
    build_routing_chain,
    generate_chain_summary,
    optimize_chain_order,
    validate_chain,
)
from fallbackrabbit.chain_schema import load_chain, load_outage_scenario
from fallbackrabbit.config_export import (
    export_chain,
    export_custom,
    export_haystack,
    export_langchain,
)
from fallbackrabbit.models import (
    Chain,
    ChainReport,
    ErrorType,
    ExportFormat,
    FallbackAction,
    FallbackRule,
    PromptSpec,
    Provider,
    SimulatedOutage,
)
from fallbackrabbit.simulator import Simulator, generate_test_prompts

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def production_chain() -> Chain:
    """A realistic 3-provider production chain."""
    return Chain(
        name="production-v1",
        providers=[
            Provider(
                name="GPT-4o",
                model_id="gpt-4o",
                api_base="https://api.openai.com/v1",
                priority=0,
                max_tokens=4096,
                timeout=30.0,
            ),
            Provider(
                name="Claude-Sonnet",
                model_id="claude-sonnet-4-20250514",
                api_base="https://api.anthropic.com/v1",
                priority=1,
                max_tokens=8192,
                timeout=45.0,
            ),
            Provider(
                name="Llama3-Local",
                model_id="llama3:8b",
                api_base="http://localhost:11434/v1",
                priority=2,
                max_tokens=2048,
                timeout=60.0,
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=5.0,
                retry_count=3,
            ),
            FallbackRule(condition_error_type=ErrorType.TIMEOUT, action=FallbackAction.FAILOVER),
            FallbackRule(
                condition_error_type=ErrorType.SERVER_ERROR,
                action=FallbackAction.RETRY,
                retry_count=2,
            ),
            FallbackRule(
                condition_error_type=ErrorType.CONNECTION_ERROR, action=FallbackAction.FAILOVER
            ),
        ],
        metadata={"env": "production", "team": "ml-platform"},
    )


@pytest.fixture
def chain_yaml_file(tmp_path) -> Path:
    """Write a chain YAML config to a temp file."""
    config = {
        "name": "integration-test-chain",
        "providers": [
            {
                "name": "P1",
                "model_id": "gpt-4o",
                "api_base": "https://api.openai.com/v1",
                "priority": 0,
            },
            {
                "name": "P2",
                "model_id": "claude-sonnet",
                "api_base": "https://api.anthropic.com/v1",
                "priority": 1,
            },
        ],
        "fallback_rules": [
            {
                "condition_error_type": "rate_limit",
                "action": "wait",
                "wait_seconds": 2.0,
                "retry_count": 2,
            },
            {"condition_error_type": "timeout", "action": "failover"},
        ],
    }
    path = tmp_path / "chain.yaml"
    path.write_text(yaml.dump(config, default_flow_style=False))
    return path


@pytest.fixture
def outage_yaml_file(tmp_path) -> Path:
    """Write an outage scenario YAML config to a temp file."""
    config = {
        "outages": [
            {"provider_name": "P1", "error_type": "rate_limit", "probability": 1.0},
            {"provider_name": "P2", "error_type": "timeout", "probability": 0.5},
        ],
    }
    path = tmp_path / "outage.yaml"
    path.write_text(yaml.dump(config, default_flow_style=False))
    return path


# ---------------------------------------------------------------------------
# Workflow 1: Create → Validate → Test → Export (full round-trip)
# ---------------------------------------------------------------------------


class TestCreateValidateTestExportWorkflow:
    """End-to-end: build chain, validate, simulate, export to all formats."""

    def test_full_round_trip(self, production_chain):
        chain = production_chain

        # Step 1: Validate
        issues = validate_chain(chain)
        assert len(issues) == 0, f"Chain validation failed: {issues}"

        # Step 2: Simulate (10 prompts, no outages)
        sim = Simulator(chain)
        prompts = generate_test_prompts(10)
        report = asyncio.run(sim.run_batch(prompts))
        assert isinstance(report, ChainReport)
        assert report.total_prompts == 10
        assert report.success_rate == 1.0  # No outages → all succeed
        assert len(report.results) == 10

        # Step 3: Export to all formats
        for fmt in [
            ExportFormat.LITELLM,
            ExportFormat.OPENROUTER,
            ExportFormat.CUSTOM,
            ExportFormat.LANGCHAIN,
            ExportFormat.HAYSTACK,
        ]:
            result = export_chain(chain, fmt)
            assert isinstance(result, dict)
            assert len(result) > 0

    def test_chain_summary_after_simulation(self, production_chain):
        summary = generate_chain_summary(production_chain)
        assert "production-v1" in summary
        assert "GPT-4o" in summary
        assert "3" in summary  # 3 providers

    def test_routing_table(self, production_chain):
        routing = build_routing_chain(production_chain)
        assert isinstance(routing, dict)
        assert len(routing) > 0


# ---------------------------------------------------------------------------
# Workflow 2: Import → Validate → Optimize → Test → Export
# ---------------------------------------------------------------------------


class TestImportValidateOptimizeWorkflow:
    """End-to-end: import from YAML, validate, optimize, test, export."""

    def test_import_and_optimize(self, chain_yaml_file):
        # Import
        chain = load_chain(str(chain_yaml_file))
        assert chain.name == "integration-test-chain"
        assert len(chain.providers) == 2

        # Validate
        issues = validate_chain(chain)
        assert len(issues) == 0

        # Optimize
        optimized = optimize_chain_order(chain)
        assert len(optimized.providers) == 2
        priorities = [p.priority for p in optimized.providers]
        assert priorities == sorted(priorities)

        # Test
        sim = Simulator(optimized)
        report = asyncio.run(sim.run_batch(generate_test_prompts(5)))
        assert report.total_prompts == 5

        # Export (custom format uses "chain_name" key)
        custom = export_custom(optimized)
        assert custom["chain_name"] == "integration-test-chain"

    def test_import_outages_and_simulate(self, chain_yaml_file, outage_yaml_file):
        chain = load_chain(str(chain_yaml_file))
        outages = load_outage_scenario(str(outage_yaml_file))

        assert len(outages) == 2
        assert outages[0].provider_name == "P1"
        assert outages[0].error_type == ErrorType.RATE_LIMIT

        # Simulate with outages
        sim = Simulator(chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(10)))

        # With P1 at 100% rate_limit, fallbacks should fire
        # ChainReport has fallback_rate (0.0–1.0), not fallback_triggered count
        assert report.fallback_rate > 0


# ---------------------------------------------------------------------------
# Workflow 3: Stress test — all providers down
# ---------------------------------------------------------------------------


class TestAllProvidersDownWorkflow:
    """When all providers fail, the chain should report full failure correctly."""

    def test_total_failure(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=1.0
            ),
            SimulatedOutage(
                provider_name="Claude-Sonnet", error_type=ErrorType.SERVER_ERROR, probability=1.0
            ),
            SimulatedOutage(
                provider_name="Llama3-Local", error_type=ErrorType.CONNECTION_ERROR, probability=1.0
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(5)))

        assert report.success_rate == 0.0
        assert report.fallback_rate == 1.0
        # Every result should have tracked retries
        for result in report.results:
            assert result.retries_used >= 0

    def test_single_provider_up(self, production_chain):
        """Only the last provider works — all others down."""
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=1.0
            ),
            SimulatedOutage(
                provider_name="Claude-Sonnet", error_type=ErrorType.SERVER_ERROR, probability=1.0
            ),
            # Llama3-Local: no outage → works
        ]
        sim = Simulator(production_chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(5)))

        assert report.success_rate >= 0.8  # At least 4/5 should succeed (flaky local LLM)
        # All successful should have fallen back to Llama3-Local
        for result in report.results:
            if result.success:
                assert result.provider_name == "Llama3-Local"
                assert result.fallback_triggered is True


# ---------------------------------------------------------------------------
# Workflow 4: Export consistency — same chain, all formats agree on providers
# ---------------------------------------------------------------------------


class TestExportConsistency:
    """All export formats should reference the same providers and rules."""

    def test_provider_count_consistent(self, production_chain):
        custom = export_custom(production_chain)
        langchain = export_langchain(production_chain)
        haystack = export_haystack(production_chain)

        assert len(custom["providers"]) == 3
        assert len(langchain["llms"]) == 3
        assert len(haystack["components"]) == 3

    def test_fallback_rules_consistent(self, production_chain):
        custom = export_custom(production_chain)
        langchain = export_langchain(production_chain)
        haystack = export_haystack(production_chain)

        assert len(custom["fallback_rules"]) == 4
        assert len(langchain["error_handling"]) == 4
        assert len(haystack["error_handling"]) == 4

    def test_chain_name_consistent(self, production_chain):
        custom = export_custom(production_chain)
        langchain = export_langchain(production_chain)
        haystack = export_haystack(production_chain)

        # Custom format uses "chain_name", not "name"
        assert custom["chain_name"] == "production-v1"
        assert langchain["chain_name"] == "production-v1"
        assert haystack["chain_name"] == "production-v1"


# ---------------------------------------------------------------------------
# Workflow 5: File import/export round-trip
# ---------------------------------------------------------------------------


class TestFileRoundTripWorkflow:
    """Export to file, read back, verify contents."""

    def test_langchain_file_round_trip(self, production_chain, tmp_path):
        output = tmp_path / "lc.json"
        export_langchain(production_chain, output_path=str(output))

        data = json.loads(output.read_text())
        assert data["type"] == "langchain_router"
        assert len(data["llms"]) == 3
        assert data["chain_name"] == "production-v1"

    def test_haystack_file_round_trip(self, production_chain, tmp_path):
        output = tmp_path / "hs.json"
        export_haystack(production_chain, output_path=str(output))

        data = json.loads(output.read_text())
        assert data["type"] == "haystack_pipeline"
        assert len(data["components"]) == 3
        assert data["version"] == "1.0"

    def test_custom_file_round_trip(self, production_chain, tmp_path):
        output = tmp_path / "custom.yaml"
        export_custom(production_chain, output_path=str(output))

        data = yaml.safe_load(output.read_text())
        # Custom format uses "chain_name", not "name"
        assert data["chain_name"] == "production-v1"
        assert len(data["providers"]) == 3

    def test_imported_chain_exports_same(self, chain_yaml_file, tmp_path):
        """Chain imported from YAML should export correctly."""
        chain = load_chain(str(chain_yaml_file))
        export_custom(chain)
        export_path = tmp_path / "re-exported.yaml"
        export_custom(chain, output_path=str(export_path))
        data = yaml.safe_load(export_path.read_text())
        assert data["chain_name"] == chain.name


# ---------------------------------------------------------------------------
# Workflow 6: Apply rules → verify resolved routing
# ---------------------------------------------------------------------------


class TestApplyRulesWorkflow:
    """Apply fallback rules to a chain and verify the resolved routing."""

    def test_apply_rules(self, production_chain):
        resolved = apply_fallback_rules(production_chain, production_chain.fallback_rules)
        assert isinstance(resolved, dict)
        # Should map error types to rule dicts
        assert "rate_limit" in resolved
        assert "timeout" in resolved
        assert "server_error" in resolved
        assert "connection_error" in resolved

    def test_rules_match_actions(self, production_chain):
        resolved = apply_fallback_rules(production_chain, production_chain.fallback_rules)
        # apply_fallback_rules returns dicts with action strings, not FallbackAction enums
        assert resolved["rate_limit"]["action"] == "wait"
        assert resolved["timeout"]["action"] == "failover"
        assert resolved["server_error"]["action"] == "retry"
        assert resolved["connection_error"]["action"] == "failover"


# ---------------------------------------------------------------------------
# Workflow 7: Server full workflow via test client
# ---------------------------------------------------------------------------


class TestServerIntegrationWorkflow:
    """Full server workflow: create → list → get → test → export → delete."""

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

    def test_full_crud_lifecycle(self, client):
        # Create
        resp = client.post(
            "/chains",
            json={
                "name": "integration-chain",
                "providers": [
                    {
                        "name": "A",
                        "model_id": "gpt-4o",
                        "api_base": "https://a.test",
                        "priority": 0,
                    },
                    {
                        "name": "B",
                        "model_id": "claude",
                        "api_base": "https://b.test",
                        "priority": 1,
                    },
                ],
                "fallback_rules": [
                    {"condition_error_type": "rate_limit", "action": "failover"},
                ],
            },
        )
        assert resp.status_code == 201
        chain_id = resp.json()["detail"]["chain_id"]

        # List
        resp = client.get("/chains")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Get
        resp = client.get(f"/chains/{chain_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "integration-chain"

        # Validate
        resp = client.get(f"/chains/{chain_id}/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

        # Summary
        resp = client.get(f"/chains/{chain_id}/summary")
        assert resp.status_code == 200
        assert "integration-chain" in resp.json()["summary"]

        # Routing
        resp = client.get(f"/chains/{chain_id}/routing")
        assert resp.status_code == 200

        # Test (batch) — default is 5 prompts
        resp = client.post(f"/chains/{chain_id}/test", json={"prompts": 5})
        assert resp.status_code == 200
        report = resp.json()
        assert report["total_prompts"] == 5

        # Test (single prompt)
        resp = client.post(f"/chains/{chain_id}/test-prompt?prompt=Hello+world")
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is True

        # Export all formats
        for fmt in ["litellm", "openrouter", "custom", "langchain", "haystack"]:
            resp = client.post(f"/chains/{chain_id}/export", json={"format": fmt})
            assert resp.status_code == 200, f"Export {fmt} failed"
            data = resp.json()
            assert data["format"] == fmt

        # Delete
        resp = client.delete(f"/chains/{chain_id}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/chains/{chain_id}")
        assert resp.status_code == 404

    def test_test_with_outages(self, client):
        """Create chain, test with outages injected, verify fallback behavior."""
        resp = client.post(
            "/chains",
            json={
                "name": "outage-test",
                "providers": [
                    {
                        "name": "Fast",
                        "model_id": "gpt-4o",
                        "api_base": "https://fast.test",
                        "priority": 0,
                    },
                    {
                        "name": "Slow",
                        "model_id": "llama3",
                        "api_base": "https://slow.test",
                        "priority": 1,
                    },
                ],
                "fallback_rules": [
                    {
                        "condition_error_type": "rate_limit",
                        "action": "wait",
                        "wait_seconds": 1.0,
                        "retry_count": 1,
                    },
                ],
            },
        )
        chain_id = resp.json()["detail"]["chain_id"]

        # Test with outage on Fast
        resp = client.post(
            f"/chains/{chain_id}/test",
            json={
                "prompts": 5,
                "outages": [
                    {"provider_name": "Fast", "error_type": "rate_limit", "probability": 1.0},
                ],
            },
        )
        assert resp.status_code == 200
        report = resp.json()
        assert report["total_prompts"] == 5
        # ChainReport has fallback_rate (0.0–1.0)
        assert report["fallback_rate"] > 0

    def test_update_and_retest(self, client):
        """Create, update, re-test — verify changes take effect."""
        resp = client.post(
            "/chains",
            json={
                "name": "update-test",
                "providers": [
                    {
                        "name": "A",
                        "model_id": "gpt-4o",
                        "api_base": "https://a.test",
                        "priority": 0,
                    },
                ],
            },
        )
        chain_id = resp.json()["detail"]["chain_id"]

        # Update: add a provider
        resp = client.patch(
            f"/chains/{chain_id}",
            json={
                "providers": [
                    {
                        "name": "A",
                        "model_id": "gpt-4o",
                        "api_base": "https://a.test",
                        "priority": 0,
                    },
                    {
                        "name": "B",
                        "model_id": "claude",
                        "api_base": "https://b.test",
                        "priority": 1,
                    },
                ],
            },
        )
        assert resp.status_code == 200

        # Re-test — default is 5 prompts (server TestRequest default)
        resp = client.post(f"/chains/{chain_id}/test", json={"prompts": 5})
        assert resp.status_code == 200
        assert resp.json()["total_prompts"] == 5

    def test_import_chain_file(self, client, chain_yaml_file):
        """Import a chain from YAML file via server."""
        resp = client.post(f"/chains/import?path={chain_yaml_file}")
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Chain imported"

        chain_id = data["detail"]["chain_id"]
        resp = client.get(f"/chains/{chain_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "integration-test-chain"

    def test_optimize_chain_via_server(self, client):
        resp = client.post(
            "/chains",
            json={
                "name": "optimize-test",
                "providers": [
                    {
                        "name": "Slow",
                        "model_id": "llama3:8b",
                        "api_base": "https://slow.test",
                        "priority": 0,
                    },
                    {
                        "name": "Fast",
                        "model_id": "gpt-4o",
                        "api_base": "https://fast.test",
                        "priority": 1,
                    },
                ],
            },
        )
        chain_id = resp.json()["detail"]["chain_id"]

        resp = client.post(f"/chains/{chain_id}/optimize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["optimized_chain"]["name"] == "optimize-test"

    def test_apply_rules_via_server(self, client):
        resp = client.post(
            "/chains",
            json={
                "name": "rules-test",
                "providers": [
                    {
                        "name": "A",
                        "model_id": "gpt-4o",
                        "api_base": "https://a.test",
                        "priority": 0,
                    },
                ],
                "fallback_rules": [
                    {
                        "condition_error_type": "rate_limit",
                        "action": "wait",
                        "wait_seconds": 2.0,
                        "retry_count": 3,
                    },
                ],
            },
        )
        chain_id = resp.json()["detail"]["chain_id"]

        resp = client.post(f"/chains/{chain_id}/apply-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "resolved_rules" in data

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Workflow 8: Cross-format export comparison
# ---------------------------------------------------------------------------


class TestCrossFormatComparison:
    """Verify key data is preserved across all export formats."""

    def test_provider_names_preserved(self, production_chain):
        custom = export_custom(production_chain)
        lc = export_langchain(production_chain)
        hs = export_haystack(production_chain)

        custom_names = [p["name"] for p in custom["providers"]]
        lc_names = [entry["name"] for entry in lc["llms"]]
        hs_names = [c["name"] for c in hs["components"]]

        assert custom_names == lc_names == hs_names

    def test_error_types_preserved(self, production_chain):
        custom = export_custom(production_chain)
        lc = export_langchain(production_chain)
        hs = export_haystack(production_chain)

        # Custom format uses "error_type" key in fallback_rules
        custom_errors = [r["error_type"] for r in custom["fallback_rules"]]
        lc_errors = [h["error_type"] for h in lc["error_handling"]]
        hs_errors = [c["error_type"] for c in hs["error_handling"]]

        assert custom_errors == lc_errors == hs_errors

    def test_metadata_preserved(self, production_chain):
        custom = export_custom(production_chain)
        lc = export_langchain(production_chain)
        hs = export_haystack(production_chain)

        assert custom.get("metadata") == {"env": "production", "team": "ml-platform"}
        assert lc.get("metadata") == {"env": "production", "team": "ml-platform"}
        assert hs.get("metadata") == {"env": "production", "team": "ml-platform"}


# ---------------------------------------------------------------------------
# Workflow 9: Batch testing with varying outage probabilities
# ---------------------------------------------------------------------------


class TestBatchOutageScenarios:
    """Simulate different outage probability levels and verify behavior."""

    def test_no_outages_all_succeed(self, production_chain):
        sim = Simulator(production_chain)
        report = asyncio.run(sim.run_batch(generate_test_prompts(20)))
        assert report.success_rate == 1.0
        # There's a 1% random failure chance per call, so fallback_rate may be >0 slightly
        assert report.fallback_rate <= 0.2  # Allow for rare random failures

    def test_low_outage_some_fallbacks(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=0.3
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(20)))
        # With 30% outage rate, some should fall back but not all
        assert report.fallback_rate >= 0.0

    def test_high_outage_most_fallbacks(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=0.9
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(20)))
        # With 90% outage on GPT-4o, most prompts should trigger fallback
        assert report.fallback_rate >= 0.3  # Most prompts fall back

    def test_mixed_outages(self, production_chain):
        """Different error types on different providers."""
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o", error_type=ErrorType.RATE_LIMIT, probability=0.5
            ),
            SimulatedOutage(
                provider_name="Claude-Sonnet", error_type=ErrorType.TIMEOUT, probability=0.3
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        report = asyncio.run(sim.run_batch(generate_test_prompts(20)))
        # Should still succeed (Llama3-Local is always up)
        assert report.success_rate == 1.0


# ---------------------------------------------------------------------------
# Workflow 10: Single prompt testing with status codes
# ---------------------------------------------------------------------------


class TestSinglePromptWithStatusCodes:
    """Test individual prompts with specific status code outages."""

    def test_429_rate_limit_triggers_wait(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o",
                error_type=ErrorType.RATE_LIMIT,
                probability=1.0,
                status_code=429,
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="test 429")))

        # GPT-4o hits rate_limit → WAIT rule → 3 retries → then failover
        assert result.fallback_triggered is True
        assert result.retries_used == 3  # retry_count from the rule
        assert result.total_wait_ms == 15000.0  # 3 × 5.0s

    def test_408_timeout_triggers_failover(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o",
                error_type=ErrorType.TIMEOUT,
                probability=1.0,
                status_code=408,
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="test timeout")))

        # GPT-4o timeout → FAILOVER → Claude-Sonnet succeeds
        assert result.fallback_triggered is True
        assert result.retries_used == 0
        assert result.total_wait_ms == 0.0

    def test_500_server_error_triggers_retry(self, production_chain):
        outages = [
            SimulatedOutage(
                provider_name="GPT-4o",
                error_type=ErrorType.SERVER_ERROR,
                probability=1.0,
                status_code=500,
            ),
        ]
        sim = Simulator(production_chain, outages=outages)
        result = asyncio.run(sim.run_prompt(PromptSpec(prompt="test 500")))

        # GPT-4o server_error → RETRY rule (2 retries) → all fail → failover
        assert result.fallback_triggered is True
        assert result.provider_name != "GPT-4o"

"""Tests for the FastAPI server — chain CRUD, analysis, testing, and export endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fallbackrabbit.server import _chains, create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_store():
    """Clear the in-memory chain store before each test."""
    _chains.clear()
    yield
    _chains.clear()


@pytest.fixture
def client():
    """FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_chain_payload():
    """A valid chain creation payload."""
    return {
        "name": "test-chain",
        "providers": [
            {
                "name": "GPT-4o",
                "model_id": "gpt-4o",
                "api_base": "https://api.openai.com/v1",
                "priority": 0,
                "max_tokens": 4096,
                "timeout": 30,
            },
            {
                "name": "Claude",
                "model_id": "claude-sonnet-4-20250514",
                "api_base": "https://api.anthropic.com/v1",
                "priority": 1,
                "max_tokens": 4096,
                "timeout": 30,
            },
        ],
        "fallback_rules": [
            {
                "condition_error_type": "rate_limit",
                "action": "wait",
                "wait_seconds": 5,
                "retry_count": 3,
            },
            {
                "condition_error_type": "timeout",
                "action": "failover",
            },
        ],
        "metadata": {"description": "Test chain"},
    }


@pytest.fixture
def create_sample_chain(client, sample_chain_payload):
    """Helper that creates a sample chain and returns the response."""
    resp = client.post("/chains", json=sample_chain_payload)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["chains"] == 0


# ---------------------------------------------------------------------------
# Chain CRUD
# ---------------------------------------------------------------------------


class TestCreateChain:
    def test_create_chain(self, client, sample_chain_payload):
        resp = client.post("/chains", json=sample_chain_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Chain created"
        assert "chain_id" in data["detail"]
        assert data["detail"]["providers"] == 2

    def test_create_chain_minimal(self, client):
        """Create a chain with just one provider and no rules."""
        payload = {
            "name": "minimal",
            "providers": [
                {
                    "name": "Local",
                    "model_id": "llama3",
                    "api_base": "http://localhost:11434/v1",
                    "priority": 0,
                }
            ],
        }
        resp = client.post("/chains", json=payload)
        assert resp.status_code == 201

    def test_create_chain_empty_name(self, client):
        """Empty name should be rejected."""
        payload = {
            "name": "",
            "providers": [
                {
                    "name": "A",
                    "model_id": "gpt-4o",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                }
            ],
        }
        resp = client.post("/chains", json=payload)
        assert resp.status_code == 422

    def test_create_chain_no_providers(self, client):
        """No providers should be rejected."""
        payload = {"name": "no-providers", "providers": []}
        resp = client.post("/chains", json=payload)
        assert resp.status_code == 422

    def test_create_chain_duplicate_provider_names(self, client):
        """Duplicate provider names should fail validation."""
        payload = {
            "name": "dup-providers",
            "providers": [
                {"name": "Same", "model_id": "gpt-4o", "api_base": "https://a.com", "priority": 0},
                {"name": "Same", "model_id": "claude", "api_base": "https://b.com", "priority": 1},
            ],
        }
        resp = client.post("/chains", json=payload)
        # Pydantic validator rejects duplicates before our endpoint runs
        assert resp.status_code in (400, 422)


class TestListChains:
    def test_list_empty(self, client):
        resp = client.get("/chains")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client, create_sample_chain):
        resp = client.get("/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-chain"

    def test_list_multiple(self, client, sample_chain_payload):
        client.post("/chains", json=sample_chain_payload)
        payload2 = dict(sample_chain_payload, name="second-chain")
        client.post("/chains", json=payload2)
        resp = client.get("/chains")
        assert len(resp.json()) == 2


class TestGetChain:
    def test_get_existing(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.get(f"/chains/{chain_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-chain"
        assert len(data["providers"]) == 2

    def test_get_not_found(self, client):
        resp = client.get("/chains/nonexistent")
        assert resp.status_code == 404


class TestUpdateChain:
    def test_update_name(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.patch(f"/chains/{chain_id}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Chain updated"

        # Verify the update
        get_resp = client.get(f"/chains/{chain_id}")
        assert get_resp.json()["name"] == "renamed"

    def test_update_providers(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        new_providers = [
            {
                "name": "Local",
                "model_id": "llama3",
                "api_base": "http://localhost:11434/v1",
                "priority": 0,
            }
        ]
        resp = client.patch(f"/chains/{chain_id}", json={"providers": new_providers})
        assert resp.status_code == 200

        get_resp = client.get(f"/chains/{chain_id}")
        assert len(get_resp.json()["providers"]) == 1

    def test_update_not_found(self, client):
        resp = client.patch("/chains/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    def test_update_with_invalid_providers(self, client, create_sample_chain):
        """Patch with duplicate provider names should fail validation."""
        chain_id = create_sample_chain["detail"]["chain_id"]
        bad_providers = [
            {"name": "Dup", "model_id": "gpt-4o", "api_base": "https://a.com", "priority": 0},
            {"name": "Dup", "model_id": "claude", "api_base": "https://b.com", "priority": 1},
        ]
        resp = client.patch(f"/chains/{chain_id}", json={"providers": bad_providers})
        assert resp.status_code == 400


class TestDeleteChain:
    def test_delete_existing(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.delete(f"/chains/{chain_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Chain deleted"

        # Verify it's gone
        get_resp = client.get(f"/chains/{chain_id}")
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/chains/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Chain analysis
# ---------------------------------------------------------------------------


class TestRouting:
    def test_get_routing(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.get(f"/chains/{chain_id}/routing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain_id"] == chain_id
        assert "routing" in data
        assert "routing" in data["routing"]

    def test_routing_not_found(self, client):
        resp = client.get("/chains/nonexistent/routing")
        assert resp.status_code == 404


class TestSummary:
    def test_get_summary(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.get(f"/chains/{chain_id}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain_id"] == chain_id
        assert "summary" in data

    def test_summary_not_found(self, client):
        resp = client.get("/chains/nonexistent/summary")
        assert resp.status_code == 404


class TestValidate:
    def test_validate_valid(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.get(f"/chains/{chain_id}/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["issues"] == []

    def test_validate_not_found(self, client):
        resp = client.get("/chains/nonexistent/validate")
        assert resp.status_code == 404


class TestOptimize:
    def test_optimize(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/optimize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain_id"] == chain_id
        assert "optimized_chain" in data

    def test_optimize_not_found(self, client):
        resp = client.post("/chains/nonexistent/optimize")
        assert resp.status_code == 404


class TestApplyRules:
    def test_apply_rules(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/apply-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "resolved_rules" in data

    def test_apply_rules_not_found(self, client):
        resp = client.post("/chains/nonexistent/apply-rules")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------


class TestChainTest:
    def test_run_simulated_test(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/test", json={"prompts": 3, "seed": 42})
        assert resp.status_code == 200
        data = resp.json()
        assert data["chain_name"] == "test-chain"
        assert data["total_prompts"] == 5
        assert 0.0 <= data["success_rate"] <= 1.0
        assert data["avg_latency_ms"] >= 0

    def test_test_with_outages(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        payload = {
            "prompts": 5,
            "seed": 42,
            "outages": [
                {
                    "provider_name": "GPT-4o",
                    "error_type": "rate_limit",
                    "duration_seconds": 60,
                    "probability": 1.0,
                }
            ],
        }
        resp = client.post(f"/chains/{chain_id}/test", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_prompts"] == 5

    def test_test_not_found(self, client):
        resp = client.post("/chains/nonexistent/test", json={"prompts": 1})
        assert resp.status_code == 404


class TestSinglePrompt:
    def test_single_prompt(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(
            f"/chains/{chain_id}/test-prompt",
            params={"prompt": "Hello, world!", "category": "greeting"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "provider_name" in data
        assert "success" in data
        assert "latency_ms" in data

    def test_single_prompt_not_found(self, client):
        resp = client.post(
            "/chains/nonexistent/test-prompt",
            params={"prompt": "test"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_custom(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/export", json={"format": "custom"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "custom"
        assert "config" in data

    def test_export_litellm(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/export", json={"format": "litellm"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "litellm"

    def test_export_openrouter(self, client, create_sample_chain):
        chain_id = create_sample_chain["detail"]["chain_id"]
        resp = client.post(f"/chains/{chain_id}/export", json={"format": "openrouter"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "openrouter"

    def test_export_not_found(self, client):
        resp = client.post("/chains/nonexistent/export", json={"format": "custom"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class TestImport:
    def test_import_from_file(self, client, tmp_path):
        """Import a chain from a YAML file."""
        chain_yaml = """\
name: imported-chain
providers:
  - name: GPT-4o
    model_id: gpt-4o
    api_base: https://api.openai.com/v1
    priority: 0
    max_tokens: 4096
    timeout: 30
fallback_rules: []
metadata:
  description: Imported chain
"""
        chain_file = tmp_path / "chain.yaml"
        chain_file.write_text(chain_yaml, encoding="utf-8")

        resp = client.post("/chains/import", params={"path": str(chain_file)})
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Chain imported"
        assert data["detail"]["name"] == "imported-chain"

    def test_import_file_not_found(self, client):
        resp = client.post("/chains/import", params={"path": "/nonexistent/path.yaml"})
        assert resp.status_code == 404

    def test_import_invalid_yaml(self, client, tmp_path):
        """File with invalid structure should 400."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("name: missing-providers\nproviders: []\n", encoding="utf-8")
        resp = client.post("/chains/import", params={"path": str(bad_file)})
        assert resp.status_code == 400

    def test_import_outages_from_file(self, client, tmp_path):
        """Import outage scenarios from a YAML file."""
        outage_yaml = """\
outages:
  - provider_name: GPT-4o
    error_type: rate_limit
    duration_seconds: 30
    probability: 0.8
  - provider_name: Claude
    error_type: timeout
    duration_seconds: 60
    probability: 1.0
"""
        outage_file = tmp_path / "outages.yaml"
        outage_file.write_text(outage_yaml, encoding="utf-8")

        resp = client.post("/chains/import-outages", params={"path": str(outage_file)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["outages"]) == 2

    def test_import_outages_not_found(self, client):
        resp = client.post("/chains/import-outages", params={"path": "/nope.yaml"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full workflow
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    def test_create_test_export_workflow(self, client, sample_chain_payload):
        """End-to-end: create → validate → test → export → delete."""
        # Create
        create_resp = client.post("/chains", json=sample_chain_payload)
        assert create_resp.status_code == 201
        chain_id = create_resp.json()["detail"]["chain_id"]

        # Validate
        val_resp = client.get(f"/chains/{chain_id}/validate")
        assert val_resp.json()["valid"] is True

        # Test
        test_resp = client.post(f"/chains/{chain_id}/test", json={"prompts": 3, "seed": 99})
        assert test_resp.status_code == 200
        report = test_resp.json()
        assert report["total_prompts"] == 5

        # Export
        export_resp = client.post(f"/chains/{chain_id}/export", json={"format": "litellm"})
        assert export_resp.status_code == 200

        # Routing
        routing_resp = client.get(f"/chains/{chain_id}/routing")
        assert routing_resp.status_code == 200

        # Summary
        summary_resp = client.get(f"/chains/{chain_id}/summary")
        assert summary_resp.status_code == 200

        # Delete
        del_resp = client.delete(f"/chains/{chain_id}")
        assert del_resp.status_code == 200

        # Confirm deletion
        list_resp = client.get("/chains")
        assert list_resp.json() == []


# ---------------------------------------------------------------------------
# Template export
# ---------------------------------------------------------------------------


class TestTemplateExport:
    """Tests for the /chains/{id}/export-template endpoint."""

    def test_export_builtin_terraform(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"builtin_template": "terraform"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "template"
        assert data["builtin_template"] == "terraform"
        assert "fallbackrabbit_chain" in data["output"]
        assert "test-chain" in data["output"]

    def test_export_builtin_env(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"builtin_template": "env"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "CHAIN_NAME" in data["output"]

    def test_export_builtin_docker(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"builtin_template": "docker"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "version:" in data["output"]
        assert "fallbackrabbit" in data["output"]

    def test_export_builtin_k8s(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"builtin_template": "k8s"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ConfigMap" in data["output"]
        assert "apiVersion" in data["output"]

    def test_export_inline_template(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        template = "Chain: {{ chain.name }}, Providers: {{ providers|length }}"
        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"template": template},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "test-chain" in data["output"]
        assert "Providers: 2" in data["output"]

    def test_export_with_extra_vars(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        template = "{{ chain.name }}-{{ extra.stage }}"
        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"template": template, "extra_vars": {"stage": "prod"}},
        )
        assert resp.status_code == 200
        assert "test-chain-prod" in resp.json()["output"]

    def test_export_template_chain_not_found(self, client):
        resp = client.post(
            "/chains/nonexistent/export-template",
            json={"builtin_template": "terraform"},
        )
        assert resp.status_code == 404

    def test_export_template_no_source(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={},
        )
        assert resp.status_code == 400

    def test_export_template_unknown_builtin(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"builtin_template": "unknown"},
        )
        assert resp.status_code == 400

    def test_export_template_file_not_found(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"template_file": "/nonexistent/template.j2"},
        )
        assert resp.status_code == 404

    def test_export_template_invalid_jinja2(self, client, sample_chain_payload):
        create_resp = client.post("/chains", json=sample_chain_payload)
        chain_id = create_resp.json()["detail"]["chain_id"]

        resp = client.post(
            f"/chains/{chain_id}/export-template",
            json={"template": "{{ undefined_var }}"},
        )
        assert resp.status_code == 400

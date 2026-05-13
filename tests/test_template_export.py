"""Tests for template-based export (Jinja2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fallbackrabbit.models import Chain, ErrorType, FallbackAction, FallbackRule, Provider
from fallbackrabbit.template_export import (
    BUILTIN_TEMPLATES,
    DOCKER_COMPOSE_TEMPLATE,
    ENV_FILE_TEMPLATE,
    K8S_CONFIGMAP_TEMPLATE,
    TERRAFORM_TEMPLATE,
    render_template,
    render_template_file,
)


@pytest.fixture
def sample_chain() -> Chain:
    """Create a sample chain for testing."""
    return Chain(
        name="test-chain",
        providers=[
            Provider(
                name="GPT-4o",
                model_id="gpt-4o",
                api_base="https://api.openai.com/v1",
                priority=0,
                max_tokens=4096,
                timeout=30,
            ),
            Provider(
                name="Claude",
                model_id="claude-sonnet",
                api_base="https://api.anthropic.com/v1",
                priority=1,
                max_tokens=4096,
                timeout=30,
            ),
        ],
        fallback_rules=[
            FallbackRule(
                condition_error_type=ErrorType.RATE_LIMIT,
                action=FallbackAction.WAIT,
                wait_seconds=5,
                retry_count=3,
            ),
            FallbackRule(
                condition_error_type=ErrorType.TIMEOUT,
                action=FallbackAction.FAILOVER,
            ),
        ],
        metadata={"env": "production"},
    )


class TestRenderTemplate:
    """Tests for render_template function."""

    def test_basic_string_template(self, sample_chain: Chain):
        """Test rendering a simple Jinja2 template string."""
        template = "Chain: {{ chain.name }}, Providers: {{ providers|length }}"
        result = render_template(sample_chain, template)
        assert "Chain: test-chain" in result
        assert "Providers: 2" in result

    def test_provider_loop(self, sample_chain: Chain):
        """Test iterating over providers in a template."""
        template = (
            "{% for p in providers %}"
            "{{ p.name }}:{{ p.model_id }}"
            "{% if not loop.last %},{% endif %}"
            "{% endfor %}"
        )
        result = render_template(sample_chain, template)
        assert "GPT-4o:gpt-4o" in result
        assert "Claude:claude-sonnet" in result

    def test_routing_table(self, sample_chain: Chain):
        """Test access to routing_table variable."""
        template = (
            "{{ routing_table[0].provider_name }}"
            " -> {{ routing_table[0].failover_targets|join(', ') }}"
        )
        result = render_template(sample_chain, template)
        assert "GPT-4o" in result
        assert "Claude" in result

    def test_rules_data(self, sample_chain: Chain):
        """Test access to rules_data variable."""
        template = (
            "{% for r in rules_data %}"
            "{{ r.error_type }}:{{ r.action }}"
            "{% if not loop.last %};{% endif %}"
            "{% endfor %}"
        )
        result = render_template(sample_chain, template)
        assert "rate_limit:wait" in result
        assert "timeout:failover" in result

    def test_extra_vars(self, sample_chain: Chain):
        """Test passing extra variables to template."""
        template = "Env: {{ extra.env }}, Region: {{ extra.region }}"
        result = render_template(
            sample_chain, template, extra_vars={"env": "staging", "region": "us-east-1"}
        )
        assert "Env: staging" in result
        assert "Region: us-east-1" in result

    def test_output_path(self, sample_chain: Chain, tmp_path: Path):
        """Test writing rendered output to a file."""
        template = "Chain: {{ chain.name }}"
        output_file = str(tmp_path / "output.txt")
        render_template(sample_chain, template, output_path=output_file)
        assert Path(output_file).read_text() == "Chain: test-chain"

    def test_strict_undefined_raises(self, sample_chain: Chain):
        """Test that referencing an undefined variable raises an error."""
        template = "{{ nonexistent_var }}"
        with pytest.raises(Exception):  # noqa: B017
            render_template(sample_chain, template)

    def test_chain_metadata(self, sample_chain: Chain):
        """Test accessing chain metadata in template."""
        template = "Environment: {{ chain.metadata.env }}"
        result = render_template(sample_chain, template)
        assert "Environment: production" in result

    def test_provider_priority_sorting(self, sample_chain: Chain):
        """Test that providers are sorted by priority in template."""
        template = "{% for p in providers %}{{ p.priority }}{% endfor %}"
        result = render_template(sample_chain, template)
        assert result == "01"

    def test_provider_properties(self, sample_chain: Chain):
        """Test accessing all provider properties."""
        template = (
            "{{ providers[0].name }}|{{ providers[0].model_id }}|"
            "{{ providers[0].api_base }}|{{ providers[0].max_tokens }}|"
            "{{ providers[0].timeout }}"
        )
        result = render_template(sample_chain, template)
        assert "GPT-4o|gpt-4o|https://api.openai.com/v1|4096|30" in result

    def test_export_format_enum(self, sample_chain: Chain):
        """Test that export_format enum is available in template."""
        template = "Formats: {{ export_format.LITELLM }}, {{ export_format.CUSTOM }}"
        result = render_template(sample_chain, template)
        assert "Formats: litellm, custom" in result

    def test_rules_object_access(self, sample_chain: Chain):
        """Test accessing FallbackRule objects directly in template."""
        template = (
            "{% for r in rules %}"
            "{{ r.condition_error_type.value }}-{{ r.action.value }}"
            "{% endfor %}"
        )
        result = render_template(sample_chain, template)
        assert "rate_limit-wait" in result
        assert "timeout-failover" in result


class TestRenderTemplateFile:
    """Tests for render_template_file function."""

    def test_render_from_file(self, sample_chain: Chain, tmp_path: Path):
        """Test rendering from a template file."""
        template_file = tmp_path / "template.j2"
        template_file.write_text(
            "Chain: {{ chain.name }}, Count: {{ providers|length }}", encoding="utf-8"
        )

        result = render_template_file(sample_chain, str(template_file))
        assert "Chain: test-chain" in result
        assert "Count: 2" in result

    def test_render_from_file_with_output(self, sample_chain: Chain, tmp_path: Path):
        """Test rendering from a file and writing to an output file."""
        template_file = tmp_path / "template.j2"
        template_file.write_text("Result: {{ chain.name }}", encoding="utf-8")

        output_file = str(tmp_path / "output.txt")
        render_template_file(sample_chain, str(template_file), output_path=output_file)
        assert Path(output_file).read_text() == "Result: test-chain"

    def test_render_from_file_with_extra_vars(self, sample_chain: Chain, tmp_path: Path):
        """Test rendering from a file with extra variables."""
        template_file = tmp_path / "template.j2"
        template_file.write_text("Env: {{ extra.env }}", encoding="utf-8")

        result = render_template_file(sample_chain, str(template_file), extra_vars={"env": "dev"})
        assert "Env: dev" in result

    def test_missing_template_file(self, sample_chain: Chain):
        """Test that a missing template file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            render_template_file(sample_chain, "/nonexistent/template.j2")


class TestBuiltinTemplates:
    """Tests for built-in templates."""

    def test_terraform_template(self, sample_chain: Chain):
        """Test Terraform built-in template."""
        result = render_template(sample_chain, TERRAFORM_TEMPLATE)
        assert "fallbackrabbit_chain" in result
        assert '"test-chain"' in result
        assert '"GPT-4o"' in result
        assert '"gpt-4o"' in result
        assert "rate_limit" in result

    def test_terraform_template_output_file(self, sample_chain: Chain, tmp_path: Path):
        """Test Terraform template writing to file."""
        output_file = str(tmp_path / "main.tf")
        render_template(sample_chain, TERRAFORM_TEMPLATE, output_path=output_file)
        content = Path(output_file).read_text()
        assert "fallbackrabbit_chain" in content

    def test_docker_template(self, sample_chain: Chain):
        """Test Docker Compose built-in template."""
        result = render_template(sample_chain, DOCKER_COMPOSE_TEMPLATE)
        assert "version:" in result
        assert "fallbackrabbit:" in result
        assert "CHAIN_NAME" in result
        assert "PROVIDER_1_NAME" in result
        assert "PROVIDER_2_NAME" in result

    def test_k8s_template(self, sample_chain: Chain):
        """Test Kubernetes ConfigMap built-in template."""
        result = render_template(sample_chain, K8S_CONFIGMAP_TEMPLATE)
        assert "apiVersion: v1" in result
        assert "kind: ConfigMap" in result
        assert "test_chain-config" in result
        assert "chain.yaml" in result
        assert "GPT-4o" in result

    def test_env_template(self, sample_chain: Chain):
        """Test .env built-in template."""
        result = render_template(sample_chain, ENV_FILE_TEMPLATE)
        assert "CHAIN_NAME=test-chain" in result
        assert "PROVIDER_1_NAME=GPT-4o" in result
        assert "PROVIDER_2_NAME=Claude" in result
        assert "PROVIDER_1_MODEL_ID=gpt-4o" in result

    def test_builtin_templates_dict(self):
        """Test BUILTIN_TEMPLATES dict has expected keys."""
        assert set(BUILTIN_TEMPLATES.keys()) == {"terraform", "docker", "k8s", "env"}

    def test_builtin_terraform_by_name(self, sample_chain: Chain):
        """Test rendering using BUILTIN_TEMPLATES dict by name."""
        result = render_template(sample_chain, BUILTIN_TEMPLATES["terraform"])
        assert "fallbackrabbit_chain" in result

    def test_builtin_env_by_name(self, sample_chain: Chain):
        """Test rendering using BUILTIN_TEMPLATES dict by name."""
        result = render_template(sample_chain, BUILTIN_TEMPLATES["env"])
        assert "CHAIN_NAME=test-chain" in result

    def test_builtin_docker_with_extra_vars(self, sample_chain: Chain):
        """Test Docker template with extra variables (not used in default template)."""
        result = render_template(
            sample_chain, DOCKER_COMPOSE_TEMPLATE, extra_vars={"tag": "latest"}
        )
        assert "fallbackrabbit" in result


class TestTemplateEdgeCases:
    """Tests for edge cases in template rendering."""

    def test_empty_chain_name(self):
        """Test template rendering with a minimal chain."""
        chain = Chain(
            name="x",
            providers=[
                Provider(name="p1", model_id="m1", api_base="http://localhost"),
            ],
        )
        result = render_template(chain, "{{ chain.name }}:{{ providers|length }}")
        assert "x:1" in result

    def test_chain_with_no_rules(self):
        """Test template rendering with no fallback rules."""
        chain = Chain(
            name="no-rules",
            providers=[
                Provider(name="p1", model_id="m1", api_base="http://localhost"),
            ],
        )
        template = (
            "{% for r in rules %}{{ r.condition_error_type }}{% endfor %}Empty:{{ rules|length }}"
        )
        result = render_template(chain, template)
        assert "Empty:0" in result

    def test_single_provider_chain(self):
        """Test template with a single provider (no failover targets)."""
        chain = Chain(
            name="single",
            providers=[
                Provider(name="only", model_id="m1", api_base="http://localhost"),
            ],
        )
        template = "Failover: {{ routing_table[0].failover_targets|join(',') }}"
        result = render_template(chain, template)
        assert "Failover:" in result

    def test_many_providers(self):
        """Test template with many providers."""
        providers = [
            Provider(name=f"p{i}", model_id=f"m{i}", api_base=f"http://localhost/{i}", priority=i)
            for i in range(10)
        ]
        chain = Chain(name="big-chain", providers=providers)
        result = render_template(chain, "{{ providers|length }}")
        assert "10" in result

    def test_special_chars_in_chain_name(self):
        """Test template with special characters in chain name."""
        chain = Chain(
            name="test-chain_v2.0",
            providers=[
                Provider(name="p1", model_id="m1", api_base="http://localhost"),
            ],
        )
        result = render_template(chain, "{{ chain.name }}")
        assert "test-chain_v2.0" in result

    def test_conditional_rendering(self, sample_chain: Chain):
        """Test conditional rendering based on chain data."""
        template = (
            "{% if providers|length > 1 %}"
            "Multi-provider: {{ providers|length }}"
            "{% else %}"
            "Single provider"
            "{% endif %}"
        )
        result = render_template(sample_chain, template)
        assert "Multi-provider: 2" in result

    def test_jinja2_filters(self, sample_chain: Chain):
        """Test using Jinja2 built-in filters."""
        template = (
            "{{ chain.name|upper }}|{{ providers|length }}|{{ chain.name|replace('-', '_') }}"
        )
        result = render_template(sample_chain, template)
        assert "TEST-CHAIN|2|test_chain" in result

    def test_complex_template_with_all_variables(self, sample_chain: Chain):
        """Test a complex template that uses all available variables."""
        template = """Chain: {{ chain.name }}
Providers: {{ providers|length }}
First: {{ providers[0].name }}
Routing: {{ routing_table[0].failover_targets|join(', ') }}
Rules: {{ rules|length }}
Data rules: {{ rules_data|length }}
Format: {{ export_format.CUSTOM }}"""
        result = render_template(sample_chain, template)
        assert "Chain: test-chain" in result
        assert "Providers: 2" in result
        assert "First: GPT-4o" in result
        assert "Rules: 2" in result

"""Template-based export — render chains to user-defined Jinja2 templates.

Users provide a Jinja2 template string (or file path) and this module renders
the chain configuration into any format they want — Terraform, Docker Compose,
Kubernetes manifests, proprietary configs, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

from .models import Chain, ExportFormat


def render_template(
    chain: Chain,
    template: str,
    *,
    output_path: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> str:
    """Render a Jinja2 template with chain data.

    The template receives the following variables:
        - chain: the full Chain model
        - providers: sorted list of providers (by priority)
        - rules: list of FallbackRule objects
        - routing_table: list of dicts with provider info + failover_targets
        - export_format: the current ExportFormat enum
        - extra: any additional variables passed via extra_vars

    Args:
        chain: The chain to render.
        template: Jinja2 template string.
        output_path: Optional path to write the rendered output.
        extra_vars: Optional dict of extra template variables.

    Returns:
        Rendered string.
    """
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    # Build routing table (same structure as export_custom)
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

    # Build fallback rules (same structure as export_custom)
    rules_data = []
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
        rules_data.append(rule_dict)

    env = jinja2.Environment(
        loader=jinja2.BaseLoader(),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )
    tmpl = env.from_string(template)

    result = tmpl.render(
        chain=chain,
        providers=sorted_providers,
        rules=chain.fallback_rules,
        routing_table=routing_table,
        rules_data=rules_data,
        export_format=ExportFormat,
        extra=extra_vars or {},
    )

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


def render_template_file(
    chain: Chain,
    template_path: str,
    *,
    output_path: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> str:
    """Render a Jinja2 template from a file with chain data.

    Args:
        chain: The chain to render.
        template_path: Path to a Jinja2 template file.
        output_path: Optional path to write the rendered output.
        extra_vars: Optional dict of extra template variables.

    Returns:
        Rendered string.
    """
    template_text = Path(template_path).read_text(encoding="utf-8")
    return render_template(
        chain,
        template_text,
        output_path=output_path,
        extra_vars=extra_vars,
    )


# ---------------------------------------------------------------------------
# Built-in templates for common formats
# ---------------------------------------------------------------------------

TERRAFORM_TEMPLATE = """\
resource "fallbackrabbit_chain" "{{ chain.name | replace('-', '_') | lower }}" {
  name = "{{ chain.name }}"

  {% for provider in providers %}
  provider {
    name       = "{{ provider.name }}"
    model_id   = "{{ provider.model_id }}"
    api_base   = "{{ provider.api_base }}"
    priority   = {{ provider.priority }}
    max_tokens = {{ provider.max_tokens }}
    timeout    = {{ provider.timeout }}
  }
  {% endfor %}

  {% for rule in rules %}
  fallback_rule {
    error_type   = "{{ rule.condition_error_type.value }}"
    action       = "{{ rule.action.value }}"
    wait_seconds = {{ rule.wait_seconds }}
    retry_count  = {{ rule.retry_count }}
  }
  {% endfor %}
}
"""

DOCKER_COMPOSE_TEMPLATE = """\
version: "3.8"
services:
  fallbackrabbit:
    image: fallbackrabbit:latest
    environment:
      CHAIN_NAME: "{{ chain.name }}"
      {% for provider in providers %}
      PROVIDER_{{ loop.index }}_NAME: "{{ provider.name }}"
      PROVIDER_{{ loop.index }}_MODEL: "{{ provider.model_id }}"
      PROVIDER_{{ loop.index }}_API_BASE: "{{ provider.api_base }}"
      PROVIDER_{{ loop.index }}_PRIORITY: "{{ provider.priority }}"
      PROVIDER_{{ loop.index }}_MAX_TOKENS: "{{ provider.max_tokens }}"
      PROVIDER_{{ loop.index }}_TIMEOUT: "{{ provider.timeout }}"
      {% endfor %}
"""

K8S_CONFIGMAP_TEMPLATE = """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ chain.name | replace('-', '_') | lower }}-config
data:
  chain.yaml: |
    name: {{ chain.name }}
    providers:
{% for provider in providers %}
      - name: {{ provider.name }}
        model_id: {{ provider.model_id }}
        api_base: {{ provider.api_base }}
        priority: {{ provider.priority }}
        max_tokens: {{ provider.max_tokens }}
        timeout: {{ provider.timeout }}
{% endfor %}
    fallback_rules:
{% for rule in rules %}
      - error_type: {{ rule.condition_error_type.value }}
        action: {{ rule.action.value }}
        wait_seconds: {{ rule.wait_seconds }}
        retry_count: {{ rule.retry_count }}
{% endfor %}
"""

ENV_FILE_TEMPLATE = """\
# FallbackRabbit chain: {{ chain.name }}
# Generated from template export

CHAIN_NAME={{ chain.name }}

{% for provider in providers %}
# Provider: {{ provider.name }} (priority {{ provider.priority }})
PROVIDER_{{ loop.index }}_NAME={{ provider.name }}
PROVIDER_{{ loop.index }}_MODEL_ID={{ provider.model_id }}
PROVIDER_{{ loop.index }}_API_BASE={{ provider.api_base }}
PROVIDER_{{ loop.index }}_PRIORITY={{ provider.priority }}
PROVIDER_{{ loop.index }}_MAX_TOKENS={{ provider.max_tokens }}
PROVIDER_{{ loop.index }}_TIMEOUT={{ provider.timeout }}
{% endfor %}
"""

BUILTIN_TEMPLATES: dict[str, str] = {
    "terraform": TERRAFORM_TEMPLATE,
    "docker": DOCKER_COMPOSE_TEMPLATE,
    "k8s": K8S_CONFIGMAP_TEMPLATE,
    "env": ENV_FILE_TEMPLATE,
}
"""Built-in template names mapping to Jinja2 template strings."""

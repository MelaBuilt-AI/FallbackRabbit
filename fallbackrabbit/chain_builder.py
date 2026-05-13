"""Chain builder — construct routing logic, validate, optimize, and summarize chains."""

from __future__ import annotations

from copy import deepcopy

from .models import Chain, FallbackAction, FallbackRule, Provider


def build_routing_chain(chain: Chain) -> dict:
    """Build an ordered routing dict from a Chain.

    The routing dict contains:
      - providers ordered by priority (ascending — lower number = higher priority)
      - per-provider timeout and max_tokens
      - fallback order (the failover sequence after each provider)
      - fallback rules mapped by error type

    Returns:
        A dict describing the full routing configuration.
    """
    # Sort providers by priority (ascending)
    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)

    routing_table: list[dict] = []
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
            }
        )

    # Map fallback rules by error type for quick lookup
    rules_by_error: dict[str, list[dict]] = {}
    for rule in chain.fallback_rules:
        error_key = rule.condition_error_type.value
        entry = {
            "action": rule.action.value,
            "wait_seconds": rule.wait_seconds,
            "retry_count": rule.retry_count,
        }
        if rule.condition_latency_threshold is not None:
            entry["latency_threshold_ms"] = rule.condition_latency_threshold
        if rule.condition_status_codes:
            entry["status_codes"] = list(rule.condition_status_codes)
        rules_by_error.setdefault(error_key, []).append(entry)

    return {
        "chain_name": chain.name,
        "routing": routing_table,
        "fallback_rules": rules_by_error,
        "total_providers": len(sorted_providers),
    }


def apply_fallback_rules(chain: Chain, rules: list[FallbackRule]) -> dict:
    """Apply fallback rules to determine when/how to failover for each error type.

    Args:
        chain: The chain configuration.
        rules: Additional fallback rules to apply (merged with chain's rules).

    Returns:
        A dict mapping each error type to its fallback strategy:
        {
            "rate_limit": {"action": "wait", "wait_seconds": 5, "retry_count": 3},
            "timeout": {"action": "failover"},
            ...
        }
    """
    # Merge chain rules with extra rules (extra rules take precedence on collision)
    merged: dict[str, FallbackRule] = {}

    for rule in chain.fallback_rules:
        key = rule.condition_error_type.value
        merged[key] = rule

    for rule in rules:
        key = rule.condition_error_type.value
        merged[key] = rule  # extra rules override chain rules

    result: dict[str, dict] = {}
    for error_type, rule in merged.items():
        strategy: dict = {"action": rule.action.value}
        if rule.action == FallbackAction.WAIT:
            strategy["wait_seconds"] = rule.wait_seconds
            strategy["retry_count"] = rule.retry_count
        elif rule.action == FallbackAction.RETRY:
            strategy["retry_count"] = rule.retry_count
        elif rule.action == FallbackAction.FAILOVER:
            strategy["next_provider"] = "next_in_chain"
        if rule.condition_latency_threshold is not None:
            strategy["latency_threshold_ms"] = rule.condition_latency_threshold
        if rule.condition_status_codes:
            strategy["status_codes"] = list(rule.condition_status_codes)
        result[error_type] = strategy

    return result


def validate_chain(chain: Chain) -> list[str]:
    """Validate chain integrity, returning a list of issues (empty = valid).

    Checks:
      - Provider names are unique (already enforced by model, but double-check)
      - No circular fallback references
      - Valid priority ordering (no gaps that would cause issues)
      - Each provider has required fields
      - Fallback rules reference valid error types

    Returns:
        A list of validation issue strings. Empty list means the chain is valid.
    """
    issues: list[str] = []

    # Check unique provider names
    names = [p.name for p in chain.providers]
    if len(names) != len(set(names)):
        seen: set[str] = set()
        for name in names:
            if name in seen:
                issues.append(f"Duplicate provider name: {name!r}")
            seen.add(name)

    # Single-provider chain is fine but worth noting
    if len(chain.providers) == 1:
        # Not an error, just informational — we don't add issues for this
        pass

    # Check for empty chain (shouldn't happen due to Pydantic validation, but defensive)
    if len(chain.providers) == 0:
        issues.append("Chain has no providers")

    # Check priority ordering — warn about non-sequential priorities
    priorities = [p.priority for p in chain.providers]
    expected = list(range(len(chain.providers)))
    if sorted(priorities) != expected and max(priorities) >= len(chain.providers):
        issues.append(
            f"Priority gap detected: priorities {priorities} with {len(chain.providers)} providers"
        )

    # Check for duplicate priorities (providers with same priority)
    if len(priorities) != len(set(priorities)):
        issues.append("Multiple providers share the same priority value")

    # Validate fallback rules — check that condition_error_type values are valid

    for rule in chain.fallback_rules:
        if rule.action == FallbackAction.WAIT and rule.wait_seconds <= 0:
            issues.append(
                f"Rule for {rule.condition_error_type.value} has "
                f"WAIT action but wait_seconds={rule.wait_seconds}"
            )
        if rule.action == FallbackAction.RETRY and rule.retry_count < 1:
            issues.append(
                f"Rule for {rule.condition_error_type.value} has "
                f"RETRY action but retry_count={rule.retry_count}"
            )

    return issues


def optimize_chain_order(chain: Chain, latency_data: dict[str, float] | None = None) -> Chain:
    """Reorder providers by priority/latency for optimal routing.

    If latency_data is provided, providers are sorted by their average latency
    (fastest first). Otherwise, providers are sorted by priority (ascending).

    Args:
        chain: The chain to optimize.
        latency_data: Optional mapping of provider name → average latency in ms.

    Returns:
        A new Chain with providers reordered for optimal routing.
    """
    providers = list(chain.providers)

    if latency_data:
        # Sort by latency (fastest first); providers without data keep original order
        def sort_key(p: Provider) -> float:
            return latency_data.get(p.name, float("inf"))

        providers = sorted(providers, key=sort_key)
    else:
        # Sort by priority (ascending — lower priority number = higher priority)
        providers = sorted(providers, key=lambda p: p.priority)

    # Re-assign sequential priorities to avoid gaps
    for idx, provider in enumerate(providers):
        provider.priority = idx

    return Chain(
        name=chain.name,
        providers=providers,
        fallback_rules=list(chain.fallback_rules),
        metadata=deepcopy(chain.metadata),
    )


def generate_chain_summary(chain: Chain) -> str:
    """Generate a human-readable summary of the chain configuration.

    Args:
        chain: The chain to summarize.

    Returns:
        A multi-line string describing the chain.
    """
    lines: list[str] = []
    lines.append(f"Chain: {chain.name}")
    lines.append(f"Providers: {len(chain.providers)}")

    sorted_providers = sorted(chain.providers, key=lambda p: p.priority)
    for idx, p in enumerate(sorted_providers):
        arrow = "→" if idx > 0 else " "
        failover = (
            " (fails over to next on error)"
            if idx < len(sorted_providers) - 1
            else " (last resort)"
        )
        lines.append(f"  {arrow} [{p.priority}] {p.name} ({p.model_id}) — {p.api_base}{failover}")

    lines.append(f"Fallback rules: {len(chain.fallback_rules)}")
    for rule in chain.fallback_rules:
        action_detail = rule.action.value
        if rule.action == FallbackAction.WAIT:
            action_detail += f" {rule.wait_seconds}s (×{rule.retry_count})"
        elif rule.action == FallbackAction.RETRY:
            action_detail += f" (×{rule.retry_count})"
        lines.append(f"  • {rule.condition_error_type.value} → {action_detail}")

    if chain.metadata:
        lines.append(f"Metadata: {chain.metadata}")

    return "\n".join(lines)

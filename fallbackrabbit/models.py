"""Core data models for FallbackRabbit."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ErrorType(StrEnum):
    """Types of errors that can trigger fallback rules."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    CONNECTION_ERROR = "connection_error"


class FallbackAction(StrEnum):
    """Actions a fallback rule can take."""

    RETRY = "retry"
    FAILOVER = "failover"
    WAIT = "wait"


class ExportFormat(StrEnum):
    """Supported export formats."""

    LITELLM = "litellm"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"
    LANGCHAIN = "langchain"
    HAYSTACK = "haystack"
    TEMPLATE = "template"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class Provider(BaseModel):
    """An LLM provider in the fallback chain."""

    name: str = Field(..., description="Human-readable provider name")
    model_id: str = Field(..., description="Model identifier (e.g. 'gpt-4o')")
    api_base: str = Field(..., description="Base URL for the provider API")
    priority: int = Field(default=0, ge=0, description="Lower = higher priority")
    max_tokens: int = Field(default=4096, ge=1, description="Max tokens per request")
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra provider config")


# ---------------------------------------------------------------------------
# FallbackRule
# ---------------------------------------------------------------------------


class FallbackRule(BaseModel):
    """Rule that triggers a fallback action based on observed conditions."""

    condition_error_type: ErrorType = Field(..., description="Error type that triggers this rule")
    condition_latency_threshold: float | None = Field(
        default=None, ge=0, description="Latency threshold (ms) to trigger"
    )
    condition_status_codes: list[int] = Field(
        default_factory=list, description="HTTP status codes that trigger this rule"
    )
    action: FallbackAction = Field(..., description="What to do when rule matches")
    wait_seconds: float = Field(
        default=0, ge=0, description="Seconds to wait before action (for wait)"
    )
    retry_count: int = Field(default=1, ge=1, description="Number of retries (for retry action)")


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------


class Chain(BaseModel):
    """A fallback chain — an ordered list of providers with rules."""

    name: str = Field(..., description="Chain name")
    providers: list[Provider] = Field(..., min_length=1, description="Ordered provider list")
    fallback_rules: list[FallbackRule] = Field(default_factory=list, description="Fallback rules")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra chain config")

    @field_validator("providers")
    @classmethod
    def providers_must_have_unique_names(cls, v: list[Provider]) -> list[Provider]:
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError("Provider names must be unique within a chain")
        return v


# ---------------------------------------------------------------------------
# Testing models
# ---------------------------------------------------------------------------


class PromptSpec(BaseModel):
    """A prompt used for testing a chain."""

    prompt: str = Field(..., description="The prompt text to send")
    category: str = Field(default="general", description="Category tag for grouping")
    expected_behavior: str = Field(
        default="returns a valid response", description="What we expect to happen"
    )


class PromptResult(BaseModel):
    """Result of a single test prompt against a provider."""

    provider_name: str
    prompt_id: str = Field(default="", description="Identifier for the test prompt")
    success: bool
    latency_ms: float
    error: str | None = None
    fallback_triggered: bool = False
    status_code: int | None = Field(default=None, description="HTTP status code from the response")
    retries_used: int = Field(default=0, description="Number of retries attempted")
    total_wait_ms: float = Field(default=0.0, description="Total wait time in ms across retries")


class ChainReport(BaseModel):
    """Aggregated test report for an entire chain."""

    chain_name: str
    total_prompts: int
    results: list[PromptResult] = Field(default_factory=list)
    success_rate: float = Field(default=0.0, ge=0, le=1)
    avg_latency_ms: float = Field(default=0.0, ge=0)
    fallback_rate: float = Field(default=0.0, ge=0, le=1)


# ---------------------------------------------------------------------------
# Simulation models
# ---------------------------------------------------------------------------


class SimulatedOutage(BaseModel):
    """Configuration for simulating a provider outage during testing."""

    provider_name: str = Field(..., description="Which provider to affect")
    error_type: ErrorType = Field(..., description="Type of outage to simulate")
    duration_seconds: float = Field(default=60.0, gt=0, description="How long the outage lasts")
    probability: float = Field(
        default=1.0, ge=0, le=1, description="Probability of triggering (0-1)"
    )
    status_code: int | None = Field(
        default=None, description="HTTP status code to associate with this outage"
    )

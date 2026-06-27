"""FallbackRabbit — Auto-generate and test fallback/middleware chains for LLM-powered apps."""

__version__ = "0.1.0"

from .chain_builder import (
    apply_fallback_rules,
    build_routing_chain,
    generate_chain_summary,
    optimize_chain_order,
    validate_chain,
)
from .config_export import (
    export_custom,
    export_haystack,
    export_langchain,
    export_litellm,
    export_openrouter,
)
from .models import (
    Chain,
    ChainReport,
    ErrorType,
    ExportFormat,
    FallbackAction,
    FallbackRule,
    PromptResult,
    PromptSpec,
    Provider,
    SimulatedOutage,
)
from .simulator import Simulator, generate_test_prompts

__all__ = [
    # Version
    "__version__",
    # Models
    "Chain",
    "ChainReport",
    "ErrorType",
    "ExportFormat",
    "FallbackAction",
    "FallbackRule",
    "PromptResult",
    "PromptSpec",
    "Provider",
    "SimulatedOutage",
    # Chain builder
    "apply_fallback_rules",
    "build_routing_chain",
    "generate_chain_summary",
    "optimize_chain_order",
    "validate_chain",
    # Simulator
    "Simulator",
    "generate_test_prompts",
    # Export
    "export_custom",
    "export_haystack",
    "export_langchain",
    "export_litellm",
    "export_openrouter",
]
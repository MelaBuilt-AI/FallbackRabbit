"""FallbackRabbit — Auto-generate and test fallback/middleware chains for LLM-powered apps."""

__version__ = "0.1.0"

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
from .chain_builder import (
    apply_fallback_rules,
    build_routing_chain,
    generate_chain_summary,
    optimize_chain_order,
    validate_chain,
)
from .simulator import Simulator, generate_test_prompts
from .config_export import (
    export_custom,
    export_haystack,
    export_langchain,
    export_litellm,
    export_openrouter,
)

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
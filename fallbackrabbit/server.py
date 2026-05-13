"""FastAPI server for FallbackRabbit — REST API for chain management and test execution."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from .chain_builder import (
    apply_fallback_rules,
    build_routing_chain,
    generate_chain_summary,
    optimize_chain_order,
    validate_chain,
)
from .chain_schema import load_chain, load_outage_scenario
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
    ExportFormat,
    FallbackRule,
    PromptResult,
    PromptSpec,
    Provider,
    SimulatedOutage,
)
from .simulator import Simulator, generate_test_prompts
from .storage import (
    ChainNotFoundError,
    MemoryStorage,
    StorageBackend,
    get_storage,
)

# ---------------------------------------------------------------------------
# Module-level storage (swappable for testing / persistence)
# ---------------------------------------------------------------------------

_storage: StorageBackend = MemoryStorage()


# Backwards-compatible alias: tests import _chains for fixture clearing.
# It delegates to the current storage backend.
class _ChainProxy(dict):
    """Dict-like proxy that delegates to the active storage backend.

    Only supports the subset of dict operations used by existing tests:
    - ``_chains[cid] = chain``  →  ``_storage.create(chain, chain_id=cid)``
    - ``_chains[cid]``          →  ``_storage.get(cid)``
    - ``cid in _chains``       →  ``_storage.exists(cid)``
    - ``del _chains[cid]``     →  ``_storage.delete(cid)``
    - ``len(_chains)``         →  number of stored chains
    - ``_chains.clear()``      →  ``_storage.clear()`` (MemoryStorage) or reset
    - ``_chains.items()``      →  ``_storage.list_all()``
    """

    def __setitem__(self, key: str, value: Chain) -> None:
        try:
            _storage.update(key, value)
        except ChainNotFoundError:
            _storage.create(value, chain_id=key)

    def __getitem__(self, key: str) -> Chain:
        return _storage.get(key)

    def __contains__(self, key: str) -> bool:
        return _storage.exists(key)

    def __delitem__(self, key: str) -> None:
        _storage.delete(key)

    def __len__(self) -> int:
        return len(_storage.list_all())

    def __iter__(self):
        for cid, _ in _storage.list_all():
            yield cid

    def items(self):
        return _storage.list_all()

    def clear(self) -> None:
        if isinstance(_storage, MemoryStorage):
            _storage.clear()
        else:
            # For persistent storage, delete all chains one by one
            for cid, _ in list(_storage.list_all()):
                _storage.delete(cid)

    def values(self):
        return [chain for _, chain in _storage.list_all()]

    def keys(self):
        return [cid for cid, _ in _storage.list_all()]


_chains = _ChainProxy()


def set_storage(storage: StorageBackend) -> None:
    """Replace the active storage backend (used by tests and startup config)."""
    global _storage
    _storage = storage


def get_active_storage() -> StorageBackend:
    """Return the active storage backend."""
    return _storage


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChainCreateRequest(BaseModel):
    """Request body for creating a new chain."""

    name: str = Field(..., min_length=1, description="Chain name")
    providers: list[Provider] = Field(..., min_length=1, description="Ordered provider list")
    fallback_rules: list[FallbackRule] = Field(default_factory=list, description="Fallback rules")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra chain config")


class ChainUpdateRequest(BaseModel):
    """Request body for updating an existing chain. Only supplied fields are patched."""

    name: str | None = None
    providers: list[Provider] | None = None
    fallback_rules: list[FallbackRule] | None = None
    metadata: dict[str, Any] | None = None


class TestRequest(BaseModel):
    """Request body for running a test against a chain."""

    prompts: int = Field(default=5, ge=1, le=100, description="Number of test prompts")
    seed: int | None = Field(default=None, description="Random seed for reproducibility")
    outages: list[SimulatedOutage] = Field(
        default_factory=list, description="Outage scenarios to inject"
    )
    use_real_calls: bool = Field(
        default=False, description="Use real API calls instead of simulation"
    )


class TemplateExportRequest(BaseModel):
    """Request body for template-based export."""

    template: str | None = Field(default=None, description="Jinja2 template string")
    template_file: str | None = Field(
        default=None, description="Path to Jinja2 template file on server"
    )
    builtin_template: str | None = Field(
        default=None,
        description="Built-in template name (terraform, docker, k8s, env)",
    )
    extra_vars: dict[str, str] = Field(default_factory=dict, description="Extra template variables")


class ExportRequest(BaseModel):
    """Request body for exporting a chain."""

    format: ExportFormat = Field(
        default=ExportFormat.CUSTOM,
        description="Export format (litellm, openrouter, custom, langchain, haystack, template)",
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
    detail: dict[str, Any] | None = None


class RoutingResponse(BaseModel):
    """Routing table response."""

    chain_id: str
    chain_name: str
    routing: dict[str, Any]


class SummaryResponse(BaseModel):
    """Chain summary response."""

    chain_id: str
    chain_name: str
    summary: str


class OptimizationResponse(BaseModel):
    """Optimized chain response."""

    chain_id: str
    original_name: str
    optimized_chain: Chain


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown — clear in-memory store on shutdown."""
    yield
    _chains.clear()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    storage_url: str | None = None,
    api_keys: list[str] | None = None,
    auth_enabled: bool = False,
    rate_limit_rpm: int | None = None,
    rate_limit_burst: int | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        storage_url: Storage backend URL. Defaults to in-memory.
            - ``None`` or ``"memory"`` — in-memory (ephemeral)
            - ``"sqlite:///path/to/chains.db"`` — SQLite persistence
            - ``"sqlite://"``, ``"sqlite"`` — default SQLite path
        api_keys: List of valid API keys. Also reads from ``FALLBACKRABBIT_API_KEYS`` env var.
        auth_enabled: Enable API key authentication. Defaults to False.
        rate_limit_rpm: Requests per minute per IP. None disables rate limiting.
        rate_limit_burst: Burst size per IP. Defaults to 10 if rpm is set.
    """
    global _storage
    _storage = get_storage(storage_url)

    # Configure auth
    from .auth import APIKeyAuth, APIKeyAuthMiddleware, set_auth

    auth = APIKeyAuth(keys=api_keys, enabled=auth_enabled)
    set_auth(auth)

    app = FastAPI(
        title="FallbackRabbit",
        version="0.1.0",
        description="API for managing and testing LLM fallback chains",
        lifespan=lifespan,
    )

    # Add rate limit middleware if configured
    if rate_limit_rpm is not None:
        from .ratelimit import RateLimiter, RateLimitMiddleware

        limiter = RateLimiter(
            requests_per_minute=rate_limit_rpm,
            burst=rate_limit_burst or 10,
        )
        app.add_middleware(RateLimitMiddleware, limiter=limiter)

    # Add auth middleware if enabled (after rate limiter so auth is checked second)
    if auth_enabled:
        app.add_middleware(APIKeyAuthMiddleware, auth=auth)

    _register_routes(app)

    # Mount dashboard
    from .dashboard import mount_dashboard

    mount_dashboard(app)

    return app


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _register_routes(app: FastAPI) -> None:
    """Register all API routes."""

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "chains": len(_chains)}

    # ------------------------------------------------------------------
    # Chain CRUD
    # ------------------------------------------------------------------
    @app.post("/chains", response_model=MessageResponse, status_code=201, tags=["chains"])
    async def create_chain(req: ChainCreateRequest):
        """Create a new fallback chain."""
        try:
            chain = Chain(
                name=req.name,
                providers=req.providers,
                fallback_rules=req.fallback_rules,
                metadata=req.metadata,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Validate business rules
        issues = validate_chain(chain)
        if issues:
            raise HTTPException(status_code=400, detail={"validation_errors": issues})

        chain_id = uuid.uuid4().hex[:12]
        _chains[chain_id] = chain
        return MessageResponse(
            message="Chain created",
            detail={"chain_id": chain_id, "name": chain.name, "providers": len(chain.providers)},
        )

    @app.get("/chains", tags=["chains"])
    async def list_chains():
        """List all stored chains."""
        return [
            {
                "chain_id": cid,
                "name": chain.name,
                "providers": len(chain.providers),
                "fallback_rules": len(chain.fallback_rules),
            }
            for cid, chain in _chains.items()
        ]

    @app.get("/chains/{chain_id}", tags=["chains"])
    async def get_chain(chain_id: str):
        """Get a chain by ID."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None
        return chain.model_dump()

    @app.patch("/chains/{chain_id}", response_model=MessageResponse, tags=["chains"])
    async def update_chain(chain_id: str, req: ChainUpdateRequest):
        """Partially update a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        if req.name is not None:
            chain.name = req.name
        if req.providers is not None:
            chain.providers = req.providers
        if req.fallback_rules is not None:
            chain.fallback_rules = req.fallback_rules
        if req.metadata is not None:
            chain.metadata = req.metadata

        # Re-validate after patch
        issues = validate_chain(chain)
        if issues:
            raise HTTPException(status_code=400, detail={"validation_errors": issues})

        _storage.update(chain_id, chain)
        return MessageResponse(message="Chain updated", detail={"chain_id": chain_id})

    @app.delete("/chains/{chain_id}", response_model=MessageResponse, tags=["chains"])
    async def delete_chain(chain_id: str):
        """Delete a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        name = chain.name
        _storage.delete(chain_id)
        return MessageResponse(message="Chain deleted", detail={"chain_id": chain_id, "name": name})

    # ------------------------------------------------------------------
    # Chain analysis
    # ------------------------------------------------------------------
    @app.get("/chains/{chain_id}/routing", response_model=RoutingResponse, tags=["chains"])
    async def get_routing(chain_id: str):
        """Get the routing table for a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        routing = build_routing_chain(chain)
        return RoutingResponse(chain_id=chain_id, chain_name=chain.name, routing=routing)

    @app.get("/chains/{chain_id}/summary", response_model=SummaryResponse, tags=["chains"])
    async def get_summary(chain_id: str):
        """Get a human-readable summary of a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        summary = generate_chain_summary(chain)
        return SummaryResponse(chain_id=chain_id, chain_name=chain.name, summary=summary)

    @app.get(
        "/chains/{chain_id}/validate",
        tags=["chains"],
    )
    async def validate_chain_endpoint(chain_id: str):
        """Validate a chain and return any issues."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        issues = validate_chain(chain)
        return {"chain_id": chain_id, "valid": len(issues) == 0, "issues": issues}

    @app.post(
        "/chains/{chain_id}/optimize",
        response_model=OptimizationResponse,
        tags=["chains"],
    )
    async def optimize_chain(chain_id: str):
        """Optimize the provider order in a chain based on latency and success rates."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        optimized = optimize_chain_order(chain)
        _storage.update(chain_id, optimized)
        return OptimizationResponse(
            chain_id=chain_id,
            original_name=chain.name,
            optimized_chain=optimized,
        )

    @app.post(
        "/chains/{chain_id}/apply-rules",
        tags=["chains"],
    )
    async def apply_rules(chain_id: str):
        """Apply fallback rules to a chain and return the resolved routing."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        resolved = apply_fallback_rules(chain, chain.fallback_rules)
        return {"chain_id": chain_id, "resolved_rules": resolved}

    # ------------------------------------------------------------------
    # Testing
    # ------------------------------------------------------------------
    @app.post("/chains/{chain_id}/test", response_model=ChainReport, tags=["testing"])
    async def test_chain(chain_id: str, req: TestRequest):
        """Run simulated tests against a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        if req.seed is not None:
            import random

            random.seed(req.seed)

        sim = Simulator(chain, req.outages)
        test_prompts = generate_test_prompts(req.prompts)
        report = await sim.run_batch(test_prompts)
        return report

    @app.post("/chains/{chain_id}/test-prompt", response_model=PromptResult, tags=["testing"])
    async def test_single_prompt(
        chain_id: str,
        prompt: str = Query(..., description="Prompt text to test"),
        category: str = Query(default="general", description="Prompt category"),
    ):
        """Test a single prompt against a chain."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        sim = Simulator(chain)
        spec = PromptSpec(prompt=prompt, category=category)
        result = await sim.run_prompt(spec)
        return result

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    @app.post("/chains/{chain_id}/export", tags=["export"])
    async def export_chain(chain_id: str, req: ExportRequest):
        """Export a chain in the specified format."""
        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        if req.format == ExportFormat.LITELLM:
            return {"format": "litellm", "config": export_litellm(chain)}
        elif req.format == ExportFormat.OPENROUTER:
            return {"format": "openrouter", "config": export_openrouter(chain)}
        elif req.format == ExportFormat.LANGCHAIN:
            return {"format": "langchain", "config": export_langchain(chain)}
        elif req.format == ExportFormat.HAYSTACK:
            return {"format": "haystack", "config": export_haystack(chain)}
        else:
            return {"format": "custom", "config": export_custom(chain)}

    @app.post("/chains/{chain_id}/export-template", tags=["export"])
    async def export_chain_template(chain_id: str, req: TemplateExportRequest):
        """Export a chain using a Jinja2 template."""
        import jinja2 as _jinja2

        from .template_export import (
            BUILTIN_TEMPLATES,
            render_template,
            render_template_file,
        )

        try:
            chain = _storage.get(chain_id)
        except ChainNotFoundError:
            raise HTTPException(status_code=404, detail="Chain not found") from None

        if req.builtin_template:
            if req.builtin_template not in BUILTIN_TEMPLATES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown template: {req.builtin_template}. "
                    f"Available: {', '.join(BUILTIN_TEMPLATES.keys())}",
                )
            result = render_template(
                chain,
                BUILTIN_TEMPLATES[req.builtin_template],
                extra_vars=req.extra_vars or None,
            )
        elif req.template:
            try:
                result = render_template(chain, req.template, extra_vars=req.extra_vars or None)
            except _jinja2.UndefinedError as exc:
                raise HTTPException(status_code=400, detail=f"Template error: {exc}") from exc
        elif req.template_file:
            try:
                result = render_template_file(
                    chain, req.template_file, extra_vars=req.extra_vars or None
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide one of: template, template_file, or builtin_template",
            )

        return {
            "format": "template",
            "builtin_template": req.builtin_template,
            "output": result,
        }

    # ------------------------------------------------------------------
    # Import from file
    # ------------------------------------------------------------------
    @app.post("/chains/import", response_model=MessageResponse, status_code=201, tags=["chains"])
    async def import_chain_from_file(
        path: str = Query(..., description="Path to chain YAML/JSON config file"),
    ):
        """Import a chain from a YAML or JSON file."""
        try:
            chain = load_chain(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        chain_id = uuid.uuid4().hex[:12]
        _chains[chain_id] = chain
        return MessageResponse(
            message="Chain imported",
            detail={"chain_id": chain_id, "name": chain.name, "providers": len(chain.providers)},
        )

    @app.post(
        "/chains/import-outages",
        tags=["testing"],
    )
    async def import_outages_from_file(
        path: str = Query(..., description="Path to outage YAML/JSON config file"),
    ):
        """Import outage scenarios from a file."""
        try:
            outages = load_outage_scenario(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {"outages": [o.model_dump() for o in outages], "count": len(outages)}

    # ------------------------------------------------------------------
    # WebSocket endpoints
    # ------------------------------------------------------------------
    from .websocket import (
        get_manager,
    )

    manager = get_manager()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        """General WebSocket endpoint — receives all broadcast events."""
        await manager.connect(ws)
        try:
            while True:
                # Keep connection alive; client can send pings
                data = await ws.receive_text()
                # Echo pings back
                if data == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(ws)

    @app.websocket("/ws/chain/{chain_id}")
    async def websocket_chain_endpoint(ws: WebSocket, chain_id: str):
        """Channel-specific WebSocket — events for a specific chain."""
        channel = f"chain:{chain_id}"
        await manager.connect(ws, channel=channel)
        try:
            while True:
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(ws)

    # Broadcast chain lifecycle events via WebSocket
    _orig_create = _register_routes  # reference for chaining if needed


# Hook chain lifecycle events to broadcast via WebSocket
_original_create_chain = None
_original_update_chain = None
_original_delete_chain = None


def _install_ws_hooks(app: FastAPI) -> None:
    """Patch route handlers to broadcast chain lifecycle events via WebSocket.

    This is called from _register_routes after routes are defined.
    """
    from .websocket import (
        get_manager,
    )

    manager = get_manager()


def _broadcast_chain_event(
    event_type: str, chain_id: str, data: dict[str, Any] | None = None
) -> None:
    """Fire-and-forget broadcast of a chain lifecycle event."""
    import asyncio

    from .websocket import get_manager, make_event

    manager = get_manager()
    event = make_event(event_type, data=data, chain_id=chain_id)
    channel = f"chain:{chain_id}"

    # Try to broadcast; if no event loop (sync context), skip silently
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast(event, channel=channel))
    except RuntimeError:
        pass  # No event loop — can't broadcast from sync context


# ---------------------------------------------------------------------------
# Module-level app instance for `uvicorn fallbackrabbit.server:app`
# ---------------------------------------------------------------------------

app = create_app()

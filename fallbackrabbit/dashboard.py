"""Web dashboard for FallbackRabbit — polished SPA for chain management and test visualization."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ---------------------------------------------------------------------------
# Load dashboard HTML from adjacent file (keeps Python source readable)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML: str | None = None


def _load_dashboard_html() -> str:
    """Load and cache the dashboard HTML from dashboard.html."""
    global _DASHBOARD_HTML
    if _DASHBOARD_HTML is None:
        html_path = Path(__file__).parent / "dashboard.html"
        _DASHBOARD_HTML = html_path.read_text(encoding="utf-8")
    return _DASHBOARD_HTML


# Backward-compatible module-level constant (lazy-loaded on first access)
class _DashboardHTMLDescriptor:
    """Descriptor that lazy-loads HTML on first attribute access."""
    def __get__(self, obj, objtype=None) -> str:
        return _load_dashboard_html()


class _DashboardModule:
    """Module proxy to support both DASHBOARD_HTML constant and function access."""
    pass


DASHBOARD_HTML = _load_dashboard_html()  # Eager load for backward compat


def get_dashboard_html() -> str:
    """Return the dashboard HTML string."""
    return _load_dashboard_html()


def mount_dashboard(app: FastAPI, *, prefix: str = "/dashboard") -> None:
    """Mount the dashboard UI on a FastAPI app.

    Args:
        app: FastAPI application.
        prefix: URL prefix for the dashboard. Defaults to /dashboard.
    """

    @app.get(prefix, response_class=HTMLResponse, tags=["dashboard"])
    async def dashboard_page():
        """Serve the FallbackRabbit dashboard UI."""
        return HTMLResponse(content=get_dashboard_html())

    @app.get(f"{prefix}/", response_class=HTMLResponse, tags=["dashboard"])
    async def dashboard_page_slash():
        """Serve the dashboard UI (trailing slash)."""
        return HTMLResponse(content=get_dashboard_html())
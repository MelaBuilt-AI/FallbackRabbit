"""Tests for FallbackRabbit web dashboard — HTML serving, endpoints, content validation."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fallbackrabbit.dashboard import DASHBOARD_HTML, get_dashboard_html, mount_dashboard
from fallbackrabbit.server import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_dashboard():
    """App with dashboard mounted."""
    return create_app(storage_url="memory")


@pytest.fixture
def client_with_dashboard(app_with_dashboard):
    return TestClient(app_with_dashboard)


# ===========================================================================
# Dashboard HTML content tests
# ===========================================================================


class TestDashboardHTML:
    """Tests for the dashboard HTML content."""

    def test_html_not_empty(self):
        assert len(DASHBOARD_HTML) > 100

    def test_html_has_title(self):
        assert "<title>FallbackRabbit Dashboard</title>" in DASHBOARD_HTML

    def test_html_has_sidebar(self):
        assert "sidebar" in DASHBOARD_HTML

    def test_html_has_overview_page(self):
        assert "Overview" in DASHBOARD_HTML

    def test_html_has_chains_page(self):
        assert "Chains" in DASHBOARD_HTML

    def test_html_has_test_page(self):
        assert "Test Runner" in DASHBOARD_HTML

    def test_html_has_export_page(self):
        assert "Export" in DASHBOARD_HTML

    def test_html_has_websocket(self):
        assert "WebSocket" in DASHBOARD_HTML or "new WebSocket" in DASHBOARD_HTML

    def test_html_has_api_fetch(self):
        assert "fetch(" in DASHBOARD_HTML

    def test_html_has_dark_theme(self):
        assert "--bg" in DASHBOARD_HTML

    def test_get_dashboard_html_returns_content(self):
        html = get_dashboard_html()
        assert html == DASHBOARD_HTML


# ===========================================================================
# Dashboard endpoint tests
# ===========================================================================


class TestDashboardEndpoints:
    """Tests for dashboard HTTP endpoints."""

    def test_dashboard_returns_html(self, client_with_dashboard):
        """GET /dashboard returns HTML."""
        resp = client_with_dashboard.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_dashboard_trailing_slash(self, client_with_dashboard):
        """GET /dashboard/ also returns HTML."""
        resp = client_with_dashboard.get("/dashboard/")
        assert resp.status_code == 200

    def test_dashboard_contains_title(self, client_with_dashboard):
        """Dashboard HTML has the correct title."""
        resp = client_with_dashboard.get("/dashboard")
        assert "FallbackRabbit" in resp.text

    def test_dashboard_has_js(self, client_with_dashboard):
        """Dashboard HTML includes JavaScript."""
        resp = client_with_dashboard.get("/dashboard")
        assert "<script>" in resp.text

    def test_dashboard_has_css(self, client_with_dashboard):
        """Dashboard HTML includes CSS styles."""
        resp = client_with_dashboard.get("/dashboard")
        assert "<style>" in resp.text

    def test_dashboard_not_404(self, client_with_dashboard):
        """Dashboard endpoint exists (not 404)."""
        resp = client_with_dashboard.get("/dashboard")
        assert resp.status_code != 404


# ===========================================================================
# mount_dashboard tests
# ===========================================================================


class TestMountDashboard:
    """Tests for the mount_dashboard function."""

    def test_mount_on_bare_app(self):
        """mount_dashboard works on a minimal FastAPI app."""
        app = FastAPI()
        mount_dashboard(app)
        client = TestClient(app)
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_mount_with_custom_prefix(self):
        """mount_dashboard respects custom prefix."""
        app = FastAPI()
        mount_dashboard(app, prefix="/ui")
        client = TestClient(app)
        resp = client.get("/ui")
        assert resp.status_code == 200

    def test_custom_prefix_trailing_slash(self):
        """Custom prefix with trailing slash."""
        app = FastAPI()
        mount_dashboard(app, prefix="/ui")
        client = TestClient(app)
        resp = client.get("/ui/")
        assert resp.status_code == 200

    def test_default_prefix_not_found_without_mount(self):
        """Without mount_dashboard, /dashboard is 404."""
        app = FastAPI()
        client = TestClient(app)
        resp = client.get("/dashboard")
        assert resp.status_code == 404

    def test_routes_registered(self):
        """Dashboard routes appear in app routes."""
        app = FastAPI()
        mount_dashboard(app)
        paths = [r.path for r in app.routes]
        assert "/dashboard" in paths
        assert "/dashboard/" in paths


# ===========================================================================
# Integration: dashboard + API
# ===========================================================================


class TestDashboardWithAPI:
    """Tests that the dashboard and REST API coexist properly."""

    def test_api_still_works(self, client_with_dashboard):
        """REST API endpoints still work after mounting dashboard."""
        resp = client_with_dashboard.get("/health")
        assert resp.status_code == 200

    def test_chains_endpoint_works(self, client_with_dashboard):
        """Chains API endpoint works alongside dashboard."""
        resp = client_with_dashboard.get("/chains")
        assert resp.status_code == 200

    def test_create_and_list(self, client_with_dashboard):
        """Create a chain and verify it appears in the API."""
        payload = {
            "name": "dashboard-test",
            "providers": [
                {
                    "name": "GPT-4",
                    "model_id": "gpt-4",
                    "api_base": "https://api.openai.com/v1",
                    "priority": 0,
                },
            ],
        }
        resp = client_with_dashboard.post("/chains", json=payload)
        assert resp.status_code == 201

        list_resp = client_with_dashboard.get("/chains")
        assert list_resp.status_code == 200
        chains = list_resp.json()
        assert any(c["name"] == "dashboard-test" for c in chains)

    def test_dashboard_and_docs_coexist(self, client_with_dashboard):
        """Both /dashboard and /docs are accessible."""
        dash = client_with_dashboard.get("/dashboard")
        docs = client_with_dashboard.get("/docs")
        assert dash.status_code == 200
        assert docs.status_code == 200

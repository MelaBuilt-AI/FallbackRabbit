"""Tests for FallbackRabbit WebSocket support — connection manager, events, progress tracking."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from fallbackrabbit.models import Chain, Provider
from fallbackrabbit.simulator import Simulator
from fallbackrabbit.websocket import (
    EVENT_CHAIN_CREATED,
    EVENT_CHAIN_DELETED,
    EVENT_CHAIN_UPDATED,
    EVENT_ERROR,
    EVENT_TEST_COMPLETE,
    EVENT_TEST_PROGRESS,
    EVENT_TEST_START,
    ConnectionManager,
    make_event,
    set_manager,
)
from fallbackrabbit.websocket import (
    ProgressTracker as TestProgressTracker,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    """Fresh ConnectionManager for each test."""
    m = ConnectionManager()
    set_manager(m)
    yield m
    m.clear()
    set_manager(None)


@pytest.fixture
def app_with_ws(manager):
    """FastAPI app with WebSocket endpoints."""
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_general(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except Exception:
            manager.disconnect(websocket)

    @app.websocket("/ws/chain/{chain_id}")
    async def ws_chain(websocket: WebSocket, chain_id: str):
        channel = f"chain:{chain_id}"
        await manager.connect(websocket, channel=channel)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except Exception:
            manager.disconnect(websocket)

    return app


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Unit tests for ConnectionManager."""

    def test_init(self, manager):
        assert manager.active_count == 0
        assert manager.channels == []

    def test_connect_and_disconnect(self, manager):
        """Test basic connect/disconnect without a real WS (mock)."""
        ws = MagicMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()

        # We can't fully test connect without an actual WS handshake,
        # but we can test the bookkeeping
        manager._connections.append(ws)
        assert manager.active_count == 1

        manager.disconnect(ws)
        assert manager.active_count == 0

    def test_channel_subscribe(self, manager):
        """Test channel subscription bookkeeping."""
        ws1 = MagicMock(spec=WebSocket)
        ws2 = MagicMock(spec=WebSocket)

        manager._channels["chain:abc"] = [ws1, ws2]
        manager._channels["tests"] = [ws1]

        assert "chain:abc" in manager.channels
        assert "tests" in manager.channels
        assert len(manager._channels["chain:abc"]) == 2

    def test_channel_unsubscribe(self, manager):
        """Test removing a WS from a specific channel."""
        ws1 = MagicMock(spec=WebSocket)
        ws2 = MagicMock(spec=WebSocket)

        manager._channels["chain:abc"] = [ws1, ws2]
        manager.disconnect(ws1)

        assert ws2 in manager._channels["chain:abc"]
        assert ws1 not in manager._channels["chain:abc"]

    def test_empty_channel_cleanup(self, manager):
        """Empty channels are automatically cleaned up."""
        ws = MagicMock(spec=WebSocket)
        manager._channels["chain:xyz"] = [ws]
        manager.disconnect(ws)

        assert "chain:xyz" not in manager.channels

    def test_clear(self, manager):
        """Clear resets all state."""
        ws = MagicMock(spec=WebSocket)
        manager._connections.append(ws)
        manager._channels["test"] = [ws]

        manager.clear()
        assert manager.active_count == 0
        assert manager.channels == []

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, manager):
        """Broadcast sends to all connections."""
        ws1 = MagicMock(spec=WebSocket)
        ws1.send_text = AsyncMock()
        ws2 = MagicMock(spec=WebSocket)
        ws2.send_text = AsyncMock()

        manager._connections = [ws1, ws2]
        event = make_event("test", data={"msg": "hello"})

        await manager.broadcast(event)

        ws1.send_text.assert_called_once_with(json.dumps(event))
        ws2.send_text.assert_called_once_with(json.dumps(event))

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self, manager):
        """Channel broadcast only reaches channel subscribers."""
        ws_global = MagicMock(spec=WebSocket)
        ws_global.send_text = AsyncMock()
        ws_channel = MagicMock(spec=WebSocket)
        ws_channel.send_text = AsyncMock()

        manager._connections = [ws_global]
        manager._channels["chain:abc"] = [ws_channel]

        event = make_event("test", data={"msg": "hello"})

        await manager.broadcast(event, channel="chain:abc")

        ws_channel.send_text.assert_called_once()
        ws_global.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, manager):
        """Dead connections are automatically removed on broadcast failure."""
        ws_alive = MagicMock(spec=WebSocket)
        ws_alive.send_text = AsyncMock()
        ws_dead = MagicMock(spec=WebSocket)
        ws_dead.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        manager._connections = [ws_alive, ws_dead]

        await manager.broadcast(make_event("test"))

        assert manager.active_count == 1
        assert ws_alive in manager._connections
        assert ws_dead not in manager._connections


# ---------------------------------------------------------------------------
# make_event tests
# ---------------------------------------------------------------------------


class TestMakeEvent:
    """Tests for the make_event helper."""

    def test_basic_event(self):
        event = make_event("test_type")
        assert event["type"] == "test_type"
        assert "timestamp" in event
        assert abs(event["timestamp"] - time.time()) < 1

    def test_event_with_data(self):
        event = make_event("test", data={"key": "value"})
        assert event["data"] == {"key": "value"}

    def test_event_with_chain_id(self):
        event = make_event("test", chain_id="abc123")
        assert event["chain_id"] == "abc123"

    def test_event_no_optional_fields(self):
        event = make_event("test")
        assert "data" not in event
        assert "chain_id" not in event

    def test_event_all_fields(self):
        event = make_event("test", data={"x": 1}, chain_id="cid")
        assert event["type"] == "test"
        assert event["data"] == {"x": 1}
        assert event["chain_id"] == "cid"
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------


class TestEventConstants:
    """Verify event constant values."""

    def test_event_names(self):
        assert EVENT_TEST_START == "test_start"
        assert EVENT_TEST_PROGRESS == "test_progress"
        assert EVENT_TEST_COMPLETE == "test_complete"
        assert EVENT_CHAIN_CREATED == "chain_created"
        assert EVENT_CHAIN_UPDATED == "chain_updated"
        assert EVENT_CHAIN_DELETED == "chain_deleted"
        assert EVENT_ERROR == "error"


# ---------------------------------------------------------------------------
# TestProgressTracker tests
# ---------------------------------------------------------------------------


class TestTestProgressTracker:
    """Tests for the WebSocket test progress tracker."""

    @pytest.fixture
    def sample_chain(self):
        return Chain(
            name="Test Chain",
            providers=[
                Provider(
                    name="gpt-4", model_id="gpt-4", api_base="https://api.openai.com/v1", priority=1
                ),
                Provider(
                    name="claude",
                    model_id="claude-3-opus",
                    api_base="https://api.anthropic.com",
                    priority=2,
                ),
            ],
        )

    @pytest.fixture
    def simulator(self, sample_chain):
        return Simulator(sample_chain)

    @pytest.mark.asyncio
    async def test_tracker_broadcasts_start(self, manager, simulator):
        """Tracker emits test_start event."""
        tracker = TestProgressTracker(manager)
        received = []

        # Monkey-patch broadcast to capture events
        # Monkey-patch broadcast to capture events

        async def capture_broadcast(event, channel=None):
            received.append((event, channel))

        manager.broadcast = capture_broadcast

        await tracker.run_and_track(
            simulator,
            "chain123",
            ["Hello world"],
        )

        # First event should be test_start
        assert len(received) >= 1
        assert received[0][0]["type"] == EVENT_TEST_START
        assert received[0][0]["chain_id"] == "chain123"
        assert received[0][0]["data"]["total_prompts"] == 1

    @pytest.mark.asyncio
    async def test_tracker_broadcasts_progress(self, manager, simulator):
        """Tracker emits test_progress events for each prompt."""
        tracker = TestProgressTracker(manager)
        received = []

        async def capture_broadcast(event, channel=None):
            received.append(event)

        manager.broadcast = capture_broadcast

        await tracker.run_and_track(
            simulator,
            "chain123",
            ["Prompt 1", "Prompt 2"],
        )

        # Should have: start, 2x progress, complete
        types = [e["type"] for e in received]
        assert types[0] == EVENT_TEST_START
        assert types.count(EVENT_TEST_PROGRESS) == 2
        assert types[-1] == EVENT_TEST_COMPLETE

    @pytest.mark.asyncio
    async def test_tracker_broadcasts_complete(self, manager, simulator):
        """Tracker emits test_complete event with summary."""
        tracker = TestProgressTracker(manager)
        received = []

        async def capture_broadcast(event, channel=None):
            received.append(event)

        manager.broadcast = capture_broadcast

        await tracker.run_and_track(
            simulator,
            "chain123",
            ["Prompt 1"],
        )

        complete_events = [e for e in received if e["type"] == EVENT_TEST_COMPLETE]
        assert len(complete_events) == 1
        assert complete_events[0]["data"]["total"] == 1
        assert "successful" in complete_events[0]["data"]
        assert "failed" in complete_events[0]["data"]

    @pytest.mark.asyncio
    async def test_tracker_channel_routing(self, manager, simulator):
        """Events are broadcast to the correct chain channel."""
        tracker = TestProgressTracker(manager)
        channels = []

        async def capture_broadcast(event, channel=None):
            channels.append(channel)

        manager.broadcast = capture_broadcast

        await tracker.run_and_track(
            simulator,
            "abc123",
            ["test"],
        )

        # All events should target chain:abc123
        for ch in channels:
            assert ch == "chain:abc123"

    @pytest.mark.asyncio
    async def test_tracker_handles_errors(self, manager, simulator):
        """Tracker emits error events for failed prompts without stopping."""
        tracker = TestProgressTracker(manager)
        received = []

        async def capture_broadcast(event, channel=None):
            received.append(event)

        manager.broadcast = capture_broadcast

        # Make run_prompt fail on first call
        original_run = simulator.run_prompt
        call_count = 0

        async def failing_run(spec, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API timeout")
            return await original_run(spec, **kwargs)

        simulator.run_prompt = failing_run

        await tracker.run_and_track(
            simulator,
            "chain123",
            ["Prompt 1", "Prompt 2"],
        )

        types = [e["type"] for e in received]
        assert EVENT_ERROR in types
        # Still got start + progress (for successful prompt) + complete
        assert EVENT_TEST_START in types
        assert EVENT_TEST_COMPLETE in types

    @pytest.mark.asyncio
    async def test_tracker_empty_prompts(self, manager, simulator):
        """Tracker handles empty prompt list gracefully."""
        tracker = TestProgressTracker(manager)
        received = []

        async def capture_broadcast(event, channel=None):
            received.append(event)

        manager.broadcast = capture_broadcast

        await tracker.run_and_track(
            simulator,
            "chain123",
            [],
        )

        # Should get start + complete (0 prompts)
        types = [e["type"] for e in received]
        assert EVENT_TEST_START in types
        assert EVENT_TEST_COMPLETE in types
        complete = [e for e in received if e["type"] == EVENT_TEST_COMPLETE][0]
        assert complete["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_tracker_returns_results(self, manager, simulator):
        """Tracker returns results list from simulation."""
        tracker = TestProgressTracker(manager)

        async def noop_broadcast(event, channel=None):
            pass

        manager.broadcast = noop_broadcast

        results = await tracker.run_and_track(
            simulator,
            "chain123",
            ["test1", "test2", "test3"],
        )

        assert len(results) == 3
        for r in results:
            assert isinstance(r, dict)


# ---------------------------------------------------------------------------
# WebSocket endpoint integration tests (using TestClient)
# ---------------------------------------------------------------------------


class TestWebSocketEndpoints:
    """Integration tests for WebSocket endpoints via TestClient."""

    def test_general_ws_connect(self, app_with_ws):
        """General WebSocket endpoint accepts connections."""
        client = TestClient(app_with_ws)
        with client.websocket_connect("/ws") as ws:
            ws.send_text("ping")
            response = ws.receive_text()
            assert response == "pong"

    def test_chain_ws_connect(self, app_with_ws):
        """Chain-specific WebSocket endpoint accepts connections."""
        client = TestClient(app_with_ws)
        with client.websocket_connect("/ws/chain/abc123") as ws:
            ws.send_text("ping")
            response = ws.receive_text()
            assert response == "pong"

    def test_general_ws_disconnect(self, app_with_ws, manager):
        """Disconnection cleans up the connection manager."""
        client = TestClient(app_with_ws)
        with client.websocket_connect("/ws") as ws:
            assert manager.active_count >= 1
        # After disconnect
        assert manager.active_count == 0

    def test_chain_ws_disconnect(self, app_with_ws, manager):
        """Chain WebSocket disconnection cleans up channels."""
        client = TestClient(app_with_ws)
        with client.websocket_connect("/ws/chain/testchain") as ws:
            pass
        # Channel should be cleaned up after disconnect
        # Note: TestClient may not perfectly clean up, but the channel list should not grow
        assert (
            "chain:testchain" not in manager.channels
            or len(manager._channels.get("chain:testchain", [])) == 0
        )

    def test_multiple_connections(self, app_with_ws, manager):
        """Multiple WebSocket connections are tracked."""
        client = TestClient(app_with_ws)
        with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
            assert manager.active_count >= 2

    def test_ws_receives_broadcast(self, app_with_ws, manager):
        """WebSocket client receives broadcast events."""
        client = TestClient(app_with_ws)

        with client.websocket_connect("/ws") as ws:
            # Send a broadcast from the manager
            event = make_event("test_event", data={"msg": "hello ws"})

            # Use asyncio to broadcast
            import asyncio

            loop = asyncio.new_event_loop()
            loop.run_until_complete(manager.broadcast(event))
            loop.close()

            response = ws.receive_text()
            parsed = json.loads(response)
            assert parsed["type"] == "test_event"
            assert parsed["data"]["msg"] == "hello ws"


# ---------------------------------------------------------------------------
# Broadcast helper tests
# ---------------------------------------------------------------------------


class TestBroadcastHelper:
    """Tests for the _broadcast_chain_event helper."""

    def test_broadcast_chain_event_no_loop(self):
        """_broadcast_chain_event skips silently when no event loop exists."""
        from fallbackrabbit.server import _broadcast_chain_event

        # Calling from sync context (no event loop) should not raise
        _broadcast_chain_event(EVENT_CHAIN_CREATED, "chain123", {"name": "test"})

    @pytest.mark.asyncio
    async def test_broadcast_chain_event_with_loop(self, manager):
        """_broadcast_chain_event broadcasts when an event loop exists."""
        from fallbackrabbit.server import _broadcast_chain_event

        received = []

        async def capture(event, channel=None):
            received.append(event)

        manager.broadcast = capture

        # _broadcast_chain_event is sync, creates task via loop
        _broadcast_chain_event(EVENT_CHAIN_CREATED, "chain123", {"name": "test"})

        # Give the created task a chance to run
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["type"] == EVENT_CHAIN_CREATED
        assert received[0]["chain_id"] == "chain123"


# ---------------------------------------------------------------------------
# Full-stack WebSocket + server test
# ---------------------------------------------------------------------------


class TestWebSocketFullStack:
    """Full-stack tests with the FallbackRabbit server + WebSocket."""

    @pytest.fixture
    def client_app(self):
        """Create a FallbackRabbit app with WebSocket support."""
        from fallbackrabbit.server import create_app

        app = create_app()
        return app

    def test_ws_endpoint_exists(self, client_app):
        """WebSocket /ws endpoint is registered."""
        routes = [r.path for r in client_app.routes]
        assert "/ws" in routes

    def test_ws_chain_endpoint_exists(self, client_app):
        """WebSocket /ws/chain/{chain_id} endpoint is registered."""
        routes = [r.path for r in client_app.routes]
        assert "/ws/chain/{chain_id}" in routes

    def test_ws_ping_pong(self, client_app):
        """WebSocket ping/pong works on the full server."""
        client = TestClient(client_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_text("ping")
            response = ws.receive_text()
            assert response == "pong"

    def test_ws_chain_ping_pong(self, client_app):
        """Chain WebSocket ping/pong works."""
        client = TestClient(client_app)
        with client.websocket_connect("/ws/chain/abc123") as ws:
            ws.send_text("ping")
            response = ws.receive_text()
            assert response == "pong"

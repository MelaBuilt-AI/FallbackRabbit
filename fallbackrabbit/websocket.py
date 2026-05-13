"""WebSocket support for FallbackRabbit — real-time test progress and chain events."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import WebSocket

# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._channels: dict[str, list[WebSocket]] = {}  # channel → connections

    async def connect(self, ws: WebSocket, channel: str | None = None) -> None:
        """Accept and register a WebSocket connection.

        Args:
            ws: The WebSocket connection.
            channel: Optional channel name (e.g. 'chain:abc123' or 'tests').
        """
        await ws.accept()
        self._connections.append(ws)
        if channel:
            if channel not in self._channels:
                self._channels[channel] = []
            self._channels[channel].append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection from all channels."""
        if ws in self._connections:
            self._connections.remove(ws)
        for chan_conns in self._channels.values():
            if ws in chan_conns:
                chan_conns.remove(ws)
        # Clean up empty channels
        self._channels = {k: v for k, v in self._channels.items() if v}

    async def broadcast(self, event: dict[str, Any], channel: str | None = None) -> None:
        """Broadcast an event to all connections, or a specific channel.

        Args:
            event: Event payload dict.
            channel: Optional channel to target. None = broadcast to all.
        """
        payload = json.dumps(event)
        targets = self._channels.get(channel, self._connections) if channel else self._connections
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

    @property
    def channels(self) -> list[str]:
        """Active channel names."""
        return list(self._channels.keys())

    def clear(self) -> None:
        """Reset all connections (for testing)."""
        self._connections.clear()
        self._channels.clear()


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


def make_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Create a standard WebSocket event payload.

    Args:
        event_type: Event type string (e.g. 'test_start', 'test_progress', 'test_complete').
        data: Optional event-specific data.
        chain_id: Optional chain ID for routing.

    Returns:
        Event dict with type, timestamp, and optional data/chain_id.
    """
    event: dict[str, Any] = {
        "type": event_type,
        "timestamp": time.time(),
    }
    if data:
        event["data"] = data
    if chain_id:
        event["chain_id"] = chain_id
    return event


# ---------------------------------------------------------------------------
# Event names (constants)
# ---------------------------------------------------------------------------

EVENT_TEST_START = "test_start"
EVENT_TEST_PROGRESS = "test_progress"
EVENT_TEST_COMPLETE = "test_complete"
EVENT_CHAIN_CREATED = "chain_created"
EVENT_CHAIN_UPDATED = "chain_updated"
EVENT_CHAIN_DELETED = "chain_deleted"
EVENT_ERROR = "error"


# ---------------------------------------------------------------------------
# WebSocket test progress tracker
# ---------------------------------------------------------------------------


class ProgressTracker:
    """Tracks test execution progress and broadcasts via WebSocket.

    Wraps the Simulator's run methods to emit real-time progress events
    as each prompt is tested.
    """

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    async def run_and_track(
        self,
        simulator: Any,
        chain_id: str,
        prompts: list[str],
        *,
        outages: list[Any] | None = None,
        use_real_calls: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a simulation with real-time WebSocket progress updates.

        Args:
            simulator: Simulator instance.
            chain_id: Chain being tested.
            prompts: List of test prompts.
            outages: Optional outage scenarios.
            use_real_calls: Whether to use real API calls.

        Returns:
            List of PromptResult dicts.
        """
        channel = f"chain:{chain_id}"
        total = len(prompts)
        results: list[dict[str, Any]] = []

        # Broadcast start
        await self._manager.broadcast(
            make_event(
                EVENT_TEST_START,
                data={"total_prompts": total, "chain_id": chain_id},
                chain_id=chain_id,
            ),
            channel=channel,
        )

        for i, prompt in enumerate(prompts, 1):
            try:
                spec = type("PromptSpec", (), {"text": prompt})()  # Simple spec
                if use_real_calls:
                    result = await simulator.run_prompt(spec, use_real_calls=True)
                else:
                    result = await simulator.run_prompt(spec)

                result_dict = result.model_dump() if hasattr(result, "model_dump") else result
                results.append(result_dict)

                # Broadcast progress
                await self._manager.broadcast(
                    make_event(
                        EVENT_TEST_PROGRESS,
                        data={
                            "current": i,
                            "total": total,
                            "prompt": prompt[:100],  # Truncate long prompts
                            "provider": result_dict.get("provider", "unknown"),
                            "success": result_dict.get("success", False),
                            "latency_ms": result_dict.get("latency_ms", 0),
                        },
                        chain_id=chain_id,
                    ),
                    channel=channel,
                )
            except Exception as exc:
                # Broadcast error for this prompt but continue
                await self._manager.broadcast(
                    make_event(
                        EVENT_ERROR,
                        data={"prompt_index": i, "error": str(exc)},
                        chain_id=chain_id,
                    ),
                    channel=channel,
                )

        # Broadcast completion
        successful = sum(1 for r in results if r.get("success", False))
        await self._manager.broadcast(
            make_event(
                EVENT_TEST_COMPLETE,
                data={
                    "total": total,
                    "successful": successful,
                    "failed": total - successful,
                    "chain_id": chain_id,
                },
                chain_id=chain_id,
            ),
            channel=channel,
        )

        return results


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: ConnectionManager | None = None


def get_manager() -> ConnectionManager:
    """Get or create the global ConnectionManager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


def set_manager(manager: ConnectionManager) -> None:
    """Set the global ConnectionManager (for testing)."""
    global _manager
    _manager = manager

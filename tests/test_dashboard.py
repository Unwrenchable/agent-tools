"""Tests for agent_tools.dashboard."""
from __future__ import annotations

import json
import queue
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from agent_tools.dashboard import (
    DashboardHandler,
    _EventBus,
    _ThreadingHTTPServer,
    build_graph_data,
    serve,
)
from agent_tools.registry import load_agents, load_profiles


# ── build_graph_data ──────────────────────────────────────────────────────────


class TestBuildGraphData:
    def setup_method(self) -> None:
        self.agents = load_agents()
        self.profiles = load_profiles()
        self.data = build_graph_data(self.agents, self.profiles)

    def test_returns_required_keys(self) -> None:
        assert set(self.data.keys()) == {"nodes", "edges", "workflows"}

    def test_nodes_count_matches_agents(self) -> None:
        assert len(self.data["nodes"]) == len(self.agents)

    def test_each_node_has_required_fields(self) -> None:
        required = {"id", "role", "description", "tags", "capabilities", "required_tools",
                    "preferred_profile", "risk_level"}
        for node in self.data["nodes"]:
            assert required.issubset(node.keys()), f"Node {node.get('id')} missing fields"

    def test_edges_are_list(self) -> None:
        assert isinstance(self.data["edges"], list)

    def test_edges_reference_valid_agent_ids(self) -> None:
        ids = {n["id"] for n in self.data["nodes"]}
        for edge in self.data["edges"]:
            assert edge["source"] in ids, f"Unknown source {edge['source']}"
            assert edge["target"] in ids, f"Unknown target {edge['target']}"

    def test_no_self_loops(self) -> None:
        for edge in self.data["edges"]:
            assert edge["source"] != edge["target"]

    def test_no_duplicate_edges(self) -> None:
        seen: set[tuple[str, str]] = set()
        for edge in self.data["edges"]:
            key = (edge["source"], edge["target"])
            assert key not in seen, f"Duplicate edge {key}"
            seen.add(key)

    def test_shared_capabilities_listed_in_edge(self) -> None:
        for edge in self.data["edges"]:
            assert isinstance(edge["shared_capabilities"], list)
            assert isinstance(edge["weight"], int)
            assert edge["weight"] >= 1

    def test_workflows_is_list_of_dicts(self) -> None:
        for wf in self.data["workflows"]:
            assert "name" in wf
            assert "color" in wf
            assert "steps" in wf

    def test_empty_agents_returns_empty_nodes_and_edges(self) -> None:
        result = build_graph_data({}, {})
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_node_risk_levels_are_valid(self) -> None:
        valid = {"low", "medium", "high"}
        for node in self.data["nodes"]:
            assert node["risk_level"] in valid

    def test_node_profiles_are_valid(self) -> None:
        valid = {"safe", "balanced", "power"}
        for node in self.data["nodes"]:
            assert node["preferred_profile"] in valid


# ── _EventBus ─────────────────────────────────────────────────────────────────


class TestEventBus:
    def test_subscribe_returns_queue(self) -> None:
        bus = _EventBus()
        q = bus.subscribe()
        assert isinstance(q, queue.Queue)

    def test_publish_delivers_to_subscriber(self) -> None:
        bus = _EventBus()
        q = bus.subscribe()
        event = {"type": "dispatch", "agent_id": "qa-engineer"}
        bus.publish(event)
        received = q.get_nowait()
        assert received == event

    def test_publish_delivers_to_multiple_subscribers(self) -> None:
        bus = _EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        bus.publish({"type": "test"})
        assert q1.get_nowait()["type"] == "test"
        assert q2.get_nowait()["type"] == "test"

    def test_unsubscribe_removes_queue(self) -> None:
        bus = _EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.publish({"type": "test"})
        assert q.empty()

    def test_unsubscribe_missing_queue_does_not_raise(self) -> None:
        bus = _EventBus()
        q: queue.Queue[dict] = queue.Queue()
        bus.unsubscribe(q)  # should not raise

    def test_full_queue_is_silently_dropped_and_unsubscribed(self) -> None:
        bus = _EventBus()
        q = bus.subscribe()
        # Fill queue to capacity (maxsize=50)
        for _ in range(50):
            q.put_nowait({"type": "fill"})
        # This publish should not raise and should drop the full subscriber
        bus.publish({"type": "overflow"})
        # No exception means the test passes


# ── HTTP server integration ───────────────────────────────────────────────────


def _start_test_server() -> tuple[_ThreadingHTTPServer, int]:
    """Start a dashboard server on an OS-assigned free port and return (server, port)."""
    agents = load_agents()
    profiles = load_profiles()
    graph_data = build_graph_data(agents, profiles)

    server = _ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    server.agents = agents  # type: ignore[attr-defined]
    server.profiles = profiles  # type: ignore[attr-defined]
    server.graph_data = graph_data  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


@pytest.fixture(scope="module")
def dashboard_server():
    server, port = _start_test_server()
    yield port
    server.shutdown()
    server.server_close()


class TestDashboardRoutes:
    def test_root_returns_html(self, dashboard_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", dashboard_server)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        ct = resp.getheader("Content-Type", "")
        assert "text/html" in ct
        body = resp.read()
        assert b"AgentX" in body
        assert b"<!DOCTYPE html>" in body.lower() or b"<!doctype html>" in body.lower()
        conn.close()

    def test_api_agents_returns_json_array(self, dashboard_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", dashboard_server)
        conn.request("GET", "/api/agents")
        resp = conn.getresponse()
        assert resp.status == 200
        assert "application/json" in resp.getheader("Content-Type", "")
        data = json.loads(resp.read())
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]
        conn.close()

    def test_api_profiles_returns_json_array(self, dashboard_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", dashboard_server)
        conn.request("GET", "/api/profiles")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read())
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        conn.close()

    def test_api_graph_returns_nodes_and_edges(self, dashboard_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", dashboard_server)
        conn.request("GET", "/api/graph")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "nodes" in data
        assert "edges" in data
        assert "workflows" in data
        conn.close()

    def test_unknown_route_returns_404(self, dashboard_server: int) -> None:
        conn = HTTPConnection("127.0.0.1", dashboard_server)
        conn.request("GET", "/not-a-real-path")
        resp = conn.getresponse()
        assert resp.status == 404
        conn.close()

    def test_api_events_begins_with_connected(self, dashboard_server: int) -> None:
        import socket as _socket

        s = _socket.create_connection(("127.0.0.1", dashboard_server), timeout=5)
        s.sendall(b"GET /api/events HTTP/1.0\r\nHost: localhost\r\n\r\n")
        data = b""
        s.settimeout(5)
        while b"connected" not in data:
            chunk = s.recv(256)
            if not chunk:
                break
            data += chunk
        s.close()
        assert b"text/event-stream" in data
        assert b"connected" in data

    def test_cors_header_on_json_endpoints(self, dashboard_server: int) -> None:
        for path in ("/api/agents", "/api/profiles", "/api/graph"):
            conn = HTTPConnection("127.0.0.1", dashboard_server)
            conn.request("GET", path)
            resp = conn.getresponse()
            assert resp.getheader("Access-Control-Allow-Origin") == "*", path
            resp.read()
            conn.close()

"""Embedded web dashboard for AgentX.

Visualises the agent registry as a force-directed workflow graph and
streams live simulated agent activity via Server-Sent Events (SSE).

Usage
-----
Start from the CLI::

    agentx serve [--host HOST] [--port PORT]

Or programmatically::

    from agent_tools.dashboard import serve
    serve(host="127.0.0.1", port=7070)
"""
from __future__ import annotations

import json
import queue
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

from .registry import load_agents, load_profiles
from .runtime import ExecutionEvent, get_runtime

# ---------------------------------------------------------------------------
# Activity simulation
# ---------------------------------------------------------------------------

_TASK_DESCRIPTIONS: list[str] = [
    "analysing code structure",
    "reviewing security posture",
    "implementing feature logic",
    "running test suite",
    "auditing dependencies",
    "drafting API schema",
    "optimising database queries",
    "generating documentation",
    "validating access profiles",
    "checking capability alignment",
    "orchestrating sub-agents",
    "reviewing pull request",
    "scanning for vulnerabilities",
    "profiling performance metrics",
    "resolving merge conflicts",
    "updating runbook",
    "designing entity schema",
    "wiring CI pipeline",
    "verifying on-chain transaction",
    "coordinating cross-team handoff",
]


class _EventBus:
    """Thread-safe fan-out event bus for SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[dict]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[dict]:
        q: queue.Queue[dict] = queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict]) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event: dict) -> None:
        with self._lock:
            dead: list[queue.Queue[dict]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass


_bus = _EventBus()
_simulation_enabled = True  # Can be toggled when real executions are active

#: Seconds between consecutive agent dispatch events (min, max).
_MIN_DISPATCH_INTERVAL: float = 1.5
_MAX_DISPATCH_INTERVAL: float = 4.0

#: Simulated task duration range in seconds (min, max).
_MIN_TASK_DURATION: float = 0.8
_MAX_TASK_DURATION: float = 3.5


def _runtime_event_handler(event: ExecutionEvent) -> None:
    """Handle runtime execution events and forward to dashboard bus."""
    # Convert runtime event to dashboard event format
    dashboard_event = {
        "type": event.event_type,
        "agent_id": event.agent_id,
        "ts": event.timestamp.split("T")[1].split(".")[0] if "T" in event.timestamp else event.timestamp,
        **event.data,
    }
    _bus.publish(dashboard_event)


def _simulation_loop(agents: dict) -> None:
    """Randomly dispatch and complete agents to simulate live activity."""
    agent_ids = list(agents.keys())
    while True:
        # Skip simulation if disabled (real executions active)
        if not _simulation_enabled:
            time.sleep(2)
            continue
        time.sleep(random.uniform(_MIN_DISPATCH_INTERVAL, _MAX_DISPATCH_INTERVAL))
        agent_id = random.choice(agent_ids)
        agent = agents[agent_id]
        task = random.choice(_TASK_DESCRIPTIONS)
        _bus.publish(
            {
                "type": "dispatch",
                "agent_id": agent_id,
                "role": agent.role,
                "task": task,
                "ts": time.strftime("%H:%M:%S"),
                "risk_level": agent.risk_level,
                "profile": agent.preferred_profile,
            }
        )

        def _complete(aid: str = agent_id) -> None:
            time.sleep(random.uniform(_MIN_TASK_DURATION, _MAX_TASK_DURATION))
            _bus.publish(
                {
                    "type": "complete",
                    "agent_id": aid,
                    "ts": time.strftime("%H:%M:%S"),
                }
            )

        threading.Thread(target=_complete, daemon=True).start()


# ---------------------------------------------------------------------------
# Graph data builder
# ---------------------------------------------------------------------------

#: Predefined workflow chains used to enrich graph edges.
_WORKFLOWS: list[dict] = [
    {
        "name": "Feature Development",
        "color": "#58a6ff",
        "steps": [
            "api-designer",
            "backend-engineer",
            "frontend-engineer",
            "qa-engineer",
            "documentation-specialist",
        ],
    },
    {
        "name": "Security Review",
        "color": "#f85149",
        "steps": ["repo-auditor", "cybersecurity-expert", "capability-guardian"],
    },
    {
        "name": "DevOps Pipeline",
        "color": "#3fb950",
        "steps": ["devops-engineer", "performance-engineer", "qa-engineer"],
    },
    {
        "name": "Data Layer",
        "color": "#d29922",
        "steps": ["database-architect", "backend-engineer", "api-designer"],
    },
    {
        "name": "Game Production",
        "color": "#bc8cff",
        "steps": [
            "game-creative-director",
            "game-designer",
            "gameplay-programmer",
            "game-qa-lead",
            "game-producer",
        ],
    },
]


def build_graph_data(agents: dict, _profiles: dict) -> dict:  # noqa: ARG001
    """Return nodes, edges, and workflow metadata for the dashboard graph.

    Parameters
    ----------
    agents:
        Mapping of agent id → :class:`~agent_tools.models.AgentDefinition`.
    _profiles:
        Mapping of profile name → :class:`~agent_tools.models.AccessProfile`
        (unused at present; reserved for future profile-overlay edges).

    Returns
    -------
    dict
        ``{"nodes": [...], "edges": [...], "workflows": [...]}``
    """
    nodes = [
        {
            "id": a.id,
            "role": a.role,
            "description": a.description,
            "tags": a.tags,
            "capabilities": a.capabilities,
            "required_tools": a.required_tools,
            "preferred_profile": a.preferred_profile,
            "risk_level": a.risk_level,
        }
        for a in agents.values()
    ]

    # ── Shared-capability edges ──────────────────────────────────────────────
    agent_list = list(agents.values())
    seen: set[str] = set()
    edges: list[dict] = []
    for i, a in enumerate(agent_list):
        for j, b in enumerate(agent_list):
            if i >= j:
                continue
            shared = set(a.capabilities) & set(b.capabilities)
            if shared:
                key = f"{a.id}:{b.id}"
                if key not in seen:
                    seen.add(key)
                    edges.append(
                        {
                            "source": a.id,
                            "target": b.id,
                            "shared_capabilities": sorted(shared),
                            "weight": len(shared),
                        }
                    )

    # ── Workflow-chain edges (deduplicated) ──────────────────────────────────
    agent_ids = set(agents.keys())
    for wf in _WORKFLOWS:
        steps = [s for s in wf["steps"] if s in agent_ids]
        for k in range(len(steps) - 1):
            a_id, b_id = steps[k], steps[k + 1]
            key = f"{a_id}:{b_id}"
            rev = f"{b_id}:{a_id}"
            if key not in seen and rev not in seen:
                seen.add(key)
                edges.append(
                    {
                        "source": a_id,
                        "target": b_id,
                        "shared_capabilities": [],
                        "weight": 1,
                        "workflow": wf["name"],
                    }
                )

    return {"nodes": nodes, "edges": edges, "workflows": _WORKFLOWS}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class DashboardHandler(BaseHTTPRequestHandler):
    """Request handler for the AgentX dashboard."""

    # silence default request logging
    def log_message(self, _fmt: str, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"

        routes = {
            "/": self._serve_html,
            "/api/agents": self._serve_agents,
            "/api/profiles": self._serve_profiles,
            "/api/graph": self._serve_graph,
            "/api/events": self._serve_sse,
            "/api/executions": self._serve_executions,
            "/api/executions/active": self._serve_active_executions,
        }
        handler = routes.get(path)
        if handler is None:
            self.send_error(404)
            return
        handler()

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/api/execute":
            self._handle_execute()
        elif path == "/api/simulation/toggle":
            self._handle_toggle_simulation()
        else:
            self.send_error(404)

    # ── Route handlers ───────────────────────────────────────────────────────

    def _serve_html(self) -> None:
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_agents(self) -> None:
        self._json_response(self.server.graph_data["nodes"])  # type: ignore[attr-defined]

    def _serve_profiles(self) -> None:
        from dataclasses import asdict

        self._json_response(
            [asdict(p) for p in self.server.profiles.values()]  # type: ignore[attr-defined]
        )

    def _serve_graph(self) -> None:
        self._json_response(self.server.graph_data)  # type: ignore[attr-defined]

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = _bus.subscribe()
        try:
            self.wfile.write(b'data: {"type":"connected"}\n\n')
            self.wfile.flush()
        except OSError:
            _bus.unsubscribe(q)
            return

        try:
            while True:
                try:
                    event = q.get(timeout=15)
                    msg = f"data: {json.dumps(event)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # keepalive comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except OSError:
            pass
        finally:
            _bus.unsubscribe(q)

    def _serve_executions(self) -> None:
        runtime = get_runtime()
        executions = runtime.get_recent_executions(limit=50)
        self._json_response([e.to_dict() for e in executions])

    def _serve_active_executions(self) -> None:
        runtime = get_runtime()
        executions = runtime.get_active_executions()
        self._json_response([e.to_dict() for e in executions])

    def _handle_execute(self) -> None:
        """Handle POST request to execute an agent."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            agent_id = data.get("agent_id")
            task = data.get("task", "")

            if not agent_id:
                self.send_error(400, "Missing agent_id")
                return

            agents = self.server.agents  # type: ignore[attr-defined]
            agent = agents.get(agent_id)
            if not agent:
                self.send_error(404, f"Agent not found: {agent_id}")
                return

            # Create execution
            runtime = get_runtime()
            execution_id = runtime.create_execution(
                agent_id=agent_id,
                agent_role=agent.role,
                task=task,
                metadata={
                    "risk_level": agent.risk_level,
                    "profile": agent.preferred_profile,
                },
            )

            # Start execution immediately (in real implementation,
            # this would be async or delegated to a worker)
            runtime.start_execution(execution_id)

            # Return execution ID
            self._json_response({"execution_id": execution_id, "status": "started"})

        except Exception as e:
            self.send_error(500, str(e))

    def _handle_toggle_simulation(self) -> None:
        """Toggle simulation mode on/off."""
        global _simulation_enabled
        _simulation_enabled = not _simulation_enabled
        self._json_response({"simulation_enabled": _simulation_enabled})

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _json_response(self, data: object) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def serve(host: str = "127.0.0.1", port: int = 7070, enable_simulation: bool = True) -> None:
    """Start the AgentX dashboard HTTP server.

    Parameters
    ----------
    host:
        Interface to bind to.  Defaults to ``127.0.0.1``.
    port:
        Port to listen on.  Defaults to ``7070``.
    enable_simulation:
        Enable simulated activity when no real executions are running.
        Defaults to ``True``.
    """
    global _simulation_enabled
    _simulation_enabled = enable_simulation

    agents = load_agents()
    profiles = load_profiles()
    graph_data = build_graph_data(agents, profiles)

    # Subscribe to real execution events
    runtime = get_runtime()
    runtime.subscribe(_runtime_event_handler)

    # Start simulation loop (will pause when real executions are active)
    threading.Thread(
        target=_simulation_loop,
        args=(agents,),
        daemon=True,
        name="agentx-simulation",
    ).start()

    server = _ThreadingHTTPServer((host, port), DashboardHandler)
    server.agents = agents  # type: ignore[attr-defined]
    server.profiles = profiles  # type: ignore[attr-defined]
    server.graph_data = graph_data  # type: ignore[attr-defined]

    url = f"http://{host}:{port}"
    print(f"AgentX Dashboard  →  {url}")
    print(f"Serving {len(agents)} agents across {len(profiles)} profiles")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Embedded dashboard HTML/CSS/JS
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AgentX — Workflow Dashboard | AI Agent Registry & Orchestration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="AgentX live workflow dashboard — visualise your AI agent registry, monitor real-time task execution, and manage capability-based access profiles across repos.">
<meta name="keywords" content="agentx, ai agents, agent registry, github copilot agents, llm tooling, workflow orchestration, capability checks, access profiles, devtools">
<meta property="og:type" content="website">
<meta property="og:title" content="AgentX — AI Agent Workflow Dashboard">
<meta property="og:description" content="Real-time visualisation of your AI agent registry. Monitor task execution, capability enforcement, and multi-agent workflows.">
<meta name="robots" content="index, follow">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;height:100vh;overflow:hidden}
#app{display:flex;flex-direction:column;height:100vh}

/* ── Top bar ── */
#topbar{height:52px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between;padding:0 20px;flex-shrink:0;gap:12px}
.brand{display:flex;align-items:center;gap:10px}
.logo{font-size:22px;color:#58a6ff;line-height:1}
.title{font-size:15px;font-weight:600;letter-spacing:.4px;white-space:nowrap}
.stats{display:flex;gap:20px;align-items:center}
.stat{display:flex;flex-direction:column;align-items:center;min-width:40px}
.stat .val{font-size:17px;font-weight:700;color:#58a6ff;line-height:1.1}
.stat .lbl{font-size:9px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-top:1px}
.conn-stat{flex-direction:row;gap:6px;align-items:center}
.conn-stat .lbl{font-size:11px;color:#8b949e}
.dot-conn{width:8px;height:8px;border-radius:50%;background:#484f58;display:inline-block;flex-shrink:0}
.dot-conn.live{background:#3fb950;box-shadow:0 0 6px #3fb950}
.dot-conn.err{background:#f85149}

/* ── Layout ── */
#layout{flex:1;display:flex;overflow:hidden}

/* ── Agent panel ── */
#agent-panel{width:252px;background:#0d1117;border-right:1px solid #30363d;display:flex;flex-direction:column;flex-shrink:0;overflow:hidden}
.panel-hdr{padding:10px;border-bottom:1px solid #30363d;display:flex;flex-direction:column;gap:7px}
#search-box{width:100%;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#e6edf3;font-size:12px;outline:none;transition:border-color .15s}
#search-box:focus{border-color:#58a6ff}
#search-box::placeholder{color:#484f58}
.filter-row{display:flex;gap:3px;flex-wrap:wrap}
.fbtn{padding:3px 7px;background:transparent;border:1px solid #30363d;border-radius:4px;color:#8b949e;font-size:9px;cursor:pointer;transition:all .15s;white-space:nowrap}
.fbtn:hover,.fbtn.on{background:#21262d;color:#e6edf3;border-color:#484f58}
.fbtn.on{color:#58a6ff;border-color:#58a6ff}
#agent-list{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:5px}
#agent-list::-webkit-scrollbar{width:4px}
#agent-list::-webkit-scrollbar-track{background:#0d1117}
#agent-list::-webkit-scrollbar-thumb{background:#30363d;border-radius:2px}
.ac{background:#161b22;border:1px solid #30363d;border-radius:7px;padding:9px;cursor:pointer;transition:border-color .15s,box-shadow .15s,background .15s}
.ac:hover{border-color:#484f58;background:#1c2128}
.ac.running{border-color:#3fb950;box-shadow:0 0 8px rgba(63,185,80,.2)}
.ac-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.ac-id{font-size:10px;color:#58a6ff;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:130px}
.ac-role{font-size:11px;font-weight:500;margin-bottom:5px;color:#e6edf3;line-height:1.3}
.ac-tags{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:5px}
.tag{background:#21262d;border:1px solid #30363d;border-radius:3px;padding:1px 5px;font-size:9px;color:#8b949e}
.tag.cap{color:#79c0ff;border-color:#0d419d;background:#0d1932}
.tag.tool{color:#ffa657;border-color:#6e4012;background:#180f05}
.tag.more{color:#484f58}
.rbadge{font-size:9px;padding:1px 5px;border-radius:10px;font-weight:600;text-transform:uppercase;white-space:nowrap;flex-shrink:0}
.r-low{background:rgba(63,185,80,.12);color:#3fb950;border:1px solid rgba(63,185,80,.3)}
.r-medium{background:rgba(210,153,34,.12);color:#d29922;border:1px solid rgba(210,153,34,.3)}
.r-high{background:rgba(248,81,73,.12);color:#f85149;border:1px solid rgba(248,81,73,.3)}
.pbadge{font-size:9px;padding:1px 5px;border-radius:3px;display:inline-block}
.p-safe{color:#58a6ff;background:rgba(88,166,255,.1)}
.p-balanced{color:#d29922;background:rgba(210,153,34,.1)}
.p-power{color:#bc8cff;background:rgba(188,140,255,.1)}

/* ── Graph panel ── */
#graph-panel{flex:1;background:#0d1117;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#graph-tb{height:38px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between;padding:0 14px;flex-shrink:0}
.tb-label{font-size:11px;font-weight:500;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}
.legend{display:flex;gap:10px;align-items:center}
.li{display:flex;align-items:center;gap:4px;font-size:10px;color:#8b949e}
.li .ld{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}
.ld.low{background:#3fb950}.ld.medium{background:#d29922}.ld.high{background:#f85149}
#graph-svg{flex:1;width:100%;height:100%;display:block}
.gnode{cursor:pointer;transition:opacity .2s}
@keyframes pulse-out{0%{r:0;opacity:.7}100%{r:20;opacity:0}}
.pulse-ring.on{animation:pulse-out 1.4s ease-out infinite}

/* ── Activity panel ── */
#act-panel{width:252px;background:#0d1117;border-left:1px solid #30363d;display:flex;flex-direction:column;flex-shrink:0;overflow:hidden}
#act-panel .panel-hdr{flex-direction:row;justify-content:space-between;align-items:center}
.ph-title{font-size:12px;font-weight:500;color:#e6edf3}
#clear-btn{background:transparent;border:1px solid #30363d;border-radius:4px;color:#8b949e;font-size:10px;padding:2px 8px;cursor:pointer}
#clear-btn:hover{background:#21262d;color:#e6edf3}
#act-feed{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:4px}
#act-feed::-webkit-scrollbar{width:4px}
#act-feed::-webkit-scrollbar-track{background:#0d1117}
#act-feed::-webkit-scrollbar-thumb{background:#30363d;border-radius:2px}
.ai{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:7px;font-size:11px;animation:slidein .2s ease}
@keyframes slidein{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
.ai.dispatch{border-left:3px solid #58a6ff}
.ai.complete{border-left:3px solid #3fb950;opacity:.7}
.ai-hdr{display:flex;justify-content:space-between;margin-bottom:3px;align-items:center}
.ai-ts{color:#484f58;font-size:10px;font-family:monospace}
.ai-type{font-size:9px;font-weight:700;padding:1px 4px;border-radius:2px}
.ai-type.dispatch{color:#58a6ff;background:rgba(88,166,255,.1)}
.ai-type.complete{color:#3fb950;background:rgba(63,185,80,.1)}
.ai-agent{color:#79c0ff;font-family:monospace;cursor:pointer;font-size:10px}
.ai-agent:hover{text-decoration:underline}
.ai-task{color:#8b949e}

/* ── Detail modal ── */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;z-index:200}
.modal-bg.hidden{display:none}
.modal-box{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;max-width:480px;width:90vw;max-height:80vh;overflow-y:auto;position:relative}
.modal-x{position:absolute;top:12px;right:16px;background:none;border:none;color:#8b949e;font-size:20px;cursor:pointer;line-height:1}
.modal-x:hover{color:#e6edf3}
.m-hdr{margin-bottom:8px}
.m-hdr h2{font-size:17px;font-weight:600}
.m-badges{display:flex;gap:6px;margin-top:5px;flex-wrap:wrap}
.m-id{font-size:11px;color:#58a6ff;font-family:monospace;margin-bottom:8px}
.m-desc{font-size:12px;color:#8b949e;line-height:1.5;margin-bottom:14px}
.m-sec{margin-bottom:12px}
.m-sec h3{font-size:10px;text-transform:uppercase;color:#8b949e;letter-spacing:.5px;margin-bottom:5px}
.tag-list{display:flex;flex-wrap:wrap;gap:4px}
.m-status{display:flex;align-items:center;gap:6px;font-size:11px;color:#8b949e;margin-top:12px;padding-top:12px;border-top:1px solid #30363d}
.sdot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.sdot.idle{background:#484f58}
.sdot.active{background:#3fb950;box-shadow:0 0 6px #3fb950}
</style>
</head>
<body>
<div id="app">
  <header id="topbar">
    <div class="brand">
      <span class="logo">&#11041;</span>
      <span class="title">AgentX Dashboard</span>
    </div>
    <div class="stats">
      <div class="stat"><span class="val" id="s-agents">&mdash;</span><span class="lbl">Agents</span></div>
      <div class="stat"><span class="val" id="s-active">0</span><span class="lbl">Active</span></div>
      <div class="stat"><span class="val" id="s-profiles">&mdash;</span><span class="lbl">Profiles</span></div>
      <div class="stat conn-stat"><span class="dot-conn" id="conn-dot"></span><span class="lbl" id="conn-lbl">Connecting&hellip;</span></div>
    </div>
  </header>

  <div id="layout">
    <!-- Agent list panel -->
    <aside id="agent-panel">
      <div class="panel-hdr">
        <input id="search-box" type="search" placeholder="Search agents&hellip;" autocomplete="off">
        <div class="filter-row">
          <button class="fbtn on" data-f="all">All</button>
          <button class="fbtn" data-f="low">Low</button>
          <button class="fbtn" data-f="medium">Medium</button>
          <button class="fbtn" data-f="high">High</button>
          <button class="fbtn" data-f="safe">Safe</button>
          <button class="fbtn" data-f="balanced">Balanced</button>
          <button class="fbtn" data-f="power">Power</button>
        </div>
      </div>
      <div id="agent-list"></div>
    </aside>

    <!-- Force-directed graph -->
    <main id="graph-panel">
      <div id="graph-tb">
        <span class="tb-label">Workflow Graph</span>
        <div class="legend">
          <span class="li"><span class="ld low"></span>Low risk</span>
          <span class="li"><span class="ld medium"></span>Medium risk</span>
          <span class="li"><span class="ld high"></span>High risk</span>
        </div>
      </div>
      <svg id="graph-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <g id="g-edges"></g>
        <g id="g-nodes"></g>
      </svg>
    </main>

    <!-- Activity feed panel -->
    <aside id="act-panel">
      <div class="panel-hdr">
        <span class="ph-title">Live Activity</span>
        <button id="clear-btn">Clear</button>
      </div>
      <div id="act-feed"></div>
    </aside>
  </div>

  <!-- Detail modal -->
  <div class="modal-bg hidden" id="modal">
    <div class="modal-box">
      <button class="modal-x" id="modal-x">&times;</button>
      <div id="modal-body"></div>
    </div>
  </div>
</div>
<script>
/* =====================================================================
   AgentX Dashboard — vanilla JS, no external dependencies
   ===================================================================== */

const RISK_COLOR = {low:'#3fb950', medium:'#d29922', high:'#f85149'};
const PROF_COLOR = {safe:'#58a6ff', balanced:'#d29922', power:'#bc8cff'};
const SVG_NS = 'http://www.w3.org/2000/svg';
const MAX_FEED = 35;

const st = {agents:[], profiles:[], graphData:null, active:new Set(), filter:'all', search:''};

// ── Escape helper ────────────────────────────────────────────────────────────
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

// ── Force-directed graph ─────────────────────────────────────────────────────
class ForceGraph {
  constructor(nodes, edges){
    this.W=800; this.H=600; this.alpha=1;
    this.nodes = nodes.map(n=>({...n, x:0, y:0, vx:0, vy:0}));
    this.edges = edges;
    this._byId = {};
    this.nodes.forEach(n=>this._byId[n.id]=n);
  }
  resize(W,H){
    if(this.W===W && this.H===H) return;
    this.W=W; this.H=H;
    this.nodes.forEach((n,i)=>{
      if(n.x===0&&n.y===0){
        const a=(2*Math.PI*i)/this.nodes.length;
        const r=Math.min(W,H)*0.33;
        n.x=W/2+r*Math.cos(a); n.y=H/2+r*Math.sin(a);
      }
    });
    this.alpha=Math.max(this.alpha,0.4);
  }
  tick(){
    if(this.alpha<0.002) return;
    const {nodes,edges,W,H,_byId}=this;
    // Repulsion
    for(let i=0;i<nodes.length;i++){
      for(let j=i+1;j<nodes.length;j++){
        const a=nodes[i],b=nodes[j];
        let dx=b.x-a.x, dy=b.y-a.y;
        const d=Math.sqrt(dx*dx+dy*dy)||.1;
        const k=7000/(d*d);
        const fx=k*dx/d, fy=k*dy/d;
        a.vx-=fx; a.vy-=fy; b.vx+=fx; b.vy+=fy;
      }
    }
    // Spring attraction
    for(const e of edges){
      const a=_byId[e.source], b=_byId[e.target];
      if(!a||!b) continue;
      const dx=b.x-a.x, dy=b.y-a.y;
      const d=Math.sqrt(dx*dx+dy*dy)||.1;
      const ideal=110+(e.weight||1)*15;
      const k=0.025*(d-ideal);
      const fx=k*dx/d, fy=k*dy/d;
      a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
    }
    // Centre gravity
    for(const n of nodes){
      n.vx+=(W/2-n.x)*0.004;
      n.vy+=(H/2-n.y)*0.004;
    }
    // Integrate
    for(const n of nodes){
      n.vx*=0.84; n.vy*=0.84;
      n.x=Math.max(38,Math.min(W-38,n.x+n.vx));
      n.y=Math.max(38,Math.min(H-38,n.y+n.vy));
    }
    this.alpha*=0.995;
  }
}

let fg=null, raf=null;

function initGraph(data){
  const svg=document.getElementById('graph-svg');
  fg=new ForceGraph(data.nodes, data.edges);
  fg.resize(svg.clientWidth||800, svg.clientHeight||600);

  _renderEdges(data.edges);
  _renderNodes(fg.nodes);

  if(raf) cancelAnimationFrame(raf);
  function loop(){fg.tick();_updatePos();raf=requestAnimationFrame(loop);}
  raf=requestAnimationFrame(loop);

  const ro=new ResizeObserver(()=>{
    fg.resize(svg.clientWidth, svg.clientHeight);
  });
  ro.observe(svg);
}

function _renderEdges(edges){
  const g=document.getElementById('g-edges');
  g.innerHTML='';
  for(const e of edges){
    const line=document.createElementNS(SVG_NS,'line');
    line.setAttribute('stroke','#30363d');
    line.setAttribute('stroke-width', Math.min(3,e.weight||1).toString());
    line.setAttribute('opacity','0.55');
    line.dataset.src=e.source; line.dataset.tgt=e.target;
    g.appendChild(line);
  }
}

function _renderNodes(nodes){
  const g=document.getElementById('g-nodes');
  g.innerHTML='';
  for(const n of nodes){
    const color=RISK_COLOR[n.risk_level]||'#8b949e';
    const r=20+Math.min(n.capabilities.length*1.8,12);
    const grp=document.createElementNS(SVG_NS,'g');
    grp.id='n-'+n.id;
    grp.setAttribute('class','gnode');

    // Pulse ring (animated when active)
    const pulse=document.createElementNS(SVG_NS,'circle');
    pulse.setAttribute('class','pulse-ring');
    pulse.setAttribute('cx','0'); pulse.setAttribute('cy','0');
    pulse.setAttribute('r', (r+6).toString());
    pulse.setAttribute('fill','none');
    pulse.setAttribute('stroke',color);
    pulse.setAttribute('stroke-width','2');
    pulse.setAttribute('opacity','0');
    pulse.style.transformBox='fill-box';
    pulse.style.transformOrigin='center';

    // Body circle
    const circ=document.createElementNS(SVG_NS,'circle');
    circ.setAttribute('class','body-circ');
    circ.setAttribute('cx','0'); circ.setAttribute('cy','0');
    circ.setAttribute('r',r.toString());
    circ.setAttribute('fill',color);
    circ.setAttribute('fill-opacity','0.18');
    circ.setAttribute('stroke',color);
    circ.setAttribute('stroke-width','1.8');

    // Profile dot
    const pdot=document.createElementNS(SVG_NS,'circle');
    pdot.setAttribute('cx',(r-3).toString()); pdot.setAttribute('cy',(-r+3).toString());
    pdot.setAttribute('r','5');
    pdot.setAttribute('fill',PROF_COLOR[n.preferred_profile]||'#8b949e');

    // Label
    const words=n.role.split(' ');
    const label=words.length<=2 ? words.map(w=>w.slice(0,5)).join(' ')
      : words.slice(0,2).map(w=>w[0].toUpperCase()).join('')+words.slice(2).map(w=>w[0]).join('');
    const txt=document.createElementNS(SVG_NS,'text');
    txt.setAttribute('text-anchor','middle');
    txt.setAttribute('dy','4');
    txt.setAttribute('font-size','9');
    txt.setAttribute('fill','#e6edf3');
    txt.setAttribute('font-family',"-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif");
    txt.setAttribute('pointer-events','none');
    txt.textContent=label;

    grp.appendChild(pulse);
    grp.appendChild(circ);
    grp.appendChild(pdot);
    grp.appendChild(txt);

    grp.addEventListener('click',()=>showDetail(n.id));
    grp.addEventListener('mouseenter',()=>hlConnected(n.id));
    grp.addEventListener('mouseleave',()=>clearHl());

    // Tooltip title
    const title=document.createElementNS(SVG_NS,'title');
    title.textContent=n.role+' ('+n.preferred_profile+', '+n.risk_level+' risk)';
    grp.appendChild(title);

    g.appendChild(grp);
  }
}

function _updatePos(){
  if(!fg) return;
  for(const n of fg.nodes){
    const g=document.getElementById('n-'+n.id);
    if(g) g.setAttribute('transform',`translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`);
  }
  for(const el of document.querySelectorAll('#g-edges line')){
    const a=fg._byId[el.dataset.src], b=fg._byId[el.dataset.tgt];
    if(!a||!b) continue;
    el.setAttribute('x1',a.x.toFixed(1)); el.setAttribute('y1',a.y.toFixed(1));
    el.setAttribute('x2',b.x.toFixed(1)); el.setAttribute('y2',b.y.toFixed(1));
  }
}

// ── Node activation ──────────────────────────────────────────────────────────
function activateNode(id){
  st.active.add(id);
  const g=document.getElementById('n-'+id);
  if(!g) return;
  g.querySelector('.body-circ').setAttribute('fill-opacity','0.55');
  const p=g.querySelector('.pulse-ring');
  if(p){p.setAttribute('opacity','1');p.classList.add('on');}
  if(fg) fg.alpha=Math.max(fg.alpha,0.12);
  _syncActiveCount();
}
function deactivateNode(id){
  st.active.delete(id);
  const g=document.getElementById('n-'+id);
  if(!g) return;
  g.querySelector('.body-circ').setAttribute('fill-opacity','0.18');
  const p=g.querySelector('.pulse-ring');
  if(p){p.setAttribute('opacity','0');p.classList.remove('on');}
  _syncActiveCount();
}

// ── Highlight ────────────────────────────────────────────────────────────────
function hlConnected(nodeId){
  if(!fg) return;
  const conn=new Set([nodeId]);
  for(const e of fg.edges){
    if(e.source===nodeId) conn.add(e.target);
    if(e.target===nodeId) conn.add(e.source);
  }
  for(const n of fg.nodes){
    const g=document.getElementById('n-'+n.id);
    if(g) g.setAttribute('opacity', conn.has(n.id)?'1':'0.2');
  }
  for(const el of document.querySelectorAll('#g-edges line')){
    const isConn=el.dataset.src===nodeId||el.dataset.tgt===nodeId;
    el.setAttribute('opacity', isConn?'1':'0.08');
    if(isConn){el.setAttribute('stroke','#58a6ff');el.setAttribute('stroke-width','2');}
  }
}
function clearHl(){
  document.querySelectorAll('.gnode').forEach(g=>g.setAttribute('opacity','1'));
  if(fg){
    for(const e of fg.edges){
      const el=document.querySelector(`line[data-src="${e.source}"][data-tgt="${e.target}"]`);
      if(el){
        el.setAttribute('opacity','0.55');
        el.setAttribute('stroke','#30363d');
        el.setAttribute('stroke-width', Math.min(3,e.weight||1).toString());
      }
    }
  }
}

// ── Agent list panel ─────────────────────────────────────────────────────────
function renderAgentList(){
  const cont=document.getElementById('agent-list');
  const q=st.search.toLowerCase();
  const flt=st.filter;

  const visible=st.agents.filter(a=>{
    if(flt==='low'||flt==='medium'||flt==='high') return a.risk_level===flt;
    if(flt==='safe'||flt==='balanced'||flt==='power') return a.preferred_profile===flt;
    return true;
  }).filter(a=>{
    if(!q) return true;
    return [a.id,a.role,...a.tags,...a.capabilities].some(s=>s.toLowerCase().includes(q));
  });

  cont.innerHTML='';
  for(const a of visible){
    const div=document.createElement('div');
    div.className='ac'+(st.active.has(a.id)?' running':'');
    div.dataset.id=a.id;
    const tagHtml=a.tags.slice(0,3).map(t=>`<span class="tag">${esc(t)}</span>`).join('')
      +(a.tags.length>3?`<span class="tag more">+${a.tags.length-3}</span>`:'');
    div.innerHTML=`
      <div class="ac-top">
        <span class="ac-id" title="${esc(a.id)}">${esc(a.id)}</span>
        <span class="rbadge r-${a.risk_level}">${a.risk_level}</span>
      </div>
      <div class="ac-role">${esc(a.role)}</div>
      <div class="ac-tags">${tagHtml}</div>
      <span class="pbadge p-${a.preferred_profile}">${a.preferred_profile}</span>`;
    div.addEventListener('click',()=>showDetail(a.id));
    cont.appendChild(div);
  }
}

// ── Activity feed ─────────────────────────────────────────────────────────────
function addFeedItem(ev){
  const feed=document.getElementById('act-feed');
  const d=document.createElement('div');
  d.className='ai '+ev.type;
  if(ev.type==='dispatch'){
    d.innerHTML=`<div class="ai-hdr">
      <span class="ai-ts">${esc(ev.ts)}</span>
      <span class="ai-type dispatch">DISPATCH</span>
    </div>
    <div>
      <span class="ai-agent" data-id="${esc(ev.agent_id)}">${esc(ev.agent_id)}</span>
      <span class="ai-task"> \u2192 ${esc(ev.task)}</span>
    </div>`;
  } else {
    d.innerHTML=`<div class="ai-hdr">
      <span class="ai-ts">${esc(ev.ts)}</span>
      <span class="ai-type complete">DONE</span>
    </div>
    <div>
      <span class="ai-agent" data-id="${esc(ev.agent_id)}">${esc(ev.agent_id)}</span>
      <span class="ai-task"> completed task</span>
    </div>`;
  }
  d.querySelector('.ai-agent').addEventListener('click',()=>{
    hlConnected(ev.agent_id);
    const card=document.querySelector(`.ac[data-id="${ev.agent_id}"]`);
    if(card) card.scrollIntoView({behavior:'smooth',block:'nearest'});
  });
  feed.insertBefore(d,feed.firstChild);
  while(feed.children.length>MAX_FEED) feed.removeChild(feed.lastChild);
}

// ── Agent detail modal ────────────────────────────────────────────────────────
function showDetail(agentId){
  const a=st.agents.find(x=>x.id===agentId);
  if(!a) return;
  const rc=RISK_COLOR[a.risk_level]||'#8b949e';
  const isActive=st.active.has(a.id);
  document.getElementById('modal-body').innerHTML=`
    <div class="m-hdr">
      <h2>${esc(a.role)}</h2>
      <div class="m-badges">
        <span class="rbadge r-${a.risk_level}">${a.risk_level} risk</span>
        <span class="pbadge p-${a.preferred_profile}">${a.preferred_profile}</span>
      </div>
    </div>
    <div class="m-id">${esc(a.id)}</div>
    <p class="m-desc">${esc(a.description)}</p>
    <div class="m-sec"><h3>Tags</h3>
      <div class="tag-list">${a.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>
    </div>
    <div class="m-sec"><h3>Capabilities</h3>
      <div class="tag-list">${a.capabilities.map(c=>`<span class="tag cap">${esc(c)}</span>`).join('')}</div>
    </div>
    <div class="m-sec"><h3>Required Tools</h3>
      <div class="tag-list">${a.required_tools.map(t=>`<span class="tag tool">${esc(t)}</span>`).join('')}</div>
    </div>
    <div class="m-status">
      <span class="sdot ${isActive?'active':'idle'}"></span>
      ${isActive?'Currently active':'Idle'}
    </div>`;
  document.getElementById('modal').classList.remove('hidden');
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function connectSSE(){
  const dot=document.getElementById('conn-dot');
  const lbl=document.getElementById('conn-lbl');
  const es=new EventSource('/api/events');
  es.onopen=()=>{dot.className='dot-conn live';lbl.textContent='Live';};
  es.onerror=()=>{dot.className='dot-conn err';lbl.textContent='Reconnecting\u2026';};
  es.onmessage=e=>{
    const ev=JSON.parse(e.data);
    if(ev.type==='connected') return;
    if(ev.type==='dispatch'){
      activateNode(ev.agent_id);
      addFeedItem(ev);
      _syncCard(ev.agent_id,true);
    } else if(ev.type==='complete'){
      deactivateNode(ev.agent_id);
      addFeedItem(ev);
      _syncCard(ev.agent_id,false);
    }
  };
}

function _syncCard(id,running){
  const c=document.querySelector(`.ac[data-id="${id}"]`);
  if(c){running?c.classList.add('running'):c.classList.remove('running');}
}
function _syncActiveCount(){
  document.getElementById('s-active').textContent=st.active.size;
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init(){
  const [ar,pr,gr]=await Promise.all([
    fetch('/api/agents'), fetch('/api/profiles'), fetch('/api/graph')
  ]);
  st.agents=await ar.json();
  st.profiles=await pr.json();
  st.graphData=await gr.json();
  document.getElementById('s-agents').textContent=st.agents.length;
  document.getElementById('s-profiles').textContent=st.profiles.length;
  renderAgentList();
  initGraph(st.graphData);
  connectSSE();
}

// ── Event listeners ───────────────────────────────────────────────────────────
document.getElementById('search-box').addEventListener('input',e=>{
  st.search=e.target.value; renderAgentList();
});
document.querySelectorAll('.fbtn').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.fbtn').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); st.filter=b.dataset.f; renderAgentList();
}));
document.getElementById('clear-btn').addEventListener('click',()=>{
  document.getElementById('act-feed').innerHTML='';
});
document.getElementById('modal-x').addEventListener('click',()=>{
  document.getElementById('modal').classList.add('hidden');
});
document.getElementById('modal').addEventListener('click',e=>{
  if(e.target===document.getElementById('modal'))
    document.getElementById('modal').classList.add('hidden');
});

init();
</script>
</body>
</html>
"""

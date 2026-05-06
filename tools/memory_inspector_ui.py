#!/usr/bin/env python3
"""Flask UI to inspect session memory and run semantic searches.

Reads from the persistent ChromaDB vector store (or falls back to an
in-memory store when chromadb is not installed).

Endpoints
---------
GET  /                     HTML inspector landing page.
GET  /inspect?session=…    HTML view of global memory for a session.
GET  /search?session=…&q=… HTML semantic search results.
GET  /api/inspect_json?session=… JSON: {"items": […]}
GET  /api/search_json?session=…&q=… JSON: {"items": […]}

Run::

    python tools/memory_inspector_ui.py
    # Open http://localhost:5002/

Set REPO_ROOT env var to point at the right vector_memory directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_DIR))

from agent_tools.engine.memory import create_memory_adapter, MemoryAdapter

try:
    from flask import Flask, abort, jsonify, render_template_string, request
except ImportError as exc:
    print("Flask is required:  pip install flask", file=sys.stderr)
    raise SystemExit(1) from exc

app = Flask(__name__)

_REPO_ROOT = Path(os.getenv("REPO_ROOT", str(_REPO_ROOT_DIR))).resolve()

# Build memory adapter — prefer chroma (persistent); fall back to in-memory.
try:
    _mem: MemoryAdapter = create_memory_adapter("chroma", _REPO_ROOT)
except Exception:  # chromadb not installed or no data yet
    _mem = create_memory_adapter("vector", _REPO_ROOT)

# Optional: wire RealAI embeddings for semantic search.
try:
    from agent_tools.providers.realai_embeddings import RealAIEmbeddings
    _emb = RealAIEmbeddings()
except Exception:
    _emb = None

if _emb is not None:
    try:
        _mem = create_memory_adapter("chroma", _REPO_ROOT, embeddings_provider=_emb)
    except Exception:
        pass  # keep existing adapter

_INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Memory Inspector</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }
    h1   { border-bottom: 2px solid #e0e0e0; padding-bottom: .5rem; }
    li   { margin: .4rem 0; }
    em   { color: #555; }
    input { padding: .3rem .6rem; font-size: 1rem; }
    button { padding: .3rem .8rem; font-size: 1rem; cursor: pointer; }
  </style>
</head>
<body>
  <h1>&#x1F9E0; Memory Inspector</h1>
  <form method="get" action="/inspect">
    Session ID: <input name="session" value="{{ session }}" placeholder="e.g. my-session-1" />
    <button type="submit">Inspect</button>
  </form>

  {% if session %}
    <h2>Global namespace: {{ session }}:global ({{ items | length }} item(s))</h2>
    {% if items %}
    <ul>
      {% for item in items %}
      <li><strong>{{ item.agent_id }}</strong>: {{ item.input }}<br/><em>{{ item.summary }}</em></li>
      {% endfor %}
    </ul>
    {% else %}
      <p><em>No items found.</em></p>
    {% endif %}

    <h3>Semantic search</h3>
    <form method="get" action="/search">
      <input name="session" type="hidden" value="{{ session }}"/>
      <input name="q" placeholder="search query" />
      <button type="submit">Search</button>
    </form>
  {% endif %}
</body>
</html>
"""

_SEARCH_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Search results</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }
    li { margin: .4rem 0; }
    em { color: #555; }
  </style>
</head>
<body>
  <h1>Search: "{{ q }}" — session {{ session }}</h1>
  {% if results %}
  <ul>
    {% for item in results %}
    <li><strong>{{ item.agent_id }}</strong>: {{ item.input }}<br/><em>{{ item.summary }}</em></li>
    {% endfor %}
  </ul>
  {% else %}
    <p><em>No results.</em></p>
  {% endif %}
  <a href="/inspect?session={{ session }}">&larr; Back</a>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(_INDEX_HTML, session="", items=[])


@app.route("/inspect")
def inspect():
    session = request.args.get("session", "").strip()
    if not session:
        return render_template_string(_INDEX_HTML, session="", items=[])
    items = _get_items(session)
    return render_template_string(_INDEX_HTML, session=session, items=items)


@app.route("/search")
def search():
    session = request.args.get("session", "").strip()
    q = request.args.get("q", "").strip()
    if not session or not q:
        abort(400)
    results = _search_items(session, q)
    return render_template_string(_SEARCH_HTML, session=session, q=q, results=results)


# ---------------------------------------------------------------------------
# JSON API routes (consumed by the React dashboard)
# ---------------------------------------------------------------------------

@app.route("/api/inspect_json")
def inspect_json():
    session = request.args.get("session", "").strip()
    if not session:
        return jsonify({"items": []})
    return jsonify({"items": _get_items(session)})


@app.route("/api/search_json")
def search_json():
    session = request.args.get("session", "").strip()
    q = request.args.get("q", "").strip()
    if not session or not q:
        return jsonify({"items": []})
    return jsonify({"items": _search_items(session, q)})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(items: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for it in items:
        if isinstance(it, dict):
            out.append({
                "agent_id": str(it.get("agent_id", "unknown")),
                "input": str(it.get("input", "")),
                "summary": str(it.get("summary", "")),
            })
    return out


def _get_items(session: str) -> list[dict[str, str]]:
    ns = f"{session}:global"
    try:
        items = _mem.read(namespace=ns, limit=200)
    except Exception:
        items = []
    return _normalize(items)


def _search_items(session: str, q: str, k: int = 10) -> list[dict[str, str]]:
    ns = f"{session}:global"
    try:
        results = _mem.search(namespace=ns, query=q, k=k)
    except Exception:
        results = []
    return _normalize(results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Memory Inspector UI")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode (development only — never use in production)",
    )
    args = parser.parse_args()
    print(f"Starting Memory Inspector at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug)

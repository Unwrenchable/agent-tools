# RealAI Dashboard

A minimal React dashboard for inspecting session memory and monitoring the approval queue.

## What it shows

| Panel | Source |
|---|---|
| **Session Memory** | Reads global memory for a session from the Memory Inspector UI (`/api/inspect_json`) |
| **Semantic Search** | Queries vector memory for a session (`/api/search_json`) |
| **Approval Queue** | Lists all approval requests from the Approval UI (`/api/requests`) |

## Prerequisites

- Node.js ≥ 18
- Memory Inspector UI running on `http://localhost:5002` (`python tools/memory_inspector_ui.py`)
- Approval UI running on `http://localhost:5001` (`python tools/approval_ui.py`)

## Quick start

```bash
cd web/dashboard
npm install
npm start
# Open http://localhost:3000
```

## Configuration

Set environment variables before `npm start` to override backend URLs:

```bash
REACT_APP_INSPECTOR_BASE=https://inspector.example.com \
REACT_APP_APPROVAL_BASE=https://approvals.example.com \
npm start
```

## Production build

```bash
npm run build
# Serve the build/ directory with any static web server.
```

## API contract

The dashboard expects these JSON endpoints on the inspector and approval services:

| Endpoint | Response |
|---|---|
| `GET /api/inspect_json?session=<id>` | `{"items": [{"agent_id": "…", "input": "…", "summary": "…"}]}` |
| `GET /api/search_json?session=<id>&q=<query>` | `{"items": […]}` |
| `GET /api/requests` | `[{"id": "…", "action": "…", "payload": {…}, "status": "…"}]` |

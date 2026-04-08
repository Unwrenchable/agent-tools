# Fullstack Vercel Deployment Guide

Deploy the AgentX dashboard and API as a fullstack application on Vercel using Python serverless functions for the backend and a static HTML frontend.

## Architecture

```
Vercel project
├── public/
│   └── index.html          ← dashboard UI (extracted from dashboard.py _HTML)
├── api/
│   ├── agents.py           ← GET /api/agents
│   ├── profiles.py         ← GET /api/profiles
│   ├── graph.py            ← GET /api/graph
│   ├── executions.py       ← GET /api/executions
│   └── execute.py          ← POST /api/execute
└── vercel.json             ← routing + Python runtime config
```

> **SSE limitation**: The `/api/events` Server-Sent Events endpoint requires a
> persistent long-lived connection and is not suitable for Vercel's serverless
> runtime (max 25 s execution time on all plans). The static dashboard falls
> back to polling `/api/executions` every few seconds instead.

---

## Prerequisites

- [Vercel account](https://vercel.com/signup) (free Hobby plan is sufficient)
- [Vercel CLI](https://vercel.com/docs/cli): `npm i -g vercel`
- Python 3.11 or later (local development only)
- The `agent-tools` package installable locally: `pip install -e .`

---

## Step 1 — Extract the dashboard HTML

The dashboard HTML lives inside `agent_tools/dashboard.py` as the `_HTML`
string. Extract it to a static file that Vercel can serve directly.

```bash
python - <<'EOF'
from agent_tools.dashboard import _HTML
from pathlib import Path
Path("public").mkdir(exist_ok=True)
Path("public/index.html").write_text(_HTML, encoding="utf-8")
print("Written public/index.html")
EOF
```

The frontend fetches `/api/agents`, `/api/graph`, and `/api/executions` via
`fetch()`. Because SSE is not available in serverless, replace the
`EventSource` connection in `public/index.html` with a polling loop inside the
`<script>` block:

```js
// Before (SSE – remove this):
// const es = new EventSource('/api/events');

// After (polling every 3 s):
setInterval(async () => {
  const res = await fetch('/api/executions');
  if (!res.ok) return;
  const data = await res.json();
  updateFeed(data);          // use your existing feed-rendering function
}, 3000);
```

---

## Step 2 — Create the API serverless functions

Create an `api/` directory at the repo root. Each file becomes a Vercel
serverless function exposed at the matching URL path.

### `api/agents.py`

```python
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.registry import load_agents


def handler(request, response):
    agents = load_agents()
    payload = [
        {
            "id": a.id, "role": a.role, "description": a.description,
            "tags": a.tags, "capabilities": a.capabilities,
            "required_tools": a.required_tools,
            "preferred_profile": a.preferred_profile,
            "risk_level": a.risk_level,
        }
        for a in agents.values()
    ]
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response.body = json.dumps(payload)
```

### `api/profiles.py`

```python
from __future__ import annotations
import json, sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.registry import load_profiles


def handler(request, response):
    profiles = load_profiles()
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response.body = json.dumps([asdict(p) for p in profiles.values()])
```

### `api/graph.py`

```python
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.dashboard import build_graph_data
from agent_tools.registry import load_agents, load_profiles


def handler(request, response):
    agents = load_agents()
    profiles = load_profiles()
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response.body = json.dumps(build_graph_data(agents, profiles))
```

### `api/executions.py`

```python
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.runtime import get_runtime


def handler(request, response):
    runtime = get_runtime()
    executions = runtime.get_recent_executions(limit=50)
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response.body = json.dumps([e.to_dict() for e in executions])
```

### `api/execute.py`

```python
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.executor import execute_agent_task


def handler(request, response):
    try:
        body = json.loads(request.body)
        agent_id = body.get("agent_id", "")
        task = body.get("task", "")
        if not agent_id:
            response.status_code = 400
            response.body = json.dumps({"error": "Missing agent_id"})
            return
        execution_id = execute_agent_task(agent_id, task)
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response.body = json.dumps({"execution_id": execution_id})
    except Exception as exc:
        response.status_code = 500
        response.body = json.dumps({"error": str(exc)})
```

---

## Step 3 — Configure `vercel.json`

Replace the empty `vercel.json` at the repo root with:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/*.py",
      "use": "@vercel/python"
    },
    {
      "src": "public/**",
      "use": "@vercel/static"
    }
  ],
  "routes": [
    { "src": "/api/agents",            "dest": "/api/agents.py"     },
    { "src": "/api/profiles",          "dest": "/api/profiles.py"   },
    { "src": "/api/graph",             "dest": "/api/graph.py"      },
    { "src": "/api/executions",        "dest": "/api/executions.py" },
    { "src": "/api/execute",           "dest": "/api/execute.py"    },
    { "src": "/(.*)",                  "dest": "/public/index.html" }
  ]
}
```

---

## Step 4 — Add a `requirements.txt`

Vercel's Python runtime installs dependencies from `requirements.txt` at the
project root. Because `agent_tools` has no external runtime dependencies, the
file only needs the package itself:

```
./
```

This tells Vercel to install the local package via pip (equivalent to
`pip install .`).

---

## Step 5 — Deploy

### First deploy (interactive)

```bash
vercel
```

Follow the prompts:
1. Link to an existing project or create a new one.
2. Choose the detected framework: **Other**.
3. Override the build command if prompted: leave blank (Vercel infers it from `vercel.json`).
4. Accept the default output directory.

### Subsequent deploys

```bash
vercel --prod          # deploy to production
vercel                 # deploy to a preview URL
```

### Deploy via GitHub Actions (CI/CD)

Add the following workflow to `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Vercel

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Extract dashboard HTML
        run: |
          pip install -e .
          mkdir -p public
          python -c "
          from agent_tools.dashboard import _HTML
          from pathlib import Path
          Path('public/index.html').write_text(_HTML, encoding='utf-8')
          "

      - name: Deploy
        run: npx vercel --prod --token ${{ secrets.VERCEL_TOKEN }} --yes
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
```

Set `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` as repository
secrets (find these values in your Vercel project settings).

---

## Environment variables

No environment variables are required for basic operation. If you add
authentication or a database backend later, configure them in the Vercel
dashboard under **Settings → Environment Variables** and reference them in
your functions via `os.environ`.

---

## Local preview with the Vercel CLI

```bash
# Install dependencies and extract the HTML first (once)
pip install -e .
python -c "
from agent_tools.dashboard import _HTML
from pathlib import Path
Path('public').mkdir(exist_ok=True)
Path('public/index.html').write_text(_HTML, encoding='utf-8')
"

# Start the local dev server (mirrors the Vercel routing)
vercel dev
# Open http://localhost:3000
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: agent_tools` | `requirements.txt` missing or wrong | Ensure `requirements.txt` contains `./` and re-deploy |
| `404` on `/api/*` routes | Routing not matching function filenames | Check `vercel.json` `routes` entries match `api/*.py` filenames |
| Empty agent list | Registry data files not bundled | Confirm `agent_tools/data/*.json` is included (it is by default via `pyproject.toml` `package-data`) |
| Live feed not updating | SSE not available on serverless | Implement polling in `public/index.html` as described in Step 1 |
| Function timeout | Cold-start latency on free plan | Reduce registry size or pre-warm with a scheduled ping |

---

## Further reading

- [Vercel Python Runtime docs](https://vercel.com/docs/functions/runtimes/python)
- [Vercel routing docs](https://vercel.com/docs/projects/project-configuration#routes)
- [AgentX Real-Time Execution Guide](REAL_TIME_EXECUTION.md)

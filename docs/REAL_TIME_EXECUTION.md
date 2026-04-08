# Real-Time Agent Execution Guide

This guide shows how to use the real-time agent execution and visualization features to streamline your workflow.

## Quick Start

### 1. Start the Dashboard

Launch the web dashboard to visualize agent activity in real-time:

```bash
agentx serve
# Dashboard available at http://127.0.0.1:7070
```

Options:
- `--host HOST` - Bind to specific interface (default: 127.0.0.1)
- `--port PORT` - Use custom port (default: 7070)
- `--no-simulation` - Disable simulated activity (only show real executions)

### 2. Execute a Single Agent

Run an agent with a specific task:

```bash
# Execute and return immediately
agentx run api-designer "Design a REST API for user authentication"

# Execute and watch progress in real-time
agentx run backend-engineer "Implement JWT-based authentication" --watch
```

The execution will appear live in the dashboard with:
- Visual node activation (pulse animation)
- Real-time activity feed updates
- Task progress tracking

### 3. Execute Agent Workflows

Create a workflow JSON file defining a sequence of agent tasks:

```json
{
  "name": "Feature Development",
  "steps": [
    {
      "agent_id": "api-designer",
      "task": "Design REST API endpoints for feature X"
    },
    {
      "agent_id": "backend-engineer",
      "task": "Implement the API endpoints"
    },
    {
      "agent_id": "qa-engineer",
      "task": "Create test suite for the new endpoints"
    }
  ]
}
```

Execute the workflow:

```bash
# Sequential execution (one agent at a time)
agentx workflow --file my-workflow.json

# Parallel execution (all agents simultaneously)
agentx workflow --file my-workflow.json --parallel
```

Example workflows are available in `examples/`:
- `workflow-feature-dev.json` - Full feature development pipeline
- `workflow-security-review.json` - Security audit workflow

### 4. Monitor Execution Status

Check the status of running and recent executions:

```bash
# Show recent executions
agentx status

# Show only active executions
agentx status --active

# Show more history
agentx status --limit 50
```

## Dashboard Features

The web dashboard provides:

### Force-Directed Graph
- Visual representation of all agents and their relationships
- Color-coded by risk level (green=low, yellow=medium, red=high)
- Profile indicators (blue=safe, yellow=balanced, purple=power)
- Pulse animations when agents are active

### Live Activity Feed
- Real-time stream of agent dispatches and completions
- Timestamps for all events
- Click agent IDs to highlight in graph
- Auto-scrolling feed (max 35 items)

### Agent List Panel
- Search and filter agents by:
  - Keywords (role, tags, capabilities)
  - Risk level (low, medium, high)
  - Access profile (safe, balanced, power)
- Click any agent to see detailed information

### API Endpoints

The dashboard exposes REST APIs for integration:

- `GET /api/agents` - List all agents
- `GET /api/profiles` - List access profiles
- `GET /api/graph` - Get graph data (nodes + edges)
- `GET /api/events` - Server-Sent Events stream
- `GET /api/executions` - Recent execution history
- `GET /api/executions/active` - Currently running executions
- `POST /api/execute` - Trigger agent execution
- `POST /api/simulation/toggle` - Toggle simulation mode

## Architect Workflow Examples

### Example 1: Design Review Collaboration

```bash
# Terminal 1: Start dashboard
agentx serve --no-simulation

# Terminal 2: Execute architecture review workflow
agentx run repo-auditor "Analyze current codebase architecture and identify improvement opportunities" --watch
agentx run api-designer "Propose API design improvements based on audit findings" --watch
agentx run documentation-specialist "Update architecture documentation" --watch
```

Watch the dashboard as each agent completes and the next begins!

### Example 2: Full-Stack Feature Development

```bash
# Execute complete feature workflow
agentx workflow --file examples/workflow-feature-dev.json

# Monitor progress in dashboard and CLI
agentx status --active
```

### Example 3: Parallel Investigation

```bash
# Run multiple agents concurrently to investigate different areas
agentx workflow --file my-parallel-investigation.json --parallel
```

Example parallel workflow:
```json
{
  "name": "Parallel Investigation",
  "steps": [
    {
      "agent_id": "frontend-engineer",
      "task": "Analyze React component performance issues"
    },
    {
      "agent_id": "backend-engineer",
      "task": "Investigate API response times"
    },
    {
      "agent_id": "database-architect",
      "task": "Review database query performance"
    }
  ]
}
```

## Integration with External Systems

### Python API

```python
from agent_tools.runtime import get_runtime
from agent_tools.executor import execute_agent_task

# Execute an agent programmatically
execution_id = execute_agent_task(
    agent_id="backend-engineer",
    task="Implement user authentication",
    metadata={"priority": "high"}
)

# Monitor execution
runtime = get_runtime()
execution = runtime.get_execution(execution_id)
print(f"Status: {execution.status}")
```

### REST API Integration

```bash
# Trigger execution via HTTP
curl -X POST http://localhost:7070/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "qa-engineer",
    "task": "Run integration test suite"
  }'

# Get active executions
curl http://localhost:7070/api/executions/active
```

## Tips for Effective Use

1. **Keep Dashboard Open**: Run `agentx serve` in a dedicated terminal/window to monitor all agent activity

2. **Use Workflows for Repeatable Tasks**: Create JSON workflow files for common task sequences

3. **Watch Long-Running Tasks**: Use `--watch` flag to monitor progress without switching to dashboard

4. **Filter by Profile**: Use dashboard filters to focus on agents with specific risk/access levels

5. **Track History**: Use `agentx status` to review what agents have accomplished

6. **Disable Simulation**: When doing real work, use `--no-simulation` to avoid mixing simulated and real activity

## Architecture

```
┌─────────────┐
│   CLI       │  agentx run / workflow / status
└──────┬──────┘
       │
       v
┌─────────────┐
│  Executor   │  execute_agent_task()
└──────┬──────┘
       │
       v
┌─────────────┐
│  Runtime    │  Event tracking & management
└──────┬──────┘
       │
       v
┌─────────────┐
│  EventBus   │  Pub/sub for real-time events
└──────┬──────┘
       │
       v
┌─────────────┐
│  Dashboard  │  Web UI + SSE streaming
└─────────────┘
```

## Next Steps

- Replace the simulated executor with real AI agent integration (GitHub Copilot, LangChain, etc.)
- Add execution history persistence
- Implement agent result sharing and handoffs
- Add workflow templates for common patterns
- Integrate with CI/CD pipelines

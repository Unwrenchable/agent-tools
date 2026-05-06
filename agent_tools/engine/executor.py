from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from ..providers.router import ProviderRouter
from ..tooling.registry import ToolRegistry
from .loader import AgentManifestLoader
from .logger import ExecutionLogger
from .memory import MemoryAdapter, create_memory_adapter
from .router import AgentRouter

_SUMMARY_MAX_CHARS: int = 500

@dataclass(slots=True)
class ExecutionResult:
    agent_id: str
    provider: str
    output: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    latency_ms: int
    dry_run: bool
    session_id: str | None = None


class AgentExecutor:
    def __init__(
        self,
        repo_root: Path | None = None,
        loader: AgentManifestLoader | None = None,
        router: AgentRouter | None = None,
        tool_registry: ToolRegistry | None = None,
        provider_router: ProviderRouter | None = None,
        logger: ExecutionLogger | None = None,
    ) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._loader = loader or AgentManifestLoader(self._repo_root / "agents")
        self._router = router or AgentRouter()
        self._tool_registry = tool_registry or ToolRegistry.auto_wire()
        self._provider_router = provider_router or ProviderRouter()
        self._logger = logger or ExecutionLogger()

    def run(
        self,
        agent_id: str,
        input_text: str,
        provider_override: str | None = None,
        dry_run: bool = False,
        session_id: str | None = None,
    ) -> ExecutionResult:
        started = perf_counter()
        resolved_session_id = session_id or str(uuid4())
        self._logger.log("session", session_id=resolved_session_id)
        manifests = self._loader.load_agents()

        decision = self._router.route(manifests, input_text, preferred_agent_id=agent_id)
        manifest = manifests[decision.agent_id]
        self._logger.log("route", selected_agent=manifest.id, reason=decision.reason)

        provider = self._provider_router.select_provider(
            routing_tags=manifest.routing_tags,
            preferred_order=manifest.provider_preferences,
            user_preference=provider_override,
        )
        self._logger.log("provider", provider=provider.name)

        tool_plan = self._plan_tool_calls(input_text)
        tool_results: list[dict[str, Any]] = []

        for call in tool_plan:
            tool_name = call["tool"]
            payload = call["input"]
            result = self._tool_registry.invoke(
                tool_name=tool_name,
                payload=payload,
                allowed_tools=manifest.tools_allowed,
                dry_run=dry_run,
            )
            tool_results.append({"tool": tool_name, "result": result})
            self._logger.log("tool", tool=tool_name, dry_run=dry_run)

        memory_adapter = self._build_memory_adapter(manifest.memory_policy)
        base_namespace = str(manifest.memory_policy.get("namespace", manifest.id))
        max_history = int(manifest.memory_policy.get("max_history", 10))

        # Session-scoped namespaces when a caller-supplied session_id is present;
        # flat names otherwise (preserves backward compatibility with no-session calls).
        if session_id is not None:
            agent_namespace = f"{resolved_session_id}:agent:{base_namespace}"
            global_namespace = f"{resolved_session_id}:global"
        else:
            agent_namespace = base_namespace
            global_namespace = "global"

        history = self._load_memory_history(
            adapter=memory_adapter,
            manifest_memory_policy=manifest.memory_policy,
            agent_id=manifest.id,
            agent_namespace=agent_namespace,
            global_namespace=global_namespace,
        )

        cot_context_lines: list[str] = []
        for item in history["global"]:
            cot_context_lines.append(
                f"[GLOBAL] agent={item.get('agent_id')} input={item.get('input')} summary={item.get('summary', '')}"
            )
        for item in history["agent"]:
            cot_context_lines.append(
                f"[LOCAL] input={item.get('input')} summary={item.get('summary', '')}"
            )
        cot_context = "\n".join(cot_context_lines)

        semantic_hits = memory_adapter.search(global_namespace, query=input_text, k=5)
        semantic_lines = [
            f"[RELEVANT] agent={hit.get('agent_id')} summary={hit.get('summary', '')}"
            for hit in semantic_hits
            if hit.get("summary")
        ]
        semantic_context = "\n".join(semantic_lines)

        completion = provider.complete(
            prompt=input_text,
            context={
                "agent_id": manifest.id,
                "role": manifest.role,
                "tools": tool_results,
                "dry_run": dry_run,
                "chain_of_thought": cot_context,
                "semantic_context": semantic_context,
                "session_id": resolved_session_id,
            },
            dry_run=dry_run,
        )
        self._logger.log("completion", provider=provider.name, tokens=completion.get("tokens", 0))

        summary_text = (
            # 'response' is the canonical key; 'content' is the LocalProvider's key.
            completion.get("response") or completion.get("content") or ""
        )[:_SUMMARY_MAX_CHARS]
        memory_adapter.append(
            namespace=agent_namespace,
            value={"agent_id": manifest.id, "input": input_text, "summary": summary_text, "tool_calls": tool_results},
        )
        memory_adapter.append(
            namespace=global_namespace,
            value={"agent_id": manifest.id, "input": input_text, "summary": summary_text, "tool_calls": tool_results},
        )

        latency_ms = int((perf_counter() - started) * 1000)
        self._logger.log("metrics", latency_ms=latency_ms)

        return ExecutionResult(
            agent_id=manifest.id,
            provider=provider.name,
            output=completion,
            tool_calls=tool_results,
            logs=self._logger.to_jsonable(),
            latency_ms=latency_ms,
            dry_run=dry_run,
            session_id=resolved_session_id,
        )

    def _load_memory_history(
        self,
        adapter: MemoryAdapter,
        manifest_memory_policy: dict[str, Any],
        agent_id: str,
        agent_namespace: str | None = None,
        global_namespace: str = "global",
    ) -> dict[str, list[dict[str, Any]]]:
        # agent_namespace and global_namespace are passed in pre-computed by run() because
        # they encode the session-scoping decision (flat vs. "{session_id}:…" prefixed).
        # Passing them explicitly keeps this method free of session-awareness and easy to test.
        max_history = int(manifest_memory_policy.get("max_history", 10))
        use_global = bool(manifest_memory_policy.get("use_global", True))
        use_agent_local = bool(manifest_memory_policy.get("use_agent_local", True))

        history: dict[str, list[dict[str, Any]]] = {"global": [], "agent": []}

        if use_global:
            global_items = adapter.read(namespace=global_namespace)
            history["global"] = global_items[-max_history:]

        if use_agent_local:
            ns = agent_namespace if agent_namespace is not None else str(manifest_memory_policy.get("namespace", agent_id))
            local_items = adapter.read(namespace=ns)
            history["agent"] = local_items[-max_history:]

        return history

    def _build_memory_adapter(self, memory_policy: dict[str, Any]) -> MemoryAdapter:
        adapter = str(memory_policy.get("adapter", "json"))
        return create_memory_adapter(adapter=adapter, root_dir=self._repo_root)

    def _plan_tool_calls(self, input_text: str) -> list[dict[str, Any]]:
        lowered = input_text.lower()
        calls: list[dict[str, Any]] = []

        if "hash" in lowered or "sha256" in lowered:
            calls.append({"tool": "crypto", "input": {"operation": "sha256", "text": input_text}})

        if "read" in lowered or "file" in lowered:
            calls.append({"tool": "filesystem", "input": {"operation": "read", "path": "README.md"}})

        if "http" in lowered or "url" in lowered:
            calls.append({"tool": "http", "input": {"url": "https://example.com", "method": "GET"}})

        if "solana" in lowered:
            calls.append({"tool": "solana", "input": {"operation": "simulate_payment", "amount": 1}})

        return calls

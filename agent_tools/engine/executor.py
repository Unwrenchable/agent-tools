from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from ..providers.router import ProviderRouter
from ..tooling.registry import ToolRegistry
from .loader import AgentManifestLoader
from .logger import ExecutionLogger
from .memory import MemoryAdapter, create_memory_adapter
from .router import AgentRouter


@dataclass(slots=True)
class ExecutionResult:
    agent_id: str
    provider: str
    output: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    latency_ms: int
    dry_run: bool


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
    ) -> ExecutionResult:
        started = perf_counter()
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
        memory_namespace = str(manifest.memory_policy.get("namespace", manifest.id))
        memory_adapter.append(
            namespace=memory_namespace,
            value={"input": input_text, "tool_calls": tool_results},
        )

        completion = provider.complete(
            prompt=input_text,
            context={
                "agent_id": manifest.id,
                "role": manifest.role,
                "tools": tool_results,
                "dry_run": dry_run,
            },
            dry_run=dry_run,
        )
        self._logger.log("completion", provider=provider.name, tokens=completion.get("tokens", 0))

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
        )

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

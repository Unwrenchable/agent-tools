"""Memory Summarizer agent.

Reads recent items from a session-scoped memory namespace, calls the RealAI
provider to compress them into dense bullet summaries, and writes those
summaries back into the same namespace so they are immediately available for
semantic retrieval by subsequent executor calls.

Typical usage::

    from pathlib import Path
    from agent_tools.agents_impl.memory_summarizer_agent import MemorySummarizerAgent

    agent = MemorySummarizerAgent(repo_root=Path.cwd())
    summaries = agent.summarize_session("my-session-id")
    for s in summaries:
        print(s["summary"])
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine.memory import MemoryAdapter, create_memory_adapter
from ..providers.realai import RealAIProvider

_SYSTEM_PROMPT = (
    "You are a Memory Summarization assistant. "
    "Compress the following interaction logs into short, information-dense bullet-point "
    "summaries suitable for semantic retrieval. "
    "Keep each item to one or two sentences. "
    "Preserve key facts, decisions, and outcomes. "
    "Do not include chain-of-thought or internal deliberation."
)

_MAX_INPUT_CHARS = 8_000


class MemorySummarizerAgent:
    """Reads session memory, summarises it via RealAI, and writes results back.

    Args:
        repo_root:           Repository root used for the memory adapter.
        adapter_name:        Memory backend to use.  Defaults to ``"vector"``
                             (in-memory) so tests work without ChromaDB.
                             Pass ``"chroma"`` for persistent storage.
        embeddings_provider: Optional provider with ``.embed()`` for semantic
                             indexing.  Passed through to
                             :func:`~agent_tools.engine.memory.create_memory_adapter`.
        provider:            Optional pre-built :class:`RealAIProvider` instance.
                             Defaults to a freshly constructed one (which will
                             use ``REALAI_API_URL`` / ``REALAI_API_KEY`` env vars).
    """

    def __init__(
        self,
        repo_root: Path,
        adapter_name: str = "vector",
        embeddings_provider: Any | None = None,
        provider: RealAIProvider | None = None,
        memory: MemoryAdapter | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.memory: MemoryAdapter = memory or create_memory_adapter(
            adapter=adapter_name,
            root_dir=repo_root,
            embeddings_provider=embeddings_provider,
        )
        self._provider = provider or RealAIProvider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize_session(
        self,
        session_id: str,
        max_items: int = 200,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Summarise and re-store the global namespace for *session_id*.

        Args:
            session_id: Session whose ``"{session_id}:global"`` namespace to
                        compress.
            max_items:  Maximum number of recent items to read before
                        summarising.
            dry_run:    When *True* the LLM call is skipped; placeholder
                        summaries are written instead.

        Returns:
            A list of ``{"original": dict, "summary": str}`` pairs.
        """
        global_ns = f"{session_id}:global"
        return self.summarize_namespace(global_ns, max_items=max_items, dry_run=dry_run)

    def summarize_namespace(
        self,
        namespace: str,
        max_items: int = 50,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Summarise and re-store items in an arbitrary *namespace*.

        Args:
            namespace: The memory namespace to read from and write to.
            max_items: Cap on how many recent items to feed the model.
            dry_run:   Skip the real LLM call; write placeholder summaries.

        Returns:
            A list of ``{"original": dict, "summary": str}`` pairs.
        """
        items = self.memory.read(namespace=namespace, limit=max_items)
        if not items:
            return []

        prompt_body = self._build_prompt_body(items)
        user_prompt = (
            f"Summarize the following logs into short bullet summaries:\n\n{prompt_body}"
        )

        completion = self._provider.complete(
            prompt=user_prompt,
            context={"role": _SYSTEM_PROMPT},
            dry_run=dry_run,
        )
        response = completion.get("response", "") or ""

        summary_lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
        return self._write_summaries(namespace=namespace, items=items, summary_lines=summary_lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt_body(self, items: list[dict[str, Any]]) -> str:
        """Build a text block from *items* trimmed to ``_MAX_INPUT_CHARS``."""
        lines: list[str] = []
        for item in items:
            agent = item.get("agent_id", "unknown")
            inp = str(item.get("input", ""))
            summary = str(item.get("summary", ""))
            lines.append(f"agent={agent}\ninput={inp}\nsummary={summary}\n---")
        body = "\n".join(lines)
        return body[-_MAX_INPUT_CHARS:]

    def _write_summaries(
        self,
        namespace: str,
        items: list[dict[str, Any]],
        summary_lines: list[str],
    ) -> list[dict[str, Any]]:
        """Pair *items* with *summary_lines* and write results back to memory."""
        results: list[dict[str, Any]] = []
        n = min(len(items), len(summary_lines)) if summary_lines else 0

        for i in range(n):
            item = items[i]
            summary_text = summary_lines[i]
            self.memory.append(
                namespace=namespace,
                value={
                    "agent_id": item.get("agent_id"),
                    "input": item.get("input"),
                    "summary": summary_text,
                    "source": "memory_summarizer",
                },
            )
            results.append({"original": item, "summary": summary_text})

        # Items beyond the summary lines (model produced fewer lines): write
        # them through with the original summary truncated as a best-effort.
        for item in items[n:]:
            fallback = str(item.get("summary", ""))[:200] or "(no summary)"
            self.memory.append(
                namespace=namespace,
                value={
                    "agent_id": item.get("agent_id"),
                    "input": item.get("input"),
                    "summary": fallback,
                    "source": "memory_summarizer",
                },
            )
            results.append({"original": item, "summary": fallback})

        return results

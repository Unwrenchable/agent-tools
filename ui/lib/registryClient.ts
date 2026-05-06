// ─── Registry client helpers ──────────────────────────────────────────────────
//
// Fetches agent definitions from the running registry service.
// REGISTRY_URL must point at the base URL of the registry (e.g.
// http://localhost:4000 or https://realai-registry.onrender.com).

/** Mirrors AgentRecord from registry/src/types.ts — kept in sync manually. */
export interface AgentRecord {
  id: string;
  name: string;
  description?: string;
  repo: string;
  path: string;
  manifest: {
    id?: string;
    name?: string;
    description?: string;
    prompt?: string;
    [key: string]: unknown;
  };
  type: "manifest" | "prompt" | "embedded" | "npc" | "persona";
  lastUpdated: string;
}

function requireRegistryUrl(): string {
  const value = process.env["REGISTRY_URL"];
  if (!value) {
    throw new Error(
      "Missing required environment variable: REGISTRY_URL. " +
        "Set it to the base URL of the running registry service.",
    );
  }
  return value.replace(/\/$/, "");
}

/**
 * Fetch a single agent record by id.
 * Throws with a descriptive message when the agent is not found (404)
 * or on any other HTTP error.
 */
export async function fetchAgent(id: string): Promise<AgentRecord> {
  const base = requireRegistryUrl();
  const res = await fetch(`${base}/v1/agents/${encodeURIComponent(id)}`);

  if (res.status === 404) {
    throw new Error(`Agent not found in registry: "${id}"`);
  }
  if (!res.ok) {
    throw new Error(
      `Registry returned HTTP ${res.status} for agent "${id}": ${await res.text()}`,
    );
  }

  return res.json() as Promise<AgentRecord>;
}

/**
 * Fetch multiple agent records in parallel.
 * Returns an array in the same order as the input ids.
 */
export async function fetchAgents(ids: string[]): Promise<AgentRecord[]> {
  return Promise.all(ids.map((id) => fetchAgent(id)));
}

/**
 * Build a system prompt for a given agent.
 *
 * Priority:
 *   1. agent.manifest.prompt — use verbatim if present.
 *   2. Synthesise from name + description + type + repo + path.
 */
export function buildSystemPrompt(agent: AgentRecord): string {
  if (agent.manifest.prompt) {
    return agent.manifest.prompt;
  }

  const lines: string[] = [
    `You are ${agent.name}.`,
  ];

  if (agent.description) {
    lines.push(agent.description);
  }

  lines.push(
    `Agent type: ${agent.type}`,
    `Source: ${agent.repo} / ${agent.path}`,
  );

  return lines.join("\n");
}

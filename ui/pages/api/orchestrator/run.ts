// ─── /api/orchestrator/run ────────────────────────────────────────────────────
//
// Runs one or more agents in parallel against the same prompt and returns
// a ranked list of results with latency measurements.
//
// Request body (JSON):
//   {
//     agentIds: string[];   // one or more registry agent IDs
//     prompt:   string;     // the user turn to send to each agent
//     model?:   string;     // optional model override
//   }
//
// Response body (JSON):
//   {
//     results: Array<{
//       agentId:   string;
//       agentName: string;
//       content:   string;
//       latencyMs: number;
//       error?:    string;   // present only when the agent call failed
//     }>
//   }

import type { NextApiRequest, NextApiResponse } from "next";
import { chatCompletion, extractContent } from "@/lib/realaiClient";
import { fetchAgents, buildSystemPrompt } from "@/lib/registryClient";

interface OrchestratorRequest {
  agentIds: string[];
  prompt: string;
  model?: string;
}

interface AgentResult {
  agentId: string;
  agentName: string;
  content: string;
  latencyMs: number;
  error?: string;
}

interface OrchestratorResponse {
  results: AgentResult[];
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<OrchestratorResponse | { error: string }>,
): Promise<void> {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const body = req.body as Partial<OrchestratorRequest>;

  if (
    !Array.isArray(body.agentIds) ||
    body.agentIds.length === 0 ||
    typeof body.prompt !== "string" ||
    body.prompt.trim() === ""
  ) {
    res.status(400).json({
      error: "Request body must include non-empty `agentIds` array and `prompt` string.",
    });
    return;
  }

  const { agentIds, prompt, model } = body as OrchestratorRequest;

  // Fetch all agent definitions from the registry (fail fast if any missing).
  let agents;
  try {
    agents = await fetchAgents(agentIds);
  } catch (err) {
    res.status(502).json({
      error: `Failed to fetch agents from registry: ${String(err)}`,
    });
    return;
  }

  // Run all agents in parallel; capture errors per-agent so one failure
  // doesn't abort the entire orchestration.
  const results: AgentResult[] = await Promise.all(
    agents.map(async (agent): Promise<AgentResult> => {
      const start = Date.now();
      try {
        const systemPrompt = buildSystemPrompt(agent);
        const completion = await chatCompletion(
          [
            { role: "system", content: systemPrompt },
            { role: "user", content: prompt },
          ],
          { model },
        );
        const content = extractContent(completion);
        return {
          agentId: agent.id,
          agentName: agent.name,
          content,
          latencyMs: Date.now() - start,
        };
      } catch (err) {
        return {
          agentId: agent.id,
          agentName: agent.name,
          content: "",
          latencyMs: Date.now() - start,
          error: String(err),
        };
      }
    }),
  );

  res.status(200).json({ results });
}

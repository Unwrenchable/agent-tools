// ─── /api/playground/run ─────────────────────────────────────────────────────
//
// Runs a single agent against a user prompt in the playground.
//
// Request body (JSON):
//   {
//     agentId: string;    // registry agent ID
//     prompt:  string;    // the user turn to send
//     model?:  string;    // optional model override
//   }
//
// Response body (JSON):
//   {
//     agentId:    string;
//     agentName:  string;
//     content:    string;
//     latencyMs:  number;
//     model:      string;
//   }

import type { NextApiRequest, NextApiResponse } from "next";
import { chatCompletion, extractContent } from "@/lib/realaiClient";
import { fetchAgent, buildSystemPrompt } from "@/lib/registryClient";

interface PlaygroundRequest {
  agentId: string;
  prompt: string;
  model?: string;
}

interface PlaygroundResponse {
  agentId: string;
  agentName: string;
  content: string;
  latencyMs: number;
  model: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<PlaygroundResponse | { error: string }>,
): Promise<void> {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const body = req.body as Partial<PlaygroundRequest>;

  if (
    typeof body.agentId !== "string" ||
    body.agentId.trim() === "" ||
    typeof body.prompt !== "string" ||
    body.prompt.trim() === ""
  ) {
    res.status(400).json({
      error: "Request body must include non-empty `agentId` and `prompt` strings.",
    });
    return;
  }

  const { agentId, prompt, model } = body as PlaygroundRequest;

  // Resolve the agent definition from the registry.
  let agent;
  try {
    agent = await fetchAgent(agentId);
  } catch (err) {
    const message = String(err);
    const status = message.includes("not found") ? 404 : 502;
    res.status(status).json({ error: message });
    return;
  }

  const systemPrompt = buildSystemPrompt(agent);
  const resolvedModel =
    model ?? process.env["REALAI_MODEL"] ?? "realai-psi";

  const start = Date.now();
  let completion;
  try {
    completion = await chatCompletion(
      [
        { role: "system", content: systemPrompt },
        { role: "user", content: prompt },
      ],
      { model },
    );
  } catch (err) {
    res.status(502).json({
      error: `RealAI API call failed: ${String(err)}`,
    });
    return;
  }

  const latencyMs = Date.now() - start;
  const content = extractContent(completion);

  res.status(200).json({
    agentId: agent.id,
    agentName: agent.name,
    content,
    latencyMs,
    model: completion.model ?? resolvedModel,
  });
}

// ─── REST API routes ──────────────────────────────────────────────────────────

import express, { type Request, type Response, type Router } from "express";
import { registry } from "../registry.js";
import { githubWebhook } from "./webhook.js";

export function buildRouter(): Router {
  const router = express.Router();

  // ── health ───────────────────────────────────────────────────────────────

  router.get("/health", (_req: Request, res: Response) => {
    res.json({
      status: "ok",
      agents: registry.size,
      lastScan: registry.lastScan,
    });
  });

  // ── agents ────────────────────────────────────────────────────────────────

  /** List all agents; supports optional ?q=<query> for full-text search. */
  router.get("/v1/agents", (req: Request, res: Response) => {
    const q = typeof req.query["q"] === "string" ? req.query["q"].trim() : "";
    const agents = q ? registry.search(q) : registry.all();
    res.json(agents);
  });

  /** Get a single agent by id. */
  router.get("/v1/agents/:id", (req: Request, res: Response) => {
    const agent = registry.getById(req.params["id"] ?? "");
    if (!agent) {
      res.status(404).json({ error: "Agent not found" });
      return;
    }
    res.json(agent);
  });

  // ── webhook ───────────────────────────────────────────────────────────────

  // githubWebhook performs per-IP rate limiting before HMAC authorization.
  // express.json() is applied first to make req.body available.
  router.post(
    "/webhook/github",
    express.json({ type: "*/*" }),
    githubWebhook,
  );

  return router;
}

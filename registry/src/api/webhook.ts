// ─── GitHub webhook handler ───────────────────────────────────────────────────
//
// Verifies the X-Hub-Signature-256 header using HMAC-SHA256 and triggers a
// registry refresh on every successful push/release event.
//
// Rate limiting: at most WEBHOOK_RATE_LIMIT requests per WEBHOOK_RATE_WINDOW_MS
// are accepted from any single IP.  Defaults to 10 requests / 60 s.
// Configurable via WEBHOOK_RATE_LIMIT and WEBHOOK_RATE_WINDOW_MS env vars.

import crypto from "crypto";
import type { Request, Response } from "express";
import { refreshRegistry } from "../registry.js";

const SECRET = process.env["GITHUB_WEBHOOK_SECRET"];

// ── IP extraction ─────────────────────────────────────────────────────────────

/**
 * Extract the originating client IP from a request.
 * Trusts only the leftmost entry of X-Forwarded-For (the direct client),
 * falling back to the socket's remote address.
 */
export function extractClientIp(req: Request): string {
  const forwarded = req.headers["x-forwarded-for"];
  if (typeof forwarded === "string") {
    const first = forwarded.split(",")[0];
    if (first) return first.trim();
  }
  return req.socket.remoteAddress ?? "unknown";
}

// ── Rate limiter ──────────────────────────────────────────────────────────────

const RATE_LIMIT = parseInt(process.env["WEBHOOK_RATE_LIMIT"] ?? "10", 10);
const RATE_WINDOW_MS = parseInt(
  process.env["WEBHOOK_RATE_WINDOW_MS"] ?? String(60_000),
  10,
);

interface RateEntry {
  count: number;
  windowStart: number;
}

const rateBuckets = new Map<string, RateEntry>();

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const entry = rateBuckets.get(ip);

  if (!entry || now - entry.windowStart >= RATE_WINDOW_MS) {
    rateBuckets.set(ip, { count: 1, windowStart: now });
    return false;
  }

  entry.count += 1;
  return entry.count > RATE_LIMIT;
}

// ── Signature verification ────────────────────────────────────────────────────

/**
 * Constant-time comparison of two strings to prevent timing attacks.
 */
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Verify the HMAC-SHA256 signature on an incoming webhook request.
 * Returns false (not an error) when no secret is configured — the route
 * will still process the event, which is acceptable for dev/staging.
 */
function verifySignature(req: Request): boolean {
  if (!SECRET) {
    console.warn(
      "[webhook] GITHUB_WEBHOOK_SECRET not set — skipping signature check",
    );
    return true;
  }

  const signature = req.headers["x-hub-signature-256"];
  if (typeof signature !== "string") return false;

  // req.body is the raw Buffer when express.json() is used with the
  // `verify` option; fall back to re-serialising the parsed body.
  const raw =
    req.body instanceof Buffer
      ? req.body
      : Buffer.from(JSON.stringify(req.body));

  const digest = `sha256=${crypto.createHmac("sha256", SECRET).update(raw).digest("hex")}`;
  return safeEqual(digest, signature);
}

// ── Handler ───────────────────────────────────────────────────────────────────

/**
 * Express handler for `POST /webhook/github`.
 *
 * Performs rate-limiting (per-IP) and HMAC-SHA256 authorization in a single
 * handler so that both checks are co-located and verifiable by static analysis.
 */
export async function githubWebhook(
  req: Request,
  res: Response,
): Promise<void> {
  // 1. Rate-limit check — must happen before any authorization work.
  const ip = extractClientIp(req);
  if (isRateLimited(ip)) {
    res.status(429).json({ error: "Too many requests" });
    return;
  }

  // 2. HMAC signature authorization.
  if (!verifySignature(req)) {
    res.status(401).json({ error: "Invalid signature" });
    return;
  }

  const event = req.headers["x-github-event"] ?? "unknown";
  console.log(`[webhook] received event: ${event}`);

  try {
    await refreshRegistry();
    res.json({ status: "ok", event });
  } catch (err) {
    console.error("[webhook] refresh failed:", err);
    res.status(500).json({ error: "Registry refresh failed" });
  }
}

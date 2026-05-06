// ─── Agent detectors — one per source format ─────────────────────────────────
//
// Each detector receives the raw text content of a file and returns either
// an array of RawAgentManifest objects (when one or more agents are found) or
// an empty array (when none are found).
//
// Detectors are pure functions — they have no side-effects and do not call the
// GitHub API.  All I/O happens in scanner.ts; detectors only parse content.

import type { AgentScanHit, AgentSourceType, RawAgentManifest } from "./types.js";
import { slugify } from "./utils.js";

// ── helpers ──────────────────────────────────────────────────────────────────

/** Try to JSON-parse a string; return null on failure. */
function tryParseJSON(raw: string): RawAgentManifest | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      return value as RawAgentManifest;
    }
    return null;
  } catch {
    return null;
  }
}

/** Build a slug from repo + path when a manifest has no id field. */
function derivedId(repo: string, path: string): string {
  return slugify(`${repo}/${path}`);
}

// ── manifest detectors ───────────────────────────────────────────────────────

/**
 * Matches:
 *   *.agentx
 *   agent.json
 *   agents/*.json
 *   agents/*.agentx
 */
export function isManifestFile(filePath: string): boolean {
  const lower = filePath.toLowerCase();
  const name = lower.split("/").pop() ?? "";
  const dir = lower.split("/").slice(0, -1).join("/");

  return (
    name.endsWith(".agentx") ||
    name === "agent.json" ||
    ((name.endsWith(".json") || name.endsWith(".agentx")) &&
      /(?:^|[/\\])agents$/.test(dir))
  );
}

export function detectManifest(
  content: string,
  repo: string,
  path: string,
): AgentScanHit[] {
  const manifest = tryParseJSON(content);
  if (!manifest) return [];
  return [{ repo, path, type: "manifest", manifest }];
}

// ── prompt-based detectors ───────────────────────────────────────────────────

/**
 * Extension → type mapping for prompt-based agent files.
 */
const PROMPT_EXTENSIONS: Record<string, AgentSourceType> = {
  ".prompt": "prompt",
  ".persona": "persona",
  ".npc": "npc",
  ".overseer": "prompt",
};

export function isPromptFile(filePath: string): AgentSourceType | null {
  const lower = filePath.toLowerCase();
  for (const [ext, type] of Object.entries(PROMPT_EXTENSIONS)) {
    if (lower.endsWith(ext)) return type;
  }
  return null;
}

export function detectPrompt(
  content: string,
  repo: string,
  path: string,
  type: AgentSourceType,
): AgentScanHit[] {
  if (!content.trim()) return [];

  // Attempt to extract structured frontmatter or fall back to raw text.
  const manifest = tryParseJSON(content) ?? buildPromptManifest(content, path);
  return [{ repo, path, type, manifest }];
}

/**
 * Build a minimal manifest from a plain-text prompt file.
 * Tries to extract a "name:" or "# Name" heading from the first few lines.
 */
function buildPromptManifest(
  content: string,
  path: string,
): RawAgentManifest {
  const lines = content.split(/\r?\n/);
  let name: string | undefined;

  for (const line of lines.slice(0, 10)) {
    const headingMatch = /^#\s+(.+)/.exec(line);
    if (headingMatch) {
      name = headingMatch[1].trim();
      break;
    }
    const kvMatch = /^name\s*[:=]\s*(.+)/i.exec(line);
    if (kvMatch) {
      name = kvMatch[1].trim();
      break;
    }
  }

  const baseName = (path.split("/").pop() ?? path).replace(/\.[^.]+$/, "");

  return {
    name: name ?? baseName,
    prompt: content,
  };
}

// ── embedded agent detector ───────────────────────────────────────────────────

/** Matches source files that may contain embedded agent blocks. */
export function isEmbeddedSourceFile(filePath: string): boolean {
  return /\.(tsx?|jsx?)$/i.test(filePath);
}

/**
 * Extracts zero or more /* agent:start … agent:end *\/ blocks from source
 * code.  Each block must contain valid JSON.
 *
 * The split-based approach avoids backtracking on deeply-nested content that
 * would otherwise risk ReDoS with a greedy/lazy [\s\S]* pattern.
 */
export function detectEmbedded(
  content: string,
  repo: string,
  path: string,
): AgentScanHit[] {
  const hits: AgentScanHit[] = [];

  const START_MARKER = "/* agent:start";
  const END_MARKER = "agent:end */";

  let searchFrom = 0;
  while (searchFrom < content.length) {
    const startIdx = content.indexOf(START_MARKER, searchFrom);
    if (startIdx === -1) break;

    const bodyStart = startIdx + START_MARKER.length;
    const endIdx = content.indexOf(END_MARKER, bodyStart);
    if (endIdx === -1) break;

    const json = content.slice(bodyStart, endIdx).trim();
    const manifest = tryParseJSON(json);
    if (manifest) {
      hits.push({ repo, path, type: "embedded", manifest });
    }

    searchFrom = endIdx + END_MARKER.length;
  }

  return hits;
}

// ── normaliser ───────────────────────────────────────────────────────────────

/**
 * Convert a raw scan hit into a fully-normalised AgentRecord-compatible shape
 * by filling in missing id / name fields.
 */
export function normalise(
  hit: AgentScanHit,
): Omit<AgentScanHit, "manifest"> & { manifest: RawAgentManifest & { id: string; name: string } } {
  const id =
    typeof hit.manifest.id === "string" && hit.manifest.id.length > 0
      ? hit.manifest.id
      : derivedId(hit.repo, hit.path);

  const name =
    typeof hit.manifest.name === "string" && hit.manifest.name.length > 0
      ? hit.manifest.name
      : id;

  return {
    ...hit,
    manifest: { ...hit.manifest, id, name },
  };
}

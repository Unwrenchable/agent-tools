// ─── Shared types for the Universal Agent Scanner ───────────────────────────

/** The format in which an agent definition was found. */
export type AgentSourceType =
  | "manifest"
  | "prompt"
  | "embedded"
  | "npc"
  | "persona";

/**
 * The raw contents of an agent manifest as parsed from its source file.
 * We keep it open (index signature) because every format is different.
 */
export interface RawAgentManifest {
  id?: string;
  name?: string;
  description?: string;
  prompt?: string;
  [key: string]: unknown;
}

/**
 * The canonical, normalised representation of a discovered agent, suitable
 * for storage in the registry and consumption by the dashboard.
 */
export interface AgentRecord {
  /** Stable unique identifier derived from repo + path when the manifest has none. */
  id: string;
  /** Human-readable display name. */
  name: string;
  /** Optional one-paragraph summary of what the agent does. */
  description?: string;
  /** The GitHub repo slug where this agent was found (e.g. "Unwrenchable/realai"). */
  repo: string;
  /** Repo-relative path to the source file (e.g. "agents/router.agent.json"). */
  path: string;
  /** The raw, unparsed manifest payload kept for full fidelity. */
  manifest: RawAgentManifest;
  /** How the agent definition was encoded in the source file. */
  type: AgentSourceType;
  /** ISO-8601 timestamp of the file's last commit, or scan time as fallback. */
  lastUpdated: string;
}

/**
 * An intermediate hit produced by a detector before full normalisation.
 * Carries everything needed to build an AgentRecord.
 */
export interface AgentScanHit {
  repo: string;
  path: string;
  type: AgentSourceType;
  manifest: RawAgentManifest;
  /** ISO-8601 timestamp, filled in by the GitHub scanner when available. */
  lastUpdated?: string;
}

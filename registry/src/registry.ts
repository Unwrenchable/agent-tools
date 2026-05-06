// ─── In-memory registry service ──────────────────────────────────────────────
//
// The registry is the single source of truth for the dashboard.  It holds the
// current set of AgentRecords in memory and exposes query helpers.  Call
// `populate()` once at startup (or on demand) to (re-)scan all repos.

import { scanAllRepos } from "./scanner.js";
import type { AgentRecord, AgentSourceType } from "./types.js";

export class AgentRegistry {
  private records: Map<string, AgentRecord> = new Map();
  private lastScanAt: Date | null = null;

  // ── population ────────────────────────────────────────────────────────────

  /**
   * Scan all configured repos and replace the current registry contents.
   * Safe to call multiple times — each call discards the previous state.
   */
  async populate(): Promise<void> {
    const fresh = await scanAllRepos();
    this.records.clear();
    for (const record of fresh) {
      // When two records share the same derived id (e.g. two repos both have
      // agent.json at root), build a collision key that preserves the
      // original id and disambiguates by full repo + path.
      const key = this.records.has(record.id)
        ? `${record.id}--${record.repo}/${record.path}`
        : record.id;
      this.records.set(key, { ...record, id: key });
    }
    this.lastScanAt = new Date();
    console.log(
      `[registry] populated ${this.records.size} agent(s) at ${this.lastScanAt.toISOString()}`,
    );
  }

  // ── queries ───────────────────────────────────────────────────────────────

  /** Return every agent in the registry. */
  all(): AgentRecord[] {
    return [...this.records.values()];
  }

  /** Find an agent by its exact id. */
  getById(id: string): AgentRecord | undefined {
    return this.records.get(id);
  }

  /** Return all agents discovered from a specific repo slug. */
  byRepo(repoSlug: string): AgentRecord[] {
    return this.all().filter((r) => r.repo === repoSlug);
  }

  /** Return all agents of a specific source type. */
  byType(type: AgentSourceType): AgentRecord[] {
    return this.all().filter((r) => r.type === type);
  }

  /**
   * Case-insensitive full-text search across id, name, description, and repo.
   */
  search(query: string): AgentRecord[] {
    const q = query.toLowerCase();
    return this.all().filter(
      (r) =>
        r.id.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.repo.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q),
    );
  }

  // ── metadata ──────────────────────────────────────────────────────────────

  /** ISO-8601 timestamp of the last successful scan, or null if never run. */
  get lastScan(): string | null {
    return this.lastScanAt?.toISOString() ?? null;
  }

  /** Total number of agents currently loaded. */
  get size(): number {
    return this.records.size;
  }

  /**
   * Serialise the full registry to a plain JSON object suitable for API
   * responses or dashboard consumption.
   */
  toJSON(): { agents: AgentRecord[]; lastScan: string | null; total: number } {
    return {
      agents: this.all(),
      lastScan: this.lastScan,
      total: this.size,
    };
  }
}

/** Singleton instance shared across the process. */
export const registry = new AgentRegistry();

/**
 * Convenience function for use by the webhook handler and other callers that
 * need to trigger a registry refresh without accessing the class directly.
 */
export async function refreshRegistry(): Promise<void> {
  await registry.populate();
}

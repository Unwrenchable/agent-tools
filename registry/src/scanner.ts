// ─── Main scanner — orchestrates detectors across all configured repos ────────

import { config } from "./config.js";
import {
  detectEmbedded,
  detectManifest,
  detectPrompt,
  isEmbeddedSourceFile,
  isManifestFile,
  isPromptFile,
  normalise,
} from "./detectors.js";
import { fetchFileContent } from "./github/client.js";
import { fetchLastUpdated, walkRepoFiles } from "./github/scanner.js";
import type { AgentRecord, AgentScanHit } from "./types.js";

// ── concurrency limiter ───────────────────────────────────────────────────────

/**
 * Run `tasks` with at most `limit` in-flight at a time.
 * Returns results in the same order as the input array.
 */
async function pLimit<T>(
  tasks: Array<() => Promise<T>>,
  limit: number,
): Promise<T[]> {
  const results: T[] = new Array(tasks.length);
  let index = 0;

  async function worker(): Promise<void> {
    while (index < tasks.length) {
      const i = index++;
      results[i] = await tasks[i]();
    }
  }

  const workers = Array.from({ length: Math.min(limit, tasks.length) }, () =>
    worker(),
  );
  await Promise.all(workers);
  return results;
}

// ── per-file scanning ─────────────────────────────────────────────────────────

/**
 * Fetch a single file and run the appropriate detector(s) against it.
 * Returns zero or more scan hits.
 */
async function scanFile(
  repoSlug: string,
  filePath: string,
): Promise<AgentScanHit[]> {
  let content: string;

  try {
    content = await fetchFileContent(repoSlug, filePath);
  } catch {
    // Unreadable / too large / binary — skip silently.
    return [];
  }

  const promptType = isPromptFile(filePath);

  if (isManifestFile(filePath)) {
    return detectManifest(content, repoSlug, filePath);
  }

  if (promptType !== null) {
    return detectPrompt(content, repoSlug, filePath, promptType);
  }

  if (isEmbeddedSourceFile(filePath)) {
    return detectEmbedded(content, repoSlug, filePath);
  }

  return [];
}

// ── repo scanner ─────────────────────────────────────────────────────────────

/**
 * Walk all files in a single repo and return normalised AgentRecord objects.
 */
export async function scanRepo(repoSlug: string): Promise<AgentRecord[]> {
  const files = await walkRepoFiles(repoSlug);

  const tasks = files.map(
    (file) => () => scanFile(repoSlug, file.path),
  );

  const hitGroups = await pLimit(tasks, config.concurrency);
  const allHits = hitGroups.flat();

  // Enrich with last-updated timestamps in a second pass (also concurrency-limited).
  const timestampTasks = allHits.map(
    (hit) => async (): Promise<AgentScanHit> => {
      const lastUpdated =
        hit.lastUpdated ?? (await fetchLastUpdated(repoSlug, hit.path));
      return { ...hit, lastUpdated };
    },
  );

  const enrichedHits = await pLimit(timestampTasks, config.concurrency);

  return enrichedHits.map(hitToRecord);
}

// ── full multi-repo scan ──────────────────────────────────────────────────────

/**
 * Scan all repos listed in {@link config.repos} and return every discovered
 * agent as a normalised {@link AgentRecord}.
 *
 * Repos are scanned sequentially to avoid rate-limiting; within each repo
 * individual file fetches are concurrency-limited.
 */
export async function scanAllRepos(): Promise<AgentRecord[]> {
  const allRecords: AgentRecord[] = [];

  for (const repoSlug of config.repos) {
    console.log(`[scanner] scanning ${repoSlug} …`);
    try {
      const records = await scanRepo(repoSlug);
      console.log(`[scanner]   found ${records.length} agent(s)`);
      allRecords.push(...records);
    } catch (err) {
      console.error(
        `[scanner] failed to scan ${repoSlug}:`,
        err instanceof Error ? err.message : err,
      );
    }
  }

  return allRecords;
}

// ── conversion helper ─────────────────────────────────────────────────────────

function hitToRecord(hit: AgentScanHit): AgentRecord {
  const normalised = normalise(hit);

  return {
    id: normalised.manifest.id,
    name: normalised.manifest.name,
    description:
      typeof normalised.manifest.description === "string"
        ? normalised.manifest.description
        : undefined,
    repo: hit.repo,
    path: hit.path,
    manifest: normalised.manifest,
    type: hit.type,
    lastUpdated: hit.lastUpdated ?? new Date().toISOString(),
  };
}

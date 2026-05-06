// ─── Environment-driven configuration ───────────────────────────────────────

/**
 * Repos to scan.  Override at runtime with a comma-separated list in
 * AGENT_SCAN_REPOS, e.g.:
 *   AGENT_SCAN_REPOS="Unwrenchable/realai,Unwrenchable/my-other-repo"
 *
 * Each entry is a full "owner/repo" slug so the scanner is not restricted
 * to a single organisation.
 */
const DEFAULT_REPOS = [
  "Unwrenchable/realai",
  "Unwrenchable/agent-tools",
  "Unwrenchable/atomicfizzcaps",
  "Unwrenchable/overseer-terminal",
];

function parseRepos(raw: string | undefined): string[] {
  if (!raw) return DEFAULT_REPOS;
  return raw
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);
}

export interface Config {
  /** GitHub personal-access token (needs repo read scope). */
  githubToken: string;
  /**
   * List of "owner/repo" slugs to scan.
   * Configurable via AGENT_SCAN_REPOS environment variable.
   */
  repos: string[];
  /** Maximum number of concurrent GitHub API calls. */
  concurrency: number;
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${name}\n` +
        `Set it before running the scanner, e.g.:\n` +
        `  export ${name}=<value>`,
    );
  }
  return value;
}

export const config: Config = {
  githubToken: requireEnv("GITHUB_TOKEN"),
  repos: parseRepos(process.env["AGENT_SCAN_REPOS"]),
  concurrency: parseInt(process.env["AGENT_SCAN_CONCURRENCY"] ?? "4", 10),
};

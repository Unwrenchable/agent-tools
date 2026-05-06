// ─── Environment-driven configuration ───────────────────────────────────────

/**
 * Repos to scan.
 *
 * Two env-var conventions are supported so the same image works on both
 * Render (which sets GITHUB_OWNER + GITHUB_REPOS) and local dev
 * (which may set the combined AGENT_SCAN_REPOS instead):
 *
 *   Render style:
 *     GITHUB_OWNER=Unwrenchable
 *     GITHUB_REPOS=realai,agent-tools,atomicfizzcaps,overseer-terminal
 *
 *   Combined style (takes precedence when set):
 *     AGENT_SCAN_REPOS=Unwrenchable/realai,Unwrenchable/agent-tools
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

/**
 * Build the list of "owner/repo" slugs from either the combined
 * AGENT_SCAN_REPOS variable or the Render-style pair GITHUB_OWNER +
 * GITHUB_REPOS.
 */
function resolveRepos(): string[] {
  if (process.env["AGENT_SCAN_REPOS"]) {
    return parseRepos(process.env["AGENT_SCAN_REPOS"]);
  }

  const owner = process.env["GITHUB_OWNER"];
  const names = process.env["GITHUB_REPOS"];
  if (owner && names) {
    return names
      .split(",")
      .map((n) => `${owner}/${n.trim()}`)
      .filter((s) => s.length > owner.length + 1);
  }

  return DEFAULT_REPOS;
}

export interface Config {
  /** GitHub personal-access token (needs repo read scope). */
  githubToken: string;
  /**
   * List of "owner/repo" slugs to scan.
   * Configurable via AGENT_SCAN_REPOS or GITHUB_OWNER + GITHUB_REPOS.
   */
  repos: string[];
  /** Maximum number of concurrent GitHub API calls. */
  concurrency: number;
  /** HTTP port for the registry API server (0 = disabled / scan-only mode). */
  port: number;
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
  repos: resolveRepos(),
  concurrency: parseInt(process.env["AGENT_SCAN_CONCURRENCY"] ?? "4", 10),
  port: parseInt(process.env["PORT"] ?? "0", 10),
};

// ─── Repo file walker via GitHub Contents API ────────────────────────────────

import { githubRequest } from "./client.js";

/** Metadata for a single file entry returned by the Contents API. */
export interface GitHubFile {
  /** Full "owner/repo" slug. */
  repo: string;
  /** Repo-relative path (no leading slash). */
  path: string;
  /** Base name (last segment of path). */
  name: string;
  /** Whether this entry is a file or a directory. */
  type: "file" | "dir";
  /** ISO-8601 string of the most recent commit to this path, if fetched. */
  lastUpdated?: string;
}

interface ContentItem {
  name: string;
  path: string;
  type: "file" | "dir" | "symlink" | "submodule";
}

/**
 * Recursively walk every file in a repository, returning a flat list of
 * {@link GitHubFile} entries.  Symlinks and submodules are silently skipped.
 *
 * Uses the GitHub Contents API which caps directory listings at 1 000 entries.
 * For enormous repos use the Git Trees API instead — replace this function
 * with `walkRepoViaTree` if needed.
 *
 * @param repoSlug  Full "owner/repo" slug
 * @param dirPath   Starting path inside the repo (empty string = root)
 */
export async function walkRepoFiles(
  repoSlug: string,
  dirPath = "",
): Promise<GitHubFile[]> {
  const encodedPath = dirPath ? `/${dirPath}` : "";
  let items: ContentItem[];

  try {
    items = await githubRequest<ContentItem[]>(
      `/repos/${repoSlug}/contents${encodedPath}`,
    );
  } catch (err) {
    // A 404 most likely means the path doesn't exist; return empty gracefully.
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("404")) return [];
    throw err;
  }

  if (!Array.isArray(items)) {
    // The API returns an object instead of an array when path is a single file.
    return [];
  }

  const results: GitHubFile[] = [];

  for (const item of items) {
    if (item.type === "file") {
      results.push({
        repo: repoSlug,
        path: item.path,
        name: item.name,
        type: "file",
      });
    } else if (item.type === "dir") {
      const children = await walkRepoFiles(repoSlug, item.path);
      results.push(...children);
    }
    // symlinks and submodules are intentionally ignored
  }

  return results;
}

/**
 * Fetch the ISO-8601 timestamp of the most recent commit that touched a file.
 * Returns `undefined` when the commits endpoint returns nothing useful (e.g.
 * empty repo or no history yet).
 */
export async function fetchLastUpdated(
  repoSlug: string,
  filePath: string,
): Promise<string | undefined> {
  try {
    const commits = await githubRequest<
      Array<{ commit: { committer: { date: string } } }>
    >(
      `/repos/${repoSlug}/commits?path=${encodeURIComponent(filePath)}&per_page=1`,
    );
    return commits[0]?.commit?.committer?.date;
  } catch {
    return undefined;
  }
}

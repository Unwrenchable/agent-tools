// ─── Authenticated GitHub REST client ───────────────────────────────────────

import fetch from "node-fetch";
import { config } from "../config.js";

const GITHUB_API_BASE = "https://api.github.com";

/**
 * Make an authenticated GET request to the GitHub REST API.
 *
 * @param path  API path starting with `/`, e.g. `/repos/owner/repo/contents/`
 * @returns     Parsed JSON response body
 * @throws      Error with status code and body on non-2xx responses
 */
export async function githubRequest<T = unknown>(path: string): Promise<T> {
  const url = `${GITHUB_API_BASE}${path}`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${config.githubToken}`,
      "User-Agent": "realai-registry/1.0",
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API error ${res.status} for ${url}: ${body}`);
  }

  return res.json() as Promise<T>;
}

/**
 * Fetch the raw (decoded) text content of a file from a GitHub repository.
 *
 * @param repoSlug  Full "owner/repo" slug
 * @param filePath  Repo-relative file path
 * @param ref       Git ref (branch, tag, or commit SHA).  Defaults to HEAD.
 */
export async function fetchFileContent(
  repoSlug: string,
  filePath: string,
  ref?: string,
): Promise<string> {
  const refParam = ref ? `?ref=${encodeURIComponent(ref)}` : "";
  const data = await githubRequest<{
    content?: string;
    encoding?: string;
    message?: string;
  }>(`/repos/${repoSlug}/contents/${filePath}${refParam}`);

  if (!data.content) {
    throw new Error(
      `No content field returned for ${repoSlug}/${filePath}. ` +
        (data.message ?? "Unknown reason."),
    );
  }

  if (data.encoding !== "base64") {
    throw new Error(
      `Unexpected encoding "${data.encoding}" for ${repoSlug}/${filePath}`,
    );
  }

  // GitHub returns base64 with newlines; strip them before decoding.
  return Buffer.from(data.content.replace(/\n/g, ""), "base64").toString(
    "utf-8",
  );
}

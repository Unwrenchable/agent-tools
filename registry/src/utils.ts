// ─── Shared utilities ─────────────────────────────────────────────────────────

/**
 * Produce a URL-safe slug from an arbitrary string.
 * Convention matches the project slugify helper: alphanumeric + hyphens only,
 * no consecutive hyphens, no leading/trailing hyphens.
 */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")  // non-alphanumeric → hyphen
    .replace(/-{2,}/g, "-")        // collapse consecutive hyphens
    .replace(/^-|-$/g, "");        // strip leading/trailing hyphens
}

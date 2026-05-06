// ─── Public entry point ───────────────────────────────────────────────────────
//
// Import from this module to use the scanner and registry in other packages:
//
//   import { registry, scanAllRepos, AgentRecord } from "@unwrenchable/agent-registry";
//
// Or run directly as a CLI tool:
//   node dist/index.js

export { config } from "./config.js";
export {
  detectEmbedded,
  detectManifest,
  detectPrompt,
  isEmbeddedSourceFile,
  isManifestFile,
  isPromptFile,
  normalise,
} from "./detectors.js";
export { fetchFileContent } from "./github/client.js";
export { fetchLastUpdated, walkRepoFiles } from "./github/scanner.js";
export { AgentRegistry, refreshRegistry, registry } from "./registry.js";
export { scanAllRepos, scanRepo } from "./scanner.js";
export { slugify } from "./utils.js";
export type {
  AgentRecord,
  AgentScanHit,
  AgentSourceType,
  RawAgentManifest,
} from "./types.js";

// ── Entry point: HTTP server or scan-to-stdout ────────────────────────────────

async function main(): Promise<void> {
  const { config } = await import("./config.js");
  const { registry } = await import("./registry.js");

  if (config.port > 0) {
    // ── HTTP server mode ────────────────────────────────────────────────────
    const { startServer } = await import("./api/server.js");

    console.log("[realai-registry] Starting HTTP server …");
    console.log(`[realai-registry] Repos: ${config.repos.join(", ")}`);

    // Populate the registry before accepting traffic.
    await registry.populate();
    await startServer(config.port);
  } else {
    // ── Scan-to-stdout mode (default / CI) ──────────────────────────────────
    console.log("[realai-registry] Starting Universal Agent Scanner …");
    console.log(`[realai-registry] Repos: ${config.repos.join(", ")}`);

    await registry.populate();

    process.stdout.write(JSON.stringify(registry.toJSON(), null, 2) + "\n");
  }
}

// Detect whether we are the entry-point module using import.meta.url (ESM).
import { fileURLToPath } from "url";

const isMain =
  process.argv[1] != null &&
  process.argv[1] === fileURLToPath(import.meta.url);

if (isMain) {
  main().catch((err: unknown) => {
    console.error("[realai-registry] Fatal error:", err);
    process.exit(1);
  });
}

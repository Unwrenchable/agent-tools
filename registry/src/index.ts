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
export { AgentRegistry, registry } from "./registry.js";
export { scanAllRepos, scanRepo } from "./scanner.js";
export type {
  AgentRecord,
  AgentScanHit,
  AgentSourceType,
  RawAgentManifest,
} from "./types.js";

// ── CLI runner (invoked when this file is the main module) ───────────────────

async function main(): Promise<void> {
  const { registry } = await import("./registry.js");

  console.log("[realai-registry] Starting Universal Agent Scanner …");
  console.log(`[realai-registry] Repos: ${(await import("./config.js")).config.repos.join(", ")}`);

  await registry.populate();

  const output = registry.toJSON();
  process.stdout.write(JSON.stringify(output, null, 2) + "\n");
}

// Detect whether we are the entry-point module in both CJS and ESM contexts.
const isMain =
  process.argv[1] != null &&
  (process.argv[1].endsWith("index.js") || process.argv[1].endsWith("index.ts"));

if (isMain) {
  main().catch((err: unknown) => {
    console.error("[realai-registry] Fatal error:", err);
    process.exit(1);
  });
}

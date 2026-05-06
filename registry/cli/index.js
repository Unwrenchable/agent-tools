#!/usr/bin/env node
// ─── realai-registry CLI ──────────────────────────────────────────────────────
//
// Usage:
//   REGISTRY_URL=http://localhost:4000 node cli/index.js list
//   REGISTRY_URL=http://localhost:4000 node cli/index.js search <query>
//   REGISTRY_URL=http://localhost:4000 node cli/index.js show <id>

import fetch from "node-fetch";
import fuzzy from "fuzzy";

const REGISTRY_URL = process.env["REGISTRY_URL"];

if (!REGISTRY_URL) {
  console.error(
    "Error: REGISTRY_URL environment variable is not set.\n" +
      "Example: export REGISTRY_URL=http://localhost:4000",
  );
  process.exit(1);
}

async function getAgents() {
  const res = await fetch(`${REGISTRY_URL}/v1/agents`);
  if (!res.ok) {
    throw new Error(`Registry returned HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

async function list() {
  const agents = await getAgents();
  if (!Array.isArray(agents) || agents.length === 0) {
    console.log("No agents found.");
    return;
  }
  for (const a of agents) {
    console.log(
      [a.id, a.name, a.repo, a.type]
        .map((v) => String(v ?? "").padEnd(30))
        .join(" | "),
    );
  }
}

async function search(query) {
  if (!query) {
    console.error("Usage: search <query>");
    process.exit(1);
  }
  const agents = await getAgents();
  const results = fuzzy.filter(
    query,
    Array.isArray(agents) ? agents : [],
    { extract: (a) => `${a.name ?? ""} ${a.description ?? ""} ${a.repo ?? ""}` },
  );
  if (results.length === 0) {
    console.log("No matches.");
    return;
  }
  for (const r of results) {
    console.log(`${r.original.id}  |  ${r.original.name}  |  ${r.original.repo}`);
  }
}

async function show(id) {
  if (!id) {
    console.error("Usage: show <id>");
    process.exit(1);
  }
  const res = await fetch(`${REGISTRY_URL}/v1/agents/${encodeURIComponent(id)}`);
  if (res.status === 404) {
    console.error(`Agent "${id}" not found.`);
    process.exit(1);
  }
  if (!res.ok) {
    throw new Error(`Registry returned HTTP ${res.status}`);
  }
  const agent = await res.json();
  console.log(JSON.stringify(agent, null, 2));
}

const [cmd, arg] = process.argv.slice(2);

switch (cmd) {
  case "list":
    await list();
    break;
  case "search":
    await search(arg);
    break;
  case "show":
    await show(arg);
    break;
  default:
    console.log("Commands:\n  list            — list all registered agents\n  search <query>  — fuzzy-search by name / description / repo\n  show <id>       — print full agent record as JSON");
    break;
}

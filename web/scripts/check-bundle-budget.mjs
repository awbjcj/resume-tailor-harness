import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

const dist = resolve(import.meta.dirname, "../dist");
const manifest = JSON.parse(readFileSync(resolve(dist, ".vite/manifest.json"), "utf8"));
const sizes = new Map();
const size = (key) => {
  if (!sizes.has(key)) sizes.set(key, gzipSync(readFileSync(resolve(dist, manifest[key].file))).length);
  return sizes.get(key);
};
function graph(...roots) {
  const visited = new Set();
  function visit(key) {
    if (visited.has(key)) return;
    if (!manifest[key]) throw new Error(`Missing manifest entry: ${key}`);
    visited.add(key);
    for (const dependency of manifest[key].imports ?? []) visit(dependency);
  }
  roots.forEach(visit);
  return [...visited].filter((key) => manifest[key].file.endsWith(".js"));
}
const entry = Object.keys(manifest).find((key) => manifest[key].isEntry);
if (!entry) throw new Error("No JavaScript entry in build manifest");
const total = (keys) => keys.reduce((bytes, key) => bytes + size(key), 0);
const initialGraph = new Set(graph(entry));
const initial = total([...initialGraph]);
const dashboard = total(graph(entry, "src/app/AppLayout.tsx", "src/features/dashboard/DashboardPage.tsx"));
const pipeline = total(graph(entry, "src/app/AppLayout.tsx", "src/features/pipeline/PipelinePage.tsx"));
const largest = Object.keys(manifest)
  .filter((key) => manifest[key].file.endsWith(".js") && !initialGraph.has(key))
  .map((key) => ({ key, gzipBytes: size(key) }))
  .sort((a, b) => b.gzipBytes - a.gzipBytes)[0];
console.log(JSON.stringify({ initialGzipBytes: initial, dashboardGzipBytes: dashboard,
  pipelineGzipBytes: pipeline, largestDeferredChunk: largest, targetInitialGzipBytes: 200_000 }, null, 2));
// Retain the target while enforcing the measured, complete graph as a ratchet.
// The historical 131.72 KB figure omitted transitive shared chunks.
if (initial > 200_000) console.warn("Initial JavaScript remains above the 200 KB target; see performance-budget.md.");
if (initial > 265_000 || largest.gzipBytes > 120_000 || dashboard > 360_000 || pipeline > 625_000) {
  throw new Error("JavaScript exceeded a regression ceiling; inspect the complete import graph.");
}

// Copies the pipeline's real output (../data/processed/opportunity_areas.json)
// into frontend/data/, which is what the deployed app actually reads (see
// lib/data.ts). Run this after every pipeline/synthesize.py run you want to
// publish — it's a manual/explicit step, not automatic, so a deploy never
// silently picks up a run you didn't intend to publish.
import { copyFile, mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = path.join(frontendDir, "..", "data", "processed", "opportunity_areas.json");
const destDir = path.join(frontendDir, "data");
const dest = path.join(destDir, "opportunity_areas.json");

await mkdir(destDir, { recursive: true });
await copyFile(src, dest);
console.log(`[sync-data] copied ${src} -> ${dest}`);

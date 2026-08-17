import { readFile } from "fs/promises";
import path from "path";
import type { OpportunityAreasFile } from "./types";

// Read-only over precomputed data (architecture.md §7) — no live Groq calls,
// just a filesystem read of the pipeline's output. `sample_quotes` embedded
// in each opportunity area already carries everything the evidence
// drill-down view needs, so extracted.jsonl (mentioned as an option in
// implementation-plan.md's Phase 5 intro) isn't separately loaded here —
// one data contract, and it keeps this off the edge-case 10.5 "large file
// shipped to the client" path entirely.
//
// Lives inside frontend/data/ (not ../data/processed/) so the frontend is a
// self-contained deployable unit — a platform that builds only this
// directory (Railway/Vercel with root directory = frontend, a Docker build
// context scoped to frontend, etc.) has no access to sibling directories in
// the repo. Re-sync this file from the pipeline's real output with
// `npm run sync-data` (see package.json) whenever you want to publish a new
// run's results.
const DATA_PATH = path.join(process.cwd(), "data", "opportunity_areas.json");

export async function loadOpportunityAreas(): Promise<OpportunityAreasFile | null> {
  let raw: string;
  try {
    raw = await readFile(DATA_PATH, "utf-8");
  } catch {
    // Not run yet, or gitignored/missing in this environment — a valid
    // state (edge-case 10.1), not an error to crash the page over.
    return null;
  }

  try {
    return JSON.parse(raw) as OpportunityAreasFile;
  } catch {
    console.error(`[data] ${DATA_PATH} exists but is not valid JSON`);
    return null;
  }
}

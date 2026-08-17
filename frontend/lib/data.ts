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
const DATA_PATH = path.join(process.cwd(), "..", "data", "processed", "opportunity_areas.json");

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

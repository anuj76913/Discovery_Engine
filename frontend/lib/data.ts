import { readFile } from "fs/promises";
import path from "path";
import type { OpportunityAreasFile } from "./types";

// Read-only over precomputed data (architecture.md §7) — no live Groq calls
// from this app either way. Two sources, in priority order:
//
// 1. If API_URL is set (the deployed backend/ FastAPI service — see
//    backend/main.py), fetch from there. This is the path for a real
//    deploy: frontend and backend are separate services, so the frontend
//    can't just read the backend's filesystem.
// 2. Otherwise, fall back to the local snapshot at frontend/data/ — this is
//    what makes `npm run dev` work standalone with no backend running.
//    Re-sync it from the pipeline's real output with `npm run sync-data`.
const API_URL = process.env.API_URL;
const LOCAL_DATA_PATH = path.join(process.cwd(), "data", "opportunity_areas.json");

export async function loadOpportunityAreas(): Promise<OpportunityAreasFile | null> {
  if (API_URL) {
    return loadFromApi(API_URL);
  }
  return loadFromLocalFile();
}

async function loadFromApi(apiUrl: string): Promise<OpportunityAreasFile | null> {
  try {
    const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/opportunity-areas`, { cache: "no-store" });
    if (!res.ok) {
      // 404 means the backend is up but hasn't had data published yet
      // (edge-case 10.1) — not an error to crash the page over.
      if (res.status !== 404) {
        console.error(`[data] ${apiUrl} responded ${res.status}`);
      }
      return null;
    }
    return (await res.json()) as OpportunityAreasFile;
  } catch (err) {
    console.error(`[data] failed to reach ${apiUrl}:`, err);
    return null;
  }
}

async function loadFromLocalFile(): Promise<OpportunityAreasFile | null> {
  let raw: string;
  try {
    raw = await readFile(LOCAL_DATA_PATH, "utf-8");
  } catch {
    // Not run yet, or gitignored/missing in this environment — a valid
    // state (edge-case 10.1), not an error to crash the page over.
    return null;
  }

  try {
    return JSON.parse(raw) as OpportunityAreasFile;
  } catch {
    console.error(`[data] ${LOCAL_DATA_PATH} exists but is not valid JSON`);
    return null;
  }
}

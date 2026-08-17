"""Minimal API — serves the Discovery Engine pipeline's precomputed output
over HTTP. This does not run the pipeline and makes no LLM calls; it only
ever reads data/opportunity_areas.json and returns it, matching
architecture.md's "read-only over precomputed data" design.

To publish a new pipeline run: run the real pipeline locally (collectors ->
pipeline/normalize.py -> extract.py -> synthesize.py), then run
`python sync_data.py` from this directory to copy the fresh output here,
then redeploy.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATA_PATH = Path(__file__).resolve().parent / "data" / "opportunity_areas.json"

app = FastAPI(title="Myntra Discovery Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # public read-only data, no auth, no user data
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/opportunity-areas")
def get_opportunity_areas():
    if not DATA_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No pipeline output published yet — run the pipeline and `python sync_data.py`.",
        )
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))

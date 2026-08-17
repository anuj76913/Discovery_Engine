"""Copies the pipeline's real output (../data/processed/opportunity_areas.json)
into backend/data/, which is what the deployed API actually serves (see
main.py). Run this after every pipeline/synthesize.py run you want to
publish — a manual, explicit step so a deploy never silently picks up a run
you didn't intend to publish.
"""
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "processed" / "opportunity_areas.json"
DEST_DIR = Path(__file__).resolve().parent / "data"
DEST = DEST_DIR / "opportunity_areas.json"

if __name__ == "__main__":
    if not SRC.exists():
        raise SystemExit(f"[sync_data] ERROR: {SRC} not found — run the pipeline first.")
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DEST)
    print(f"[sync_data] copied {SRC} -> {DEST}")

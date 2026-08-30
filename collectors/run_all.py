"""Entrypoint that runs all collectors in sequence. A failure in one
source is isolated and logged, never aborts the others (architecture.md
§3, implementation-plan.md Phase 1).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import play_store
import app_store
import reddit
import apify_reddit
import youtube
import forums

COLLECTORS = [
    ("play_store", play_store.run),
    ("app_store", app_store.run),
    ("reddit", reddit.run),
    ("apify_reddit", apify_reddit.run),
    ("youtube", youtube.run),
    ("forums", forums.run),
]


def run_all(limit: int | None = None) -> dict[str, int]:
    config = common.load_config()
    summary: dict[str, int] = {}

    for name, run_fn in COLLECTORS:
        print(f"\n=== {name} ===")
        try:
            summary[name] = run_fn(config, limit=limit)
        except Exception as exc:  # noqa: BLE001 - one collector's crash must not kill the others
            print(f"[run_all] ERROR: {name} collector failed: {exc}")
            summary[name] = 0

    print("\n=== Summary ===")
    total = 0
    for name, count in summary.items():
        print(f"{name:12s} {count:5d} new rows")
        total += count
    print(f"{'total':12s} {total:5d} new rows")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all collectors")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override every source's configured item cap (useful for a small smoke-test run)",
    )
    args = parser.parse_args()

    run_all(limit=args.limit)

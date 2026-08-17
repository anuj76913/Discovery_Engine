"""Google Play Store review collector (architecture.md §3).

No API key needed. Idempotent: re-running skips reviewIds already on disk.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import timezone
from pathlib import Path

from google_play_scraper import Sort, reviews

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "play_store"
PAGE_SIZE = 100
PAGE_DELAY_SECONDS = 1  # avoid sustained-scraping IP throttling (edge-case 1.4)


def _sort_from_name(name: str) -> Sort:
    try:
        return Sort[name]
    except KeyError:
        raise ValueError(f"Unknown sort order {name!r} in config.yaml sources.play_store.sort_orders")


def _to_row(review: dict) -> dict:
    at = review.get("at")
    # google-play-scraper's `at` field is a naive datetime; community-documented
    # as UTC, but the library gives no timezone guarantee — best-effort, not
    # a hard fact (edge-case 6.5).
    timestamp = at.replace(tzinfo=timezone.utc).isoformat() if at else None
    return common.make_row(
        source=SOURCE,
        source_id=review["reviewId"],
        text=review.get("content") or "",
        rating=review.get("score"),
        timestamp=timestamp,
        # No per-review permalink exists on Play Store; matches
        # architecture.md §3's own play_store example ("url": null).
        url=None,
    )


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["play_store"]
    cap = limit if limit is not None else cfg["item_caps"]["play_store"]
    package_id = src_cfg["package_id"]
    country = src_cfg["country"]
    lang = src_cfg["lang"]
    sort_orders = src_cfg["sort_orders"]

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0

    for sort_name in sort_orders:
        if total_written >= cap:
            break
        sort_enum = _sort_from_name(sort_name)
        continuation_token = None
        while total_written < cap:
            try:
                batch, continuation_token = reviews(
                    package_id,
                    lang=lang,
                    country=country,
                    sort=sort_enum,
                    count=min(PAGE_SIZE, cap - total_written),
                    continuation_token=continuation_token,
                )
            except Exception as exc:  # noqa: BLE001 - one bad page shouldn't kill the run
                print(f"[play_store] WARN: page fetch failed under sort={sort_name}: {exc}")
                break

            if not batch:
                break

            rows = [_to_row(r) for r in batch]
            fresh = common.filter_new(rows, existing_ids)
            written = common.append_rows(SOURCE, fresh)
            existing_ids.update(r["source_id"] for r in fresh)
            total_written += written
            print(f"[play_store] sort={sort_name}: +{written} new (page size {len(batch)}, total {total_written}/{cap})")

            if continuation_token is None:
                break  # no more pages available (edge-case 1.1)

            time.sleep(PAGE_DELAY_SECONDS)

    print(f"[play_store] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Myntra Play Store reviews")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

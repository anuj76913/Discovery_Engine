"""Apple App Store review collector (architecture.md §3).

Calls Apple's public iTunes RSS customer-reviews feed directly instead of
the unmaintained `app-store-scraper` package (see implementation-plan.md's
"Environment notes" — that package hard-pins requests==2.23.0 and conflicts
with every other dependency; this is functionally identical since that's
what the package wraps internally).

No API key needed. Idempotent: re-running skips review ids already on disk.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "app_store"
FEED_URL = "https://itunes.apple.com/{storefront}/rss/customerreviews/id={track_id}/sortBy={sort}/page={page}/json"
PAGE_DELAY_SECONDS = 1


def _to_row(entry: dict) -> dict | None:
    # The feed's first entry on page 1 is sometimes the app metadata record,
    # not a review — it lacks im:rating/content (edge-case 2.3).
    if "im:rating" not in entry or "content" not in entry:
        return None
    rating_label = entry.get("im:rating", {}).get("label")
    return common.make_row(
        source=SOURCE,
        source_id=entry["id"]["label"],
        text=entry["content"]["label"],
        rating=int(rating_label) if rating_label and rating_label.isdigit() else None,
        timestamp=entry.get("updated", {}).get("label"),
        # No per-review permalink in this feed; matches architecture.md's
        # app_store example ("url": null).
        url=None,
    )


def _fetch_page(storefront: str, track_id: int, sort: str, page: int) -> list[dict] | None:
    url = FEED_URL.format(storefront=storefront, track_id=track_id, sort=sort, page=page)
    resp = requests.get(url, headers={"User-Agent": common.DEFAULT_USER_AGENT}, timeout=15)
    if resp.status_code != 200:
        print(f"[app_store] WARN: page {page} ({storefront}/{sort}) returned HTTP {resp.status_code}")
        return None
    try:
        data = resp.json()
    except ValueError:
        print(f"[app_store] WARN: page {page} ({storefront}) returned non-JSON body")
        return None
    entries = data.get("feed", {}).get("entry")
    if not entries:
        return None
    # Single-review feeds return a dict, not a list, for `entry`.
    return entries if isinstance(entries, list) else [entries]


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["app_store"]
    cap = limit if limit is not None else cfg["item_caps"]["app_store"]
    track_id = src_cfg["track_id"]
    max_pages = src_cfg.get("max_pages", 10)
    sort_orders = src_cfg.get("sort_orders", ["mostRecent"])

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0

    for storefront in src_cfg["storefronts"]:
        if total_written >= cap:
            break
        for sort in sort_orders:
            if total_written >= cap:
                break
            for page in range(1, max_pages + 1):
                if total_written >= cap:
                    break
                entries = _fetch_page(storefront, track_id, sort, page)
                if entries is None:
                    break  # end of available pages (edge-case 2.1) or a fetch failure

                rows = [r for r in (_to_row(e) for e in entries) if r is not None]
                fresh = common.filter_new(rows, existing_ids)
                written = common.append_rows(SOURCE, fresh)
                existing_ids.update(r["source_id"] for r in fresh)
                total_written += written
                print(f"[app_store] {storefront}/{sort} page {page}: +{written} new (total {total_written}/{cap})")

                time.sleep(PAGE_DELAY_SECONDS)

    print(f"[app_store] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Myntra App Store reviews")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

"""YouTube comment collector (architecture.md §3), via
`youtube-comment-downloader`. No API key needed.

Runs against a curated seed list of video URLs in config.yaml
(sources.youtube.seed_video_urls) rather than scraping YouTube search
results — search-result scraping is the fragile part and is deliberately
out of scope for this pass (see implementation-plan.md Phase 1).
"""
from __future__ import annotations

import argparse
import sys
from datetime import timezone, datetime
from pathlib import Path

from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "youtube"


def _to_row(comment: dict, video_url: str) -> dict:
    # `time_parsed` is the library's best-effort resolution of a relative
    # string like "2 years ago" to a unix timestamp — approximate, not
    # exact, but still meaningfully more useful than the raw relative string.
    time_parsed = comment.get("time_parsed")
    timestamp = (
        datetime.fromtimestamp(time_parsed, tz=timezone.utc).isoformat() if time_parsed else None
    )
    cid = comment["cid"]
    return common.make_row(
        source=SOURCE,
        source_id=cid,
        text=comment.get("text") or "",
        rating=None,  # YouTube comments have no 1-5 rating concept
        timestamp=timestamp,
        url=f"{video_url}&lc={cid}",
    )


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["youtube"]
    cap = limit if limit is not None else cfg["item_caps"]["youtube"]
    seed_urls = src_cfg.get("seed_video_urls") or []

    if not seed_urls:
        print("[youtube] no seed_video_urls configured in config.yaml — nothing to collect")
        return 0

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0
    downloader = YoutubeCommentDownloader()

    for video_url in seed_urls:
        if total_written >= cap:
            break
        try:
            comment_iter = downloader.get_comments_from_url(video_url, sort_by=SORT_BY_POPULAR)
            batch = []
            for comment in comment_iter:
                batch.append(_to_row(comment, video_url))
                if len(batch) >= cap - total_written:
                    break
        except Exception as exc:  # noqa: BLE001 - deleted/private/region-locked video (edge-case 4.1)
            print(f"[youtube] WARN: failed to fetch comments for {video_url}: {exc}")
            continue

        fresh = common.filter_new(batch, existing_ids)
        written = common.append_rows(SOURCE, fresh)
        existing_ids.update(r["source_id"] for r in fresh)
        total_written += written
        print(f"[youtube] {video_url}: +{written} new (total {total_written}/{cap})")

    print(f"[youtube] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect comments from seeded Myntra-related YouTube videos")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

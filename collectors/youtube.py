"""YouTube comment collector (architecture.md §3), via the official
YouTube Data API v3 — a real, documented Google API, not scraping, so
there's no robots.txt question.

This replaces an earlier version built on `youtube-comment-downloader`,
which turned out to call YouTube's internal `/youtubei/v1/next` endpoint —
disallowed for all bots in YouTube's robots.txt (`Disallow: /youtubei/`),
confirmed live by tracing the library's actual HTTP requests. The official
API has no such issue and, as a bonus, also supports `search.list`, so
Myntra-relevant videos can be discovered by keyword instead of only ever
working from a hand-picked seed list (YouTube's own /results search page
is itself robots.txt-disallowed, which is why that wasn't an option before
either).

Credential-gated like the Groq/Reddit-dependent stages: needs
YOUTUBE_API_KEY in .env (free — create one at
https://console.cloud.google.com after enabling "YouTube Data API v3").
Free-tier quota is 10,000 units/day; search.list costs 100 units/call,
commentThreads.list costs 1 unit/call.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "youtube"
API_BASE = "https://www.googleapis.com/youtube/v3"


def _extract_video_id(url_or_id: str) -> str:
    if "watch?v=" in url_or_id:
        return url_or_id.split("watch?v=")[1].split("&")[0]
    if "youtu.be/" in url_or_id:
        return url_or_id.split("youtu.be/")[1].split("?")[0]
    return url_or_id  # already a bare video id


def _search_video_ids(api_key: str, query: str, max_results: int) -> list[str]:
    resp = requests.get(
        f"{API_BASE}/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "key": api_key,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[youtube] WARN: search {query!r} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return []
    return [item["id"]["videoId"] for item in resp.json().get("items", [])]


def _fetch_comments(api_key: str, video_id: str, cap_remaining: int) -> list[dict]:
    rows: list[dict] = []
    page_token = None
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    while len(rows) < cap_remaining:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "order": "relevance",
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(f"{API_BASE}/commentThreads", params=params, timeout=15)
        if resp.status_code != 200:
            # Comments disabled, video not found/private, or quota exceeded
            # (edge-case 4.1) — log and move on rather than kill the run.
            print(f"[youtube] WARN: comments for {video_id} failed: HTTP {resp.status_code} {resp.text[:200]}")
            break
        data = resp.json()
        for item in data.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            cid = item["snippet"]["topLevelComment"]["id"]
            rows.append(
                common.make_row(
                    source=SOURCE,
                    source_id=cid,
                    text=top.get("textOriginal") or "",
                    rating=None,  # YouTube comments have no 1-5 rating concept
                    timestamp=top.get("publishedAt"),
                    url=f"{video_url}&lc={cid}",
                )
            )
            if len(rows) >= cap_remaining:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return rows


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["youtube"]
    cap = limit if limit is not None else cfg["item_caps"]["youtube"]

    load_dotenv(common.REPO_ROOT / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print(
            "[youtube] YOUTUBE_API_KEY not set in .env — collecting 0 rows rather than "
            "failing the run (edge-case 8.3). Get a free key at "
            "https://console.cloud.google.com (enable 'YouTube Data API v3')."
        )
        return 0

    video_ids: list[str] = []
    seen_ids: set[str] = set()

    for url in src_cfg.get("seed_video_urls") or []:
        vid = _extract_video_id(url)
        if vid not in seen_ids:
            video_ids.append(vid)
            seen_ids.add(vid)

    for query in src_cfg.get("search_queries") or []:
        found = _search_video_ids(api_key, query, src_cfg.get("max_videos_per_query", 25))
        new = [v for v in found if v not in seen_ids]
        print(f"[youtube] search {query!r}: {len(found)} results, {len(new)} new videos")
        video_ids.extend(new)
        seen_ids.update(new)

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0

    for vid in video_ids:
        if total_written >= cap:
            break
        rows = _fetch_comments(api_key, vid, cap - total_written)
        fresh = common.filter_new(rows, existing_ids)
        written = common.append_rows(SOURCE, fresh)
        existing_ids.update(r["source_id"] for r in fresh)
        total_written += written
        print(f"[youtube] video {vid}: +{written} new (total {total_written}/{cap})")

    print(f"[youtube] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect comments from Myntra-related YouTube videos via the official API")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

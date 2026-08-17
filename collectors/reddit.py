"""Reddit collector (architecture.md §3), via PRAW's read-only app-only
mode.

Discovered live during Phase 1 build: Reddit's anonymous JSON endpoints
(both old.reddit.com/*.json and www.reddit.com/*.json) now require login —
old.reddit.com redirects to a login wall, www.reddit.com returns 403.
architecture.md §3 already names the fallback for this case: "PRAW with a
free read-only app-only token." That's what this collector uses.

Credential-gated like the Groq-dependent stages: needs REDDIT_CLIENT_ID
and REDDIT_CLIENT_SECRET in .env (free — register a "script" app at
https://www.reddit.com/prefs/apps). No Reddit account password is used;
PRAW's client-credentials flow only needs the app's id/secret for
read-only access. If the credentials are missing, this collector logs a
clear message and returns 0 rather than crashing (same pattern as
youtube.py/forums.py with empty seed lists).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timezone, datetime
from pathlib import Path

import praw
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "reddit"
DEAD_TEXT = {"[deleted]", "[removed]", ""}


def _to_row(submission) -> dict | None:
    title = (submission.title or "").strip()
    selftext = (submission.selftext or "").strip()

    # Zero-signal rows before they ever hit disk (edge-case 3.3).
    if title in DEAD_TEXT and selftext in DEAD_TEXT:
        return None

    text = f"{title}\n\n{selftext}".strip() if selftext and selftext not in DEAD_TEXT else title

    return common.make_row(
        source=SOURCE,
        source_id=submission.id,
        text=text,
        rating=None,  # Reddit has no 1-5 rating concept
        timestamp=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
        url=f"https://www.reddit.com{submission.permalink}",
    )


def _get_reddit_client(src_cfg: dict) -> praw.Reddit | None:
    load_dotenv(common.REPO_ROOT / ".env")
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "[reddit] REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set in .env — "
            "skipping Reddit collection. Register a free 'script' app at "
            "https://www.reddit.com/prefs/apps to enable this source."
        )
        return None
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=src_cfg["user_agent"],
    )


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["reddit"]
    cap = limit if limit is not None else cfg["item_caps"]["reddit"]

    reddit = _get_reddit_client(src_cfg)
    if reddit is None:
        return 0

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0

    for subreddit_name in src_cfg["subreddits"]:
        if total_written >= cap:
            break
        try:
            subreddit = reddit.subreddit(subreddit_name)
        except Exception as exc:  # noqa: BLE001 - private/banned/nonexistent subreddit (edge-case 3.4)
            print(f"[reddit] WARN: r/{subreddit_name} unavailable: {exc}")
            continue

        for term in src_cfg["search_terms"]:
            if total_written >= cap:
                break
            try:
                results = list(
                    subreddit.search(term, sort="new", limit=min(100, cap - total_written))
                )
            except Exception as exc:  # noqa: BLE001 - per-subreddit/term skip, not a full-run abort
                print(f"[reddit] WARN: r/{subreddit_name} q={term!r} failed: {exc}")
                continue

            rows = [r for r in (_to_row(s) for s in results) if r is not None]
            fresh = common.filter_new(rows, existing_ids)
            written = common.append_rows(SOURCE, fresh)
            existing_ids.update(r["source_id"] for r in fresh)
            total_written += written
            print(f"[reddit] r/{subreddit_name} q={term!r}: +{written} new (total {total_written}/{cap})")

    print(f"[reddit] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Myntra-related Reddit posts")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

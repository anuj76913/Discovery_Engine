"""Apify-based Reddit collector — supplements collectors/reddit.py.

reddit.py's PRAW-based collector is restricted to a fixed subreddit
whitelist and PRAW's subreddit.search() caps at 100 results/call. This
collector instead runs an Apify actor to search the configured wishlist
terms across ALL of Reddit, and (depending on the actor's `type` setting)
can also return matching comments — which reddit.py's submission-only
collector never captures, even though wishlist complaints often show up
buried in a comment on an unrelated post rather than in a post's own
title/selftext.

Writes to the same data/raw/reddit.jsonl file as reddit.py (SOURCE stays
"reddit" — see common.VALID_SOURCES), so rows are naturally deduped
against the PRAW run by Reddit's own post/comment id via
common.load_existing_ids().

Credential-gated like the other optional collectors: needs APIFY_TOKEN in
.env (free tier available — https://console.apify.com/settings/integrations).
If missing, this collector logs a message and returns 0 rather than
crashing (same pattern as reddit.py/youtube.py/forums.py).

Field-name caveat: Apify actor input/output schemas vary by actor and can
change between versions. `_to_row()` below tries several common key names
per field rather than assuming one exact schema, but this has NOT been
verified against a live run of the configured actor_id — run with
--dry-run first to inspect the resolved request, and check one real run's
dataset in the Apify Console to confirm _to_row()'s field guesses actually
match before trusting this collector's output.

Confirmed live 2026-08-30 against trudax/reddit-scraper-lite: when a
`searches` query has zero real matches on Reddit's own search (true for
every multi-word wishlist phrasing tried except "myntra wishlist" itself
— e.g. "myntra save for later" had zero real posts), the actor does NOT
just return zero results — it falls back to crawling unrelated
subreddits pulled from some other queue/discovery source, observed
including NSFW ones, and keeps billing for every page it visits (one
6-term batch racked up $0.77 before being aborted, almost entirely spent
on this fallback). Searching multiple narrow phrases is therefore a
losing trade: real wishlist vocabulary on Reddit is too sparse for
Reddit's own search to treat those phrases as real queries.
`search_terms` is deliberately just `["myntra"]` — a single broad term
with abundant real matches, so the fallback never triggers — and wishlist
*scope* is enforced locally afterward in `run()` by requiring one of
`keyword_prefilter` (config.yaml's already-established wishlist/
save-for-later vocabulary, shared with extract.py's Stage 2 filter) in
the row text. `_to_row()`'s separate `"myntra" not in text.lower()` guard
stays as a backstop against the same actor drifting off-topic even on a
term with real matches.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "reddit"
DEAD_TEXT = {"[deleted]", "[removed]", ""}


def _first(item: dict, *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_timestamp(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # Different actor versions have returned both seconds and
        # millisecond epoch timestamps — treat anything too large to be a
        # plausible seconds value as milliseconds.
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return raw  # store as-is rather than silently dropping a real timestamp
    return None


def _to_row(item: dict) -> Optional[dict]:
    title = (_first(item, "title") or "").strip()
    body = (_first(item, "body", "selftext", "text", "communityText") or "").strip()

    if title in DEAD_TEXT and body in DEAD_TEXT:
        return None

    text = f"{title}\n\n{body}".strip() if title and body else (title or body)
    if not text or text in DEAD_TEXT:
        return None

    # Local relevance guard (edge-case found live 2026-08-30): this actor's
    # multi-word `searches` queries were unreliable beyond the first term —
    # some queries matched on subreddit *names* containing the query words
    # (e.g. r/LuigiWishList) rather than post content, and others appeared
    # to fall back to crawling unrelated r/all-style content entirely
    # (likely after Reddit itself started 429/403-blocking the actor's
    # requests mid-run). Requiring "myntra" in the row text is a cheap,
    # actor-agnostic backstop against writing that noise to disk regardless
    # of what upstream search/crawl behavior produced it.
    if "myntra" not in text.lower():
        return None

    # Found live 2026-08-30: broad "myntra" search surfaces market-research
    # survey solicitations (e.g. r/SurveyExchange, r/SurveyZone posts
    # literally titled "Myntra Shopping & Wishlist Habits — Quick Survey
    # form", linking a Google/Typeform survey) — these pass the wishlist
    # keyword check ("wishlist" is right there in the title) but are not
    # organic user behavior data, just researchers soliciting responses.
    # Excluded by survey-platform link/phrase rather than by "survey" alone
    # (a genuine complaint could mention "customer survey").
    lowered_for_survey_check = text.lower()
    survey_markers = ("docs.google.com/forms", "forms.gle", "typeform.com", "surveymonkey.com", "qualtrics.com")
    if "quick survey" in lowered_for_survey_check or any(m in lowered_for_survey_check for m in survey_markers):
        return None

    source_id = _first(item, "id", "postId", "commentId")
    if not source_id:
        # No stable id to dedupe on — skip rather than risk duplicate rows
        # on a re-run.
        return None

    url = _first(item, "url", "permalink")
    if url and url.startswith("/"):
        url = f"https://www.reddit.com{url}"

    return common.make_row(
        source=SOURCE,
        source_id=source_id,
        text=text,
        rating=None,  # Reddit has no 1-5 rating concept
        timestamp=_normalize_timestamp(_first(item, "createdAt", "created_utc", "date")),
        url=url,
    )


def _is_wishlist_relevant(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def _build_run_input(src_cfg: dict, terms: list[str], max_items: int) -> dict:
    return {
        "searches": terms,
        "type": src_cfg.get("type", "posts"),
        "sort": src_cfg.get("sort", "new"),
        "maxItems": max_items,
        # Requested live 2026-08-30: consecutive default-proxy runs started
        # getting 429/403-blocked by Reddit itself partway through a batch
        # (see run fzRBtJaO4TQKy4xN6's logs), which correlated with the
        # crawler drifting into unrelated content. Apify's residential
        # proxy group is the standard mitigation for this across
        # Puppeteer-based actors.
        "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }


def run(cfg: dict, limit: int | None = None, dry_run: bool = False) -> int:
    src_cfg = cfg["sources"]["apify_reddit"]
    cap = limit if limit is not None else cfg["item_caps"]["apify_reddit"]

    if dry_run:
        run_input = _build_run_input(src_cfg, src_cfg["search_terms"], max_items=cap)
        print(f"[apify_reddit] DRY RUN — would call actor {src_cfg['actor_id']!r} with:")
        print(json.dumps(run_input, indent=2))
        print(
            "[apify_reddit] No Apify call made. Inspect one real run's dataset in the "
            "Apify Console to confirm _to_row()'s field-name guesses match this actor "
            "before relying on this collector."
        )
        return 0

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("[apify_reddit] apify-client not installed — run `pip install apify-client` to enable this source.")
        return 0

    load_dotenv(common.REPO_ROOT / ".env")
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print(
            "[apify_reddit] APIFY_TOKEN not set in .env — skipping. Get a free-tier "
            "token at https://console.apify.com/settings/integrations to enable this source."
        )
        return 0

    client = ApifyClient(token)
    existing_ids = common.load_existing_ids(SOURCE)

    run_input = _build_run_input(src_cfg, src_cfg["search_terms"], max_items=cap)
    try:
        actor_run = client.actor(src_cfg["actor_id"]).call(run_input=run_input)
    except Exception as exc:  # noqa: BLE001 - report and return 0 rather than crash the caller
        print(f"[apify_reddit] WARN: actor run failed: {exc}")
        return 0

    try:
        items = list(client.dataset(actor_run.default_dataset_id).iterate_items())
    except Exception as exc:  # noqa: BLE001 - report and return 0 rather than crash the caller
        print(f"[apify_reddit] WARN: reading dataset failed: {exc}")
        return 0

    myntra_rows = [r for r in (_to_row(item) for item in items) if r is not None]
    keywords = [kw.lower() for kw in cfg["keyword_prefilter"]]
    rows = [r for r in myntra_rows if _is_wishlist_relevant(r["text"], keywords)]
    fresh = common.filter_new(rows, existing_ids)
    total_written = common.append_rows(SOURCE, fresh)
    print(
        f"[apify_reddit] {len(items)} items fetched, {len(myntra_rows)} myntra-relevant, "
        f"{len(rows)} wishlist-relevant, {total_written} new rows written"
    )
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Myntra wishlist-related Reddit posts/comments site-wide via Apify")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved actor input for the first search term without calling Apify",
    )
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit, dry_run=args.dry_run)

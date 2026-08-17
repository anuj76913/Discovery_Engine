"""Forum/community collector (architecture.md §3) — best-effort, lowest
priority, manual seed list. Acceptable to yield near-zero rows.

Each seeded page is treated as one item: source_id is the URL itself, so a
page already on disk is skipped without even making a network request.
Checks robots.txt before fetching (edge-case 5.2).
"""
from __future__ import annotations

import argparse
import sys
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SOURCE = "forum"


def _robots_allow(url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        # RobotFileParser.read() fetches with urllib's own bare
        # "Python-urllib/x.y" User-Agent, which some sites block outright
        # (403) independent of what their robots.txt actually says — that
        # blocked fetch then makes can_fetch() report "disallow everything"
        # as a false negative. Fetch with our real UA instead and hand the
        # parser the text directly.
        resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=10)
        if resp.status_code == 404:
            return True  # no robots.txt at all — nothing restricts us
        resp.raise_for_status()
        rp.parse(resp.text.splitlines())
    except Exception:
        # robots.txt unreachable for a reason other than a clean 404 —
        # default to allow rather than blocking a best-effort, low-volume
        # source over a fetch failure.
        return True
    return rp.can_fetch(user_agent, url)


def _to_row(url: str, soup: BeautifulSoup) -> dict | None:
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if p)
    if not text:
        return None
    return common.make_row(
        source=SOURCE,
        source_id=url,
        text=text,
        rating=None,
        # Publish date isn't reliably extractable from arbitrary forum
        # markup without per-site tuning — honest None over a guess.
        timestamp=None,
        url=url,
    )


def run(cfg: dict, limit: int | None = None) -> int:
    src_cfg = cfg["sources"]["forums"]
    cap = limit if limit is not None else cfg["item_caps"]["forums"]
    seed_urls = src_cfg.get("seed_urls") or []

    if not seed_urls:
        print("[forums] no seed_urls configured in config.yaml — nothing to collect")
        return 0

    existing_ids = common.load_existing_ids(SOURCE)
    total_written = 0

    for url in seed_urls:
        if total_written >= cap:
            break
        if url in existing_ids:
            continue  # already collected; skip the network call entirely

        if not _robots_allow(url, common.DEFAULT_USER_AGENT):
            print(f"[forums] SKIP: robots.txt disallows {url} (edge-case 5.2)")
            continue

        try:
            resp = requests.get(url, headers={"User-Agent": common.DEFAULT_USER_AGENT}, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[forums] WARN: failed to fetch {url}: {exc}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        row = _to_row(url, soup)
        if row is None:
            print(f"[forums] WARN: no extractable text at {url} (edge-case 5.1)")
            continue

        written = common.append_rows(SOURCE, [row])
        existing_ids.add(url)
        total_written += written
        print(f"[forums] {url}: +{written} new (total {total_written}/{cap})")

    print(f"[forums] done: {total_written} new rows written")
    return total_written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect seeded forum/community pages")
    parser.add_argument("--limit", type=int, default=None, help="Override the configured item cap")
    args = parser.parse_args()

    config = common.load_config()
    run(config, limit=args.limit)

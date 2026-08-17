"""Shared helpers for all collectors: config loading, the landing-row
schema (architecture.md §3), and idempotent append-only JSONL writes.

PII policy: `author_meta` is always None. None of the free/public sources
this project scrapes expose a genuinely non-PII aggregate signal (e.g. a
real "account age bucket"), so fabricating one would be worse than
omitting it — see architecture.md §3's "no PII stored" guardrail.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
CONFIG_PATH = REPO_ROOT / "config.yaml"

VALID_SOURCES = {"play_store", "app_store", "reddit", "youtube", "forum"}

DEFAULT_USER_AGENT = "discovery-engine/0.1 (Myntra wishlist-conversion research; contact via repo owner)"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def raw_path(source: str) -> Path:
    if source not in VALID_SOURCES:
        raise ValueError(f"Unknown source {source!r}; expected one of {sorted(VALID_SOURCES)}")
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_RAW_DIR / f"{source}.jsonl"


def load_existing_ids(source: str) -> set[str]:
    """(source, source_id) idempotency key set already on disk.

    Keyed per-source-file rather than globally, which already namespaces
    the id by source (edge-case 6.1) since each source writes to its own
    file.
    """
    path = raw_path(source)
    ids: set[str] = set()
    if not path.exists():
        return ids
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"[common] WARN: skipping malformed line {line_num} in {path.name} (edge-case 6.2)")
                continue
            sid = row.get("source_id")
            if sid is not None:
                ids.add(str(sid))
    return ids


def make_row(
    *,
    source: str,
    source_id: str,
    text: str,
    rating: Optional[int] = None,
    timestamp: Optional[str] = None,
    url: Optional[str] = None,
) -> dict:
    if source not in VALID_SOURCES:
        raise ValueError(f"Unknown source {source!r}")
    return {
        "source": source,
        "source_id": str(source_id),
        "text": text,
        "author_meta": None,
        "rating": rating,
        "timestamp": timestamp,
        "url": url,
        "collected_at": now_iso(),
    }


def filter_new(rows: Iterable[dict], existing_ids: set[str]) -> list[dict]:
    """Drop rows whose source_id is already on disk or already seen this run
    (pagination overlap), per the idempotency contract in architecture.md §3."""
    fresh: list[dict] = []
    seen_this_run: set[str] = set()
    for row in rows:
        sid = row["source_id"]
        if sid in existing_ids or sid in seen_this_run:
            continue
        seen_this_run.add(sid)
        fresh.append(row)
    return fresh


def append_rows(source: str, rows: Iterable[dict]) -> int:
    """Append one JSON object per line (LF only, per edge-case 11.5) to
    data/raw/<source>.jsonl. Caller is responsible for having already
    de-duplicated via filter_new."""
    path = raw_path(source)
    written = 0
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
            written += 1
    return written

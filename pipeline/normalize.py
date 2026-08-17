"""Stage 2 — Normalization (architecture.md §4).

Load all data/raw/*.jsonl -> keyword pre-filter -> exact + near-dup dedup
-> language filter (flag, don't drop) -> chunk long text -> stable item_id
-> write data/processed/normalized.parquet.

Edge cases this deliberately handles (see docs/edge-case.md §7):
- 7.1/7.2: keyword filter is a broad cost-control net, not a precision
  tool — Stage 3's LLM `is_relevant` is the real gate. Drop-rate is logged.
- 7.3: near-dup hashing only applies above a word-count floor, so two
  independent users writing "Great app!" aren't merged into one signal.
- 7.4: langdetect is unstable under ~20 chars — short text is flagged, not
  hard-dropped, and detection failures never drop a row either.
- 7.5: chunking only touches items over the size threshold, and only
  splits on paragraph/sentence boundaries, never mid-sentence.
- 7.6: an all-filtered-out run still writes a valid (empty) parquet file
  instead of crashing.
- 7.7: raw rows are schema-validated on load; unexpected shape is
  skipped-and-logged, not silently absorbed.
- 7.8: item_id is derived deterministically from (source, source_id), never
  from row position, so it's stable across re-runs.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

EXPECTED_RAW_KEYS = {
    "source", "source_id", "text", "author_meta", "rating", "timestamp", "url", "collected_at",
}

NEAR_DUP_MIN_WORDS = 8  # edge-case 7.3: fuzzy dedup only above this floor
SHINGLE_SIZE = 3
NUM_MINHASHES = 8

SHORT_TEXT_CHAR_THRESHOLD = 20  # edge-case 7.4: langdetect is unstable below this
CHUNK_CHAR_THRESHOLD = 2000  # ~500 tokens, comfortably under a batched-call budget

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

DetectorFactory.seed = 0  # deterministic langdetect output across runs


# --- loading -----------------------------------------------------------

def _load_raw_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(common.DATA_RAW_DIR.glob("*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[normalize] WARN: skipping malformed line {line_num} in {path.name} (edge-case 6.2)")
                    continue
                if set(row.keys()) != EXPECTED_RAW_KEYS:
                    print(
                        f"[normalize] WARN: skipping row with unexpected schema at "
                        f"{path.name}:{line_num}: keys={sorted(row.keys())} (edge-case 7.7)"
                    )
                    continue
                rows.append(row)
    return rows


# --- item id -------------------------------------------------------------

def _base_item_id(source: str, source_id: str) -> str:
    return hashlib.sha1(f"{source}:{source_id}".encode("utf-8")).hexdigest()[:16]


# --- keyword pre-filter --------------------------------------------------

def _passes_keyword_filter(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


# --- dedup -----------------------------------------------------------------

def _normalize_for_hash(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _shingles(normalized_text: str, k: int = SHINGLE_SIZE) -> set[str]:
    words = normalized_text.split()
    if len(words) < k:
        return set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _minhash_signature(shingles: set[str], num_hashes: int = NUM_MINHASHES) -> tuple[int, ...]:
    if not shingles:
        return tuple()
    return tuple(
        min(int(hashlib.md5(f"{i}:{s}".encode("utf-8")).hexdigest(), 16) for s in shingles)
        for i in range(num_hashes)
    )


def _dedup(rows: list[dict]) -> tuple[list[dict], int, int]:
    """Returns (kept_rows, exact_dup_count, near_dup_count)."""
    seen_exact: set[str] = set()
    seen_minhash: set[tuple[int, ...]] = set()
    kept: list[dict] = []
    exact_dupes = 0
    near_dupes = 0

    for row in rows:
        normalized = _normalize_for_hash(row["text"])
        exact_fp = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
        if exact_fp in seen_exact:
            exact_dupes += 1
            continue
        seen_exact.add(exact_fp)

        # edge-case 7.3: only apply fuzzy near-dup matching above a word-count
        # floor, so short independent texts ("Great app!") aren't merged.
        if len(normalized.split()) >= NEAR_DUP_MIN_WORDS:
            sig = _minhash_signature(_shingles(normalized))
            if sig:
                if sig in seen_minhash:
                    near_dupes += 1
                    continue
                seen_minhash.add(sig)

        kept.append(row)

    return kept, exact_dupes, near_dupes


# --- language filter (flag, never drop) -------------------------------------

def _detect_language(text: str) -> tuple[str | None, bool]:
    """Returns (best-guess language code or None, flagged). Never used to
    drop a row — architecture.md §4.4 keeps English + flags the rest,
    and edge-case 7.4 explicitly warns against hard-dropping on a single
    low-confidence short-text call."""
    if len(text.strip()) < SHORT_TEXT_CHAR_THRESHOLD:
        return None, True
    try:
        lang = detect(text)
    except LangDetectException:
        return None, True
    return lang, lang != "en"


# --- chunking (paragraph/sentence boundaries only) --------------------------

def _split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]


def _greedy_pack(units: list[str], limit: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        unit_len = len(unit) + 1
        if current and current_len + unit_len > limit:
            chunks.append(" ".join(current))
            current, current_len = [unit], unit_len
        else:
            current.append(unit)
            current_len += unit_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def _chunk_text(text: str, limit: int = CHUNK_CHAR_THRESHOLD) -> list[str]:
    if len(text) <= limit:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]

    units: list[str] = []
    for para in paragraphs:
        if len(para) <= limit:
            units.append(para)
            continue
        sentences = _split_sentences(para)
        if not sentences:
            # No sentence boundary in an oversized blob — last-resort hard
            # split so one pathological item can't stall the pipeline
            # (edge-case 7.5's caveat on naive chunking).
            units.extend(para[i : i + limit] for i in range(0, len(para), limit))
        else:
            units.extend(sentences)

    return _greedy_pack(units, limit)


# --- main pipeline -----------------------------------------------------------

def run() -> pd.DataFrame:
    cfg = common.load_config()
    keywords = cfg["keyword_prefilter"]

    raw_rows = _load_raw_rows()
    raw_count = len(raw_rows)
    print(f"[normalize] loaded {raw_count} raw rows")

    if raw_count == 0:
        print("[normalize] WARN: no raw rows found — writing an empty normalized.parquet (edge-case 7.6)")
        return _write_output([])

    # Attach a base item_id and sort by it now, so dedup's "first occurrence
    # wins" is deterministic across re-runs regardless of filesystem/glob
    # iteration order (edge-case 7.8).
    for row in raw_rows:
        row["_item_id"] = _base_item_id(row["source"], row["source_id"])
    raw_rows.sort(key=lambda r: r["_item_id"])

    per_source_raw: dict[str, int] = {}
    for row in raw_rows:
        per_source_raw[row["source"]] = per_source_raw.get(row["source"], 0) + 1

    kept = [r for r in raw_rows if _passes_keyword_filter(r["text"], keywords)]
    keyword_dropped = raw_count - len(kept)
    drop_rate = keyword_dropped / raw_count if raw_count else 0.0
    print(f"[normalize] keyword pre-filter: kept {len(kept)}, dropped {keyword_dropped} ({drop_rate:.1%})")

    kept, exact_dupes, near_dupes = _dedup(kept)
    print(f"[normalize] dedup: dropped {exact_dupes} exact + {near_dupes} near-duplicate rows, {len(kept)} remain")

    flagged_count = 0
    for row in kept:
        lang, flagged = _detect_language(row["text"])
        row["language"] = lang
        row["language_flagged"] = flagged
        if flagged:
            flagged_count += 1
    print(f"[normalize] language filter: {flagged_count}/{len(kept)} rows flagged non-English/uncertain (kept, not dropped)")

    final_rows: list[dict] = []
    chunked_source_count = 0
    for row in kept:
        chunks = _chunk_text(row["text"])
        if len(chunks) > 1:
            chunked_source_count += 1
        for idx, chunk_text in enumerate(chunks):
            final_rows.append(
                {
                    "item_id": row["_item_id"] if len(chunks) == 1 else f"{row['_item_id']}:{idx}",
                    "source": row["source"],
                    "source_id": row["source_id"],
                    "text": chunk_text,
                    "rating": row["rating"],
                    "timestamp": row["timestamp"],
                    "url": row["url"],
                    "collected_at": row["collected_at"],
                    "language": row["language"],
                    "language_flagged": row["language_flagged"],
                    "is_chunk": len(chunks) > 1,
                    "chunk_index": idx,
                    "chunk_count": len(chunks),
                }
            )
    print(f"[normalize] chunking: {chunked_source_count} source rows split into multiple chunks, {len(final_rows)} final rows")

    per_source_final: dict[str, int] = {}
    for row in final_rows:
        per_source_final[row["source"]] = per_source_final.get(row["source"], 0) + 1

    print("[normalize] per-source raw -> final:")
    for source in sorted(per_source_raw):
        print(f"  {source:12s} {per_source_raw[source]:6d} -> {per_source_final.get(source, 0):6d}")

    return _write_output(final_rows)


def _write_output(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "item_id", "source", "source_id", "text", "rating", "timestamp", "url",
        "collected_at", "language", "language_flagged", "is_chunk", "chunk_index", "chunk_count",
    ]
    df = pd.DataFrame(rows, columns=columns)
    common.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = common.DATA_PROCESSED_DIR / "normalized.parquet"
    df.to_parquet(out_path, engine="pyarrow", index=False)
    print(f"[normalize] wrote {len(df)} rows to {out_path}")
    return df


if __name__ == "__main__":
    run()

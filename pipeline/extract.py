"""Stage 3 — LLM Extraction via Groq (architecture.md §5).

Converts each normalized item into structured signal (reasons, blockers,
journey stage, decision factors, ...) using a forced-JSON Groq call.
Short items are batched (5-10/call); long items get their own call.

LLM-gated: requires GROQ_API_KEY in .env for a real run. `--dry-run` builds
the batches and prints the first prompt without calling the API or
requiring a key at all, so the shape can be sanity-checked for free.

Edge cases this deliberately handles (see docs/edge-case.md §8):
- 8.1/8.5: every result is schema-validated per-item; a malformed item in a
  batch is dropped and logged, it never invalidates its batch-mates.
- 8.2: `representative_quote` is verified as a real substring of the
  item's own source text before being trusted; unverifiable quotes are
  kept (still useful signal) but marked `quote_verified: false` rather
  than silently presented as guaranteed-verbatim evidence.
- 8.3: the API key is checked before any batch is built for a real run
  (not discovered mid-batch), with a clear exit message.
- 8.4: rate limits and transient errors get exponential backoff; a batch
  that exhausts retries is logged and skipped, not fatal to the run.
- 8.6: the prompt explicitly allows/expects empty arrays and low
  confidence for low-signal items instead of asking the model to fabricate.
- 8.7: already-extracted item_ids are skipped on re-run (idempotent, same
  pattern as the Stage 1 collectors), so a re-run doesn't re-spend budget.
- 8.8: representative_quote may carry PII/toxic language verbatim from the
  source text — deliberately not scrubbed here, since extracted.jsonl is a
  local intermediate artifact, not public. The scrub belongs at the point
  data is actually surfaced (Stage 5's dashboard), per edge-case 8.8/10.3.
- 8.9: `--dry-run` and `--limit` let a cost estimate happen before a full
  run; the run log records actual token usage either way.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import groq
import pandas as pd
from dotenv import load_dotenv

# Review/comment text can contain emoji and other characters outside
# Windows' default console codepage (cp1252); reconfigure stdout to UTF-8
# so printing raw source text (e.g. --dry-run's prompt preview) can't crash
# the run over a display-only issue. line_buffering=True flushes every
# print() immediately — a long run with fully-buffered stdout piped through
# a capture layer that doesn't actively drain it can fill the OS pipe
# buffer and block the whole process on write() with zero CPU usage,
# which is indistinguishable from a hang from the outside (observed during
# this project's own full-corpus run: 30+ minutes, zero bytes captured).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

EXTRACTED_PATH = common.DATA_PROCESSED_DIR / "extracted.jsonl"

SHORT_TEXT_MAX_CHARS = 500  # architecture.md §5: "5-10 short reviews per request"
# Reduced from 8: a batch of 8 items uses ~7,000+ tokens in one request,
# which by itself exceeds this Groq key's real 6,000-tokens/minute ceiling
# (confirmed via live response headers) — every such batch fails outright
# regardless of retry count, since retries happen within the same minute
# window. Observed live: a full run at BATCH_SIZE=8 succeeded on only 17/201
# items (184 failed after exhausting retries). At 3 items/batch (~1,250
# tokens/request) with 15s pacing, sustained throughput stays under ~5,000
# tokens/minute — safely under the ceiling with margin for estimation error.
BATCH_SIZE = 3
MAX_RETRIES = 5
MAX_OUTPUT_TOKENS = 4000
BATCH_PACING_SECONDS = 15
GROQ_CLIENT_MAX_RETRIES = 6

VALID_JOURNEY_STAGES = {
    "browsing", "saved_not_bought", "compared_alternatives", "bought", "returned", "abandoned",
}
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}

REQUIRED_KEYS = {
    "item_id", "is_relevant", "mentions_wishlist_or_save_for_later", "mentions_purchase_decision",
    "user_journey_stage", "reasons_for_saving", "blockers_to_purchase", "info_sought_outside_app",
    "decision_factors", "inferred_segment_signals", "sentiment", "representative_quote", "confidence",
}


# --- prompt construction ------------------------------------------------

def _build_system_prompt(decision_factor_vocab: set[str]) -> str:
    vocab_list = ", ".join(sorted(decision_factor_vocab))
    return f"""You are analyzing real user reviews and comments about Myntra (an Indian online fashion shopping app) for product research into wishlist-to-purchase conversion.

For each input item, extract structured signal — reasons, blockers, uncertainties — not just sentiment.

Rules:
- Only use information stated or clearly implied in that item's own text. Do not invent details or borrow from other items.
- `mentions_wishlist_or_save_for_later` must be true ONLY when the item is specifically about MYNTRA's own wishlist/save-for-later feature. A mention of a wishlist on a different platform (Amazon, Meesho, Flipkart, etc.), or a colloquial "wish list" of things someone wants a video creator/influencer to gift them (common in YouTube comments — not about any shopping app feature at all), must be marked false. When genuinely ambiguous which platform or sense is meant, default to false rather than guessing true.
- `representative_quote` MUST be an exact, verbatim substring copied from that item's own text — not a paraphrase, not from another item. If there's no quotable evidence, use an empty string.
- When an item has multiple sentences, `representative_quote` MUST be the single sentence that most SPECIFICALLY illustrates the reason/blocker/info-sought you extracted — never a vague summary, general consequence, or throwaway closer (e.g. "I hardly shop here anymore") when a more specific sentence describing the actual problem exists elsewhere in the same text. Prefer the sentence a reader could use as direct evidence for the specific reasons/blockers listed, not just any sentence from the item.
- `decision_factors` must only use values from this fixed list: {vocab_list}. Omit any that don't apply; never invent new ones.
- `user_journey_stage` must be exactly one of: {", ".join(sorted(VALID_JOURNEY_STAGES))}.
- `sentiment` must be exactly one of: {", ".join(sorted(VALID_SENTIMENTS))}.
- If an item has little or no real signal (e.g. a one-word review, or unrelated to wishlist/purchase behavior), set `is_relevant` to false, set list fields to an empty array (`[]` — never `false` or `null`), and use a low `confidence` — do not fabricate reasons or blockers just to fill the schema.
- Return ONLY a JSON object shaped exactly like {{"results": [...]}}, with exactly one result object per input item, each including its `item_id` copied exactly from the input.

Each result object must have exactly these fields: item_id, is_relevant, mentions_wishlist_or_save_for_later, mentions_purchase_decision, user_journey_stage, reasons_for_saving, blockers_to_purchase, info_sought_outside_app, decision_factors, inferred_segment_signals, sentiment, representative_quote, confidence (a number from 0.0 to 1.0)."""


def _build_user_prompt(batch: list[dict]) -> str:
    parts = []
    for item in batch:
        parts.append(f"item_id: {item['item_id']}\ntext: {item['text']}")
    return "\n---\n".join(parts)


# --- batching -------------------------------------------------------------

def _build_batches(items: list[dict]) -> list[list[dict]]:
    short = [it for it in items if len(it["text"]) <= SHORT_TEXT_MAX_CHARS]
    long_items = [it for it in items if len(it["text"]) > SHORT_TEXT_MAX_CHARS]
    batches = [short[i : i + BATCH_SIZE] for i in range(0, len(short), BATCH_SIZE)]
    batches.extend([[it] for it in long_items])
    return batches


# --- validation -------------------------------------------------------------

def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _verify_quote(quote: str, original_text: str) -> bool:
    if not quote:
        return False
    if quote in original_text:
        return True
    return _normalize_ws(quote) in _normalize_ws(original_text)


def _as_list(value) -> list:
    """Some models return `false`/`null` instead of `[]` for an empty list
    field despite prompt instructions — tolerate that instead of crashing
    the item (edge-case 8.1). A bare scalar is treated as a 1-item list
    rather than dropped."""
    if isinstance(value, list):
        return value
    if value in (None, False, ""):
        return []
    return [value]


def _validate_and_clean(result: dict, decision_factor_vocab: set[str], original_text: str) -> dict | None:
    if not isinstance(result, dict):
        return None
    missing = REQUIRED_KEYS - set(result.keys())
    if missing:
        print(f"[extract] WARN: item {result.get('item_id', '?')} missing keys {missing}, dropping (edge-case 8.1)")
        return None

    try:
        is_relevant = bool(result["is_relevant"])
        mentions_wishlist = bool(result["mentions_wishlist_or_save_for_later"])
        mentions_purchase = bool(result["mentions_purchase_decision"])
        stage = result["user_journey_stage"]
        stage = stage if stage in VALID_JOURNEY_STAGES else None
        reasons = [str(x) for x in _as_list(result.get("reasons_for_saving"))]
        blockers = [str(x) for x in _as_list(result.get("blockers_to_purchase"))]
        info_sought = [str(x) for x in _as_list(result.get("info_sought_outside_app"))]
        decision_factors = [x for x in _as_list(result.get("decision_factors")) if x in decision_factor_vocab]
        segment_signals = [str(x) for x in _as_list(result.get("inferred_segment_signals"))]
        sentiment = result["sentiment"]
        sentiment = sentiment if sentiment in VALID_SENTIMENTS else "neutral"
        quote = str(result.get("representative_quote") or "").strip()
        confidence = max(0.0, min(1.0, float(result["confidence"])))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[extract] WARN: item {result.get('item_id', '?')} failed type validation: {exc}, dropping (edge-case 8.1)")
        return None

    return {
        "item_id": str(result["item_id"]),
        "is_relevant": is_relevant,
        "mentions_wishlist_or_save_for_later": mentions_wishlist,
        "mentions_purchase_decision": mentions_purchase,
        "user_journey_stage": stage,
        "reasons_for_saving": reasons,
        "blockers_to_purchase": blockers,
        "info_sought_outside_app": info_sought,
        "decision_factors": decision_factors,
        "inferred_segment_signals": segment_signals,
        "sentiment": sentiment,
        "representative_quote": quote,
        "quote_verified": _verify_quote(quote, original_text) if quote else False,
        "confidence": confidence,
    }


# --- Groq call with retry ----------------------------------------------------

def _call_groq(client: "groq.Groq", model: str, system_prompt: str, batch: list[dict]):
    user_prompt = _build_user_prompt(batch)
    backoff = 2
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=MAX_OUTPUT_TOKENS,
                reasoning_effort="low",  # structured extraction, not a task needing heavy reasoning
            )
        except groq.RateLimitError:
            print(f"[extract] WARN: rate limited (attempt {attempt}/{MAX_RETRIES}), backing off {backoff}s")
        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as exc:
            print(f"[extract] WARN: transient error (attempt {attempt}/{MAX_RETRIES}): {exc}")
        time.sleep(backoff)
        backoff *= 2
    print(f"[extract] ERROR: batch failed after {MAX_RETRIES} retries, skipping {len(batch)} items this run (edge-case 8.4)")
    return None


# --- persistence -----------------------------------------------------------

def _load_existing_extracted_ids() -> set[str]:
    if not EXTRACTED_PATH.exists():
        return set()
    ids: set[str] = set()
    with open(EXTRACTED_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "item_id" in row:
                ids.add(str(row["item_id"]))
    return ids


def _append_extracted(rows: list[dict]) -> None:
    common.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXTRACTED_PATH, "a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _write_run_log(run_start: datetime, prompt_tokens: int, completion_tokens: int, written: int, failed: int, pricing: dict, model: str) -> Path:
    common.DATA_RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    input_rate = pricing.get("input_per_million", 0.0)
    output_rate = pricing.get("output_per_million", 0.0)
    estimated_cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    log = {
        "stage": "extract",
        "model": model,
        "run_started_at": run_start.isoformat(),
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "items_written": written,
        "items_failed": failed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": round(estimated_cost, 4),
        "cost_estimate_note": "Approximate only — config.yaml's pricing is not verified against Groq's live rates.",
    }
    out_path = common.DATA_RUN_LOGS_DIR / f"extract_{run_start.strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return out_path


# --- main --------------------------------------------------------------------

def run(limit: int | None = None, dry_run: bool = False) -> None:
    cfg = common.load_config()
    decision_factor_vocab = set(cfg["decision_factors"])
    model = cfg["models"]["extraction"]
    pricing = cfg.get("pricing", {}).get(model, {})
    system_prompt = _build_system_prompt(decision_factor_vocab)

    normalized_path = common.DATA_PROCESSED_DIR / "normalized.parquet"
    if not normalized_path.exists():
        print(f"[extract] ERROR: {normalized_path} not found — run pipeline/normalize.py first")
        sys.exit(1)

    df = pd.read_parquet(normalized_path)
    if df.empty:
        print("[extract] normalized.parquet is empty — nothing to extract")
        return

    existing_ids = _load_existing_extracted_ids()
    remaining = df[~df["item_id"].isin(existing_ids)]
    print(f"[extract] {len(df)} normalized items, {len(existing_ids)} already extracted, {len(remaining)} remaining")

    if limit is not None:
        remaining = remaining.head(limit)
        print(f"[extract] --limit {limit}: processing {len(remaining)} items this run")

    items = remaining.to_dict("records")
    batches = _build_batches(items)
    print(f"[extract] {len(items)} items packed into {len(batches)} batches (short items batched up to {BATCH_SIZE}, long items solo)")

    if dry_run:
        print("[extract] --dry-run: no API calls made, no API key required.")
        if batches:
            print("\n--- SYSTEM PROMPT ---")
            print(system_prompt)
            print(f"\n--- USER PROMPT (batch 1 of {len(batches)}, {len(batches[0])} item(s)) ---")
            print(_build_user_prompt(batches[0]))
        return

    load_dotenv(common.REPO_ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[extract] ERROR: GROQ_API_KEY not set in .env — cannot run extraction (edge-case 8.3).")
        print("[extract] Add it to .env and re-run, or use --dry-run to preview the prompt without a key.")
        sys.exit(1)

    client = groq.Groq(api_key=api_key, max_retries=GROQ_CLIENT_MAX_RETRIES)

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_written = 0
    total_failed_items = 0
    run_start = datetime.now(timezone.utc)

    for batch_num, batch in enumerate(batches, start=1):
        resp = _call_groq(client, model, system_prompt, batch)
        time.sleep(BATCH_PACING_SECONDS)  # proactive pacing, not just reactive backoff
        if resp is None:
            total_failed_items += len(batch)
            continue

        usage = resp.usage
        if usage:
            total_prompt_tokens += usage.prompt_tokens or 0
            total_completion_tokens += usage.completion_tokens or 0

        content = resp.choices[0].message.content
        try:
            parsed = json.loads(content)
            results = parsed.get("results", [])
            if not isinstance(results, list):
                raise ValueError("`results` is not a list")
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            print(f"[extract] WARN: batch {batch_num} returned unparseable JSON, skipping {len(batch)} items: {exc}")
            total_failed_items += len(batch)
            continue

        results_by_id = {str(r["item_id"]): r for r in results if isinstance(r, dict) and "item_id" in r}

        batch_written = []
        for item in batch:
            result = results_by_id.get(str(item["item_id"]))
            if result is None:
                print(f"[extract] WARN: no result for item_id={item['item_id']} in batch {batch_num} response (edge-case 8.5)")
                total_failed_items += 1
                continue
            cleaned = _validate_and_clean(result, decision_factor_vocab, item["text"])
            if cleaned is None:
                total_failed_items += 1
                continue
            batch_written.append(cleaned)

        if batch_written:
            _append_extracted(batch_written)
            total_written += len(batch_written)

        print(
            f"[extract] batch {batch_num}/{len(batches)}: +{len(batch_written)} written "
            f"(total {total_written}, failed {total_failed_items}, tokens {total_prompt_tokens + total_completion_tokens})"
        )

    log_path = _write_run_log(run_start, total_prompt_tokens, total_completion_tokens, total_written, total_failed_items, pricing, model)
    estimated_cost = (total_prompt_tokens / 1_000_000) * pricing.get("input_per_million", 0.0) + (
        total_completion_tokens / 1_000_000
    ) * pricing.get("output_per_million", 0.0)
    print(f"[extract] done: {total_written} items extracted, {total_failed_items} failed/skipped")
    print(f"[extract] tokens: {total_prompt_tokens} prompt + {total_completion_tokens} completion, estimated cost ~${estimated_cost:.4f}")
    print(f"[extract] run log: {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 3 — LLM extraction via Groq")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N not-yet-extracted items")
    parser.add_argument("--dry-run", action="store_true", help="Build batches and print the first prompt; make zero API calls, no key required")
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run)

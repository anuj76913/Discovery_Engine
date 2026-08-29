"""Stage 4 — Fixed-Taxonomy Classification & Quantification (architecture.md §6).

Classify the free-text fields (reasons_for_saving, blockers_to_purchase,
info_sought_outside_app) from Stage 3's extracted.jsonl into a FIXED set of
11 opportunity themes -> quantify each theme -> rank -> write
data/processed/opportunity_areas.json.

This replaces an earlier open-ended design (embed phrases with
sentence-transformers -> cluster with HDBSCAN -> name each cluster with a
Groq call), per explicit user decision: they identified 11 concrete wishlist
opportunity themes directly from reading the corpus (config.yaml's
`opportunity_themes`) and asked for the dashboard to be built around exactly
those, rather than whatever an unsupervised clustering pass happens to find.
This also fixes the recurring "off-topic content in a wishlist area"
complaints from the old design (an item-level wishlist-scope filter doesn't
guarantee phrase-level relevance) — a phrase that doesn't clearly match one
of the 11 fixed themes is dropped outright, never forced into the nearest
one or bucketed as "Other" (per explicit user choice).

Edge cases this deliberately handles (see docs/edge-case.md §9):
- 9.2: the count of phrases that matched no theme is logged, not silently
  absorbed.
- 9.3: below `synthesis.min_relevant_items_for_confidence` relevant items,
  the output is still written (so the rest of the pipeline stays
  exercisable) but flagged with `low_sample_warning` at the top level, not
  presented as a confident final ranking.
- 9.6: ranking ties are broken deterministically (score, then
  pct_of_relevant_items, then mention_count, then name) — never dict/set
  iteration order.
- 9.7: phrases are deduplicated and sorted before classification, so a
  re-run against unchanged input reproduces the same theme assignments.
- 9.8: segment_breakdown is a per-theme mention count per segment signal,
  explicitly not expected to sum to 100% (items can carry multiple inferred
  segment signals) — labeled as such in the output.
- 9.4/9.5: cross-theme de-duplication and near-duplicate mention inflation
  are Stage 2's job (already applied upstream); not re-solved here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import groq
import pandas as pd
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PHRASE_FIELDS = ("reasons_for_saving", "blockers_to_purchase", "info_sought_outside_app")
MAX_SAMPLE_QUOTES = 8
MAX_RETRIES = 5
OUTPUT_PATH = common.DATA_PROCESSED_DIR / "opportunity_areas.json"

# Small stopword set for the quote/phrase token-overlap check below — just
# enough to stop generic connector words from producing false "matches".
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "have", "i", "if", "in", "into", "is", "it", "its", "not", "of", "on",
    "or", "our", "that", "the", "there", "this", "to", "was", "we", "with",
}

# Nouns that are structurally content-free in this corpus — they could
# describe almost any complaint/reason ("feature", "app", "issue"...) or are
# near-universal by construction of the wishlist-scope filter ("wishlist"
# itself, ~1 in 8 phrases). Sharing one of these alone between a quote and a
# phrase is not evidence they're about the same thing (observed live: an
# item's "feature not available" blocker matched a quote praising an
# unrelated feature, purely via the shared word "feature") — excluded from
# the topical-overlap check on top of the plain English stopwords above.
_DOMAIN_FILLER_WORDS = {
    "wishlist", "app", "myntra", "item", "items", "issue", "issues",
    "feature", "features", "option", "options", "product", "products",
    "experience", "user", "service", "thing", "things", "problem", "problems",
}


def _tokenize(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z']+", text.lower())
        if t not in _STOPWORDS and t not in _DOMAIN_FILLER_WORDS and len(t) > 2
    }


def _quote_matches_phrase(quote: str, phrase: str) -> bool:
    """Whether a quote plausibly backs a specific phrase, by shared vocabulary.

    Used only for items that contributed more than one phrase (see
    item_phrase_count below) — for those, Stage 3's single representative_quote
    might belong to any one of the item's several reasons/blockers, so we only
    trust it for a given theme when it actually shares wording with that
    theme's phrase, rather than showing it as evidence for all of them.
    """
    return bool(_tokenize(quote) & _tokenize(phrase))


# --- loading & joining -------------------------------------------------------

def _load_relevant_items() -> pd.DataFrame:
    extracted_path = common.DATA_PROCESSED_DIR / "extracted.jsonl"
    normalized_path = common.DATA_PROCESSED_DIR / "normalized.parquet"
    if not extracted_path.exists():
        print(f"[synthesize] ERROR: {extracted_path} not found — run pipeline/extract.py first")
        sys.exit(1)
    if not normalized_path.exists():
        print(f"[synthesize] ERROR: {normalized_path} not found — run pipeline/normalize.py first")
        sys.exit(1)

    extracted_rows = [json.loads(line) for line in open(extracted_path, "r", encoding="utf-8") if line.strip()]
    extracted_df = pd.DataFrame(extracted_rows)
    normalized_df = pd.read_parquet(normalized_path, columns=["item_id", "source", "url"])

    # extracted.jsonl carries no source/url of its own (architecture.md §5's
    # schema is extraction-only) — join back to normalized.parquet for the
    # source/url context that source_breakdown and sample_quotes need.
    merged = extracted_df.merge(normalized_df, on="item_id", how="left")
    missing_source = merged["source"].isna().sum()
    if missing_source:
        print(f"[synthesize] WARN: {missing_source} extracted items had no matching normalized row, dropping")
        merged = merged.dropna(subset=["source"])

    # A `url` column with any non-string cells (e.g. play_store/app_store
    # rows, whose url is always None) gets coerced to a missing-value
    # sentinel by pandas on load/merge — float64 NaN on old pandas, or
    # (confirmed live on pandas 3.0) a NaN-like float that a plain
    # `.apply(... else None)` can't fix either, since pandas' apply on its
    # newer default string-dtype columns re-coerces a returned `None` right
    # back into that same sentinel. json.dump() then serializes it as the
    # bare token `NaN`, which is not valid JSON — every non-Python consumer
    # (including JSON.parse) rejects it. Casting to plain object dtype
    # *before* the string-vs-not test, via `.where()` instead of `.apply()`,
    # is what actually survives: confirmed live that a mixed column (real
    # youtube URLs alongside None-only play_store/app_store ones) now keeps
    # true strings and true Python None side by side.
    merged["url"] = merged["url"].astype(object).where(merged["url"].apply(lambda v: isinstance(v, str)), None)

    return merged


# --- mention extraction --------------------------------------------------

def _build_mentions(relevant_df: pd.DataFrame) -> list[dict]:
    mentions: list[dict] = []
    for row in relevant_df.itertuples(index=False):
        row_d = row._asdict()
        for field in PHRASE_FIELDS:
            for phrase in row_d[field]:
                phrase = str(phrase).strip()
                if not phrase:
                    continue
                mentions.append(
                    {
                        "item_id": row_d["item_id"],
                        "source": row_d["source"],
                        "url": row_d["url"],
                        "phrase": phrase,
                        "field": field,
                        "quote": row_d["representative_quote"],
                        "quote_verified": row_d["quote_verified"],
                        "segment_signals": tuple(row_d["inferred_segment_signals"]),
                        "decision_factors": tuple(row_d["decision_factors"]),
                        "journey_stage": row_d["user_journey_stage"],
                    }
                )
    # Deterministic order regardless of DataFrame row order (edge-case 9.7).
    mentions.sort(key=lambda m: (m["phrase"], m["item_id"], m["field"]))
    return mentions


# --- fixed-taxonomy classification (Groq) ---------------------------------

def _build_classification_system_prompt(themes: list[dict]) -> str:
    theme_lines = "\n".join(f'- {t["id"]}: {t["name"]} — {t["description"]}' for t in themes)
    return f"""You are classifying short phrases extracted from Myntra (an Indian online fashion shopping app) reviews into a FIXED set of known wishlist opportunity themes. Each review mentions the wishlist/save-for-later feature somewhere, but not every reason/blocker/info phrase pulled from it necessarily matches one of these specific themes — some are about unrelated things (payment, delivery, unrelated pricing, order tracking, app crashes, customer support, etc.) that just happen to appear in the same review, or are about the wishlist generally without matching any one theme specifically.

Fixed themes:
{theme_lines}

For each phrase, decide which ONE theme id it matches, using the item's quote for context. If a phrase doesn't clearly and specifically match one of these themes, its theme_id must be null — do not force a loose or generic match, and do not invent a new theme id.

Return ONLY a JSON object shaped exactly like {{"results": [...]}}, with exactly one result object per input item, each containing: item_id (copied exactly) and classifications (an array with one entry per that item's input phrases, each {{"phrase": "...", "theme_id": "..." or null}}, phrase copied verbatim)."""


def _build_classification_user_prompt(batch: list[dict]) -> str:
    parts = []
    for item in batch:
        phrase_lines = "\n".join(f"  - [{p['field']}] {p['phrase']}" for p in item["phrases"])
        parts.append(f"item_id: {item['item_id']}\nquote: \"{item['quote']}\"\nphrases:\n{phrase_lines}")
    return "\n---\n".join(parts)


def _call_groq_classify(client: "groq.Groq", model: str, system_prompt: str, batch: list[dict]):
    user_prompt = _build_classification_user_prompt(batch)
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
                max_tokens=1200,  # gpt-oss reasoning tokens count against this too, not just the JSON output
                reasoning_effort="low",  # fixed-choice classification, not a task needing heavy reasoning
            )
        except groq.RateLimitError:
            print(f"[synthesize] WARN: classification rate limited (attempt {attempt}/{MAX_RETRIES}), backing off {backoff}s")
        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as exc:
            print(f"[synthesize] WARN: classification transient error (attempt {attempt}/{MAX_RETRIES}): {exc}")
        time.sleep(backoff)
        backoff *= 2
    print(f"[synthesize] ERROR: classification batch failed after {MAX_RETRIES} retries, dropping its {len(batch)} items' phrases this run")
    return None


def _classify_phrases_into_themes(
    client: "groq.Groq", model: str, themes: list[dict], relevant_df: pd.DataFrame, batch_size: int, pacing_seconds: int
) -> tuple[dict[tuple[str, str], str], int, int]:
    """Per-item Groq classification: which fixed theme (if any) each of an
    item's reason/blocker/info phrases belongs to. Returns
    {(item_id, phrase): theme_id} — a phrase missing from the map (dropped
    by the model, or its batch failed after retries) is excluded from
    output entirely, per explicit user choice not to keep an "Other"
    bucket."""
    theme_ids = {t["id"] for t in themes}
    items = []
    for row in relevant_df.itertuples(index=False):
        row_d = row._asdict()
        phrases = [
            {"field": field, "phrase": str(p).strip()}
            for field in PHRASE_FIELDS
            for p in row_d[field]
            if str(p).strip()
        ]
        if phrases:
            items.append({"item_id": row_d["item_id"], "quote": row_d["representative_quote"] or "", "phrases": phrases})

    if not items:
        return {}, 0, 0

    system_prompt = _build_classification_system_prompt(themes)
    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    assignments: dict[tuple[str, str], str] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for i, batch in enumerate(batches, start=1):
        resp = _call_groq_classify(client, model, system_prompt, batch)
        time.sleep(pacing_seconds)
        if resp is None:
            continue

        usage = resp.usage
        if usage:
            total_prompt_tokens += usage.prompt_tokens or 0
            total_completion_tokens += usage.completion_tokens or 0

        try:
            parsed = json.loads(resp.choices[0].message.content)
            results_by_id = {str(r["item_id"]): r for r in parsed["results"]}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"[synthesize] WARN: classification batch {i}/{len(batches)} response invalid ({exc}), dropping its items' phrases")
            continue

        for item in batch:
            result = results_by_id.get(item["item_id"])
            if result is None:
                print(f"[synthesize] WARN: classification response missing item {item['item_id']}, dropping its phrases")
                continue
            classifications = result.get("classifications")
            if not isinstance(classifications, list):
                continue
            for c in classifications:
                if not isinstance(c, dict):
                    continue
                phrase = c.get("phrase")
                theme_id = c.get("theme_id")
                if phrase and theme_id in theme_ids:
                    assignments[(item["item_id"], phrase)] = theme_id

        print(f"[synthesize] classification batch {i}/{len(batches)} classified")

    return assignments, total_prompt_tokens, total_completion_tokens


# --- per-theme quantification -----------------------------------------------

def _quantify_theme(theme: dict, member_mentions: list[dict], total_classified_items: int, all_sources: set[str], item_phrase_count: Counter) -> dict:
    by_item: dict[str, dict] = {}
    for m in member_mentions:
        by_item.setdefault(
            m["item_id"],
            {
                "source": m["source"],
                "segment_signals": m["segment_signals"],
                "decision_factors": m["decision_factors"],
                "journey_stage": m["journey_stage"],
            },
        )

    mention_count = len(by_item)
    source_breakdown = dict(Counter(v["source"] for v in by_item.values()))
    segment_breakdown: Counter = Counter()
    for v in by_item.values():
        segment_breakdown.update(v["segment_signals"])
    decision_factor_breakdown: Counter = Counter()
    for v in by_item.values():
        decision_factor_breakdown.update(v["decision_factors"])
    journey_stage_breakdown = dict(Counter(v["journey_stage"] for v in by_item.values()))

    source_diversity_weight = len(source_breakdown) / len(all_sources) if all_sources else 0.0
    score = mention_count * source_diversity_weight

    # Prefer verified quotes, one per item, capped. Extraction (Stage 3) only
    # captures ONE representative_quote per item, not one per phrase — an
    # item with multiple reasons/blockers might have a quote that only
    # supports ONE of them, but that same quote would otherwise get reused
    # as "evidence" for every theme any of its phrases lands in. An item that
    # contributed only one phrase overall is unambiguous — trust it outright.
    # An item with multiple phrases is only trusted for a given theme when
    # its quote shares actual wording with that theme's phrase — otherwise
    # there's no way to know which phrase the quote backs, so it's excluded
    # rather than shown as misleading evidence.
    quotes_seen_items: set[str] = set()
    sample_quotes = []
    for m in sorted(member_mentions, key=lambda m: (not m["quote_verified"], m["item_id"])):
        if not m["quote"] or m["item_id"] in quotes_seen_items:
            continue
        if item_phrase_count.get(m["item_id"], 0) != 1 and not _quote_matches_phrase(m["quote"], m["phrase"]):
            continue
        quotes_seen_items.add(m["item_id"])
        sample_quotes.append({"quote": m["quote"], "source": m["source"], "url": m["url"]})
        if len(sample_quotes) >= MAX_SAMPLE_QUOTES:
            break

    return {
        "opportunity_area": theme["name"],
        "description": theme["description"],
        "category": theme["category"],
        "mention_count": mention_count,
        "pct_of_relevant_items": round(mention_count / total_classified_items, 4) if total_classified_items else 0.0,
        "source_breakdown": source_breakdown,
        "segment_breakdown": dict(segment_breakdown),
        "top_segment_signals": [s for s, _ in segment_breakdown.most_common(5)],
        "decision_factor_breakdown": dict(decision_factor_breakdown),
        "journey_stage_breakdown": journey_stage_breakdown,
        "cross_source_validation": len(source_breakdown) >= 2,
        "score": round(score, 4),
        "source_diversity_weight": round(source_diversity_weight, 4),
        "sample_quotes": sample_quotes,
    }


# --- run log ---------------------------------------------------------------

def _write_run_log(run_start: datetime, prompt_tokens: int, completion_tokens: int, theme_count: int, model: str, pricing: dict) -> Path:
    common.DATA_RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    input_rate = pricing.get("input_per_million", 0.0)
    output_rate = pricing.get("output_per_million", 0.0)
    estimated_cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    log = {
        "stage": "synthesize",
        "model": model,
        "run_started_at": run_start.isoformat(),
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "themes_with_mentions": theme_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": round(estimated_cost, 4),
        "cost_estimate_note": "Approximate only — config.yaml's pricing is not verified against Groq's live rates.",
    }
    out_path = common.DATA_RUN_LOGS_DIR / f"synthesize_{run_start.strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return out_path


# --- main --------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    cfg = common.load_config()
    themes = cfg["opportunity_themes"]
    classification_model = cfg["models"]["classification"]
    pricing = cfg.get("pricing", {}).get(classification_model, {})
    synthesis_cfg = cfg["synthesis"]

    relevant_df = _load_relevant_items()
    relevant_df = relevant_df[relevant_df["is_relevant"]]
    pre_wishlist_filter_count = len(relevant_df)
    # Scoped to wishlist/save-for-later mentions only, per explicit user
    # decision — the broader purchase-decision corpus (fit, price, returns,
    # trust, ...) is still extracted and available in extracted.jsonl, just
    # not what this run's opportunity areas are classified from.
    relevant_df = relevant_df[relevant_df["mentions_wishlist_or_save_for_later"]]
    print(
        f"[synthesize] wishlist-scope filter: {len(relevant_df)}/{pre_wishlist_filter_count} "
        f"relevant items mention wishlist/save-for-later"
    )
    total_relevant_items = len(relevant_df)
    all_sources = set(relevant_df["source"].unique())
    print(f"[synthesize] {total_relevant_items} relevant items across sources: {sorted(all_sources)}")

    low_sample_warning = total_relevant_items < synthesis_cfg["min_relevant_items_for_confidence"]
    if low_sample_warning:
        print(
            f"[synthesize] WARN: only {total_relevant_items} relevant items, below "
            f"synthesis.min_relevant_items_for_confidence={synthesis_cfg['min_relevant_items_for_confidence']} "
            f"— output will be flagged low_sample_warning (edge-case 9.3), not a confident final ranking"
        )

    pre_filter_mentions = _build_mentions(relevant_df)
    print(f"[synthesize] {len(pre_filter_mentions)} phrase mentions extracted from {total_relevant_items} relevant items (pre theme classification)")

    system_prompt = _build_classification_system_prompt(themes)

    if dry_run:
        print("[synthesize] --dry-run: no API calls made, no API key required.")
        sample_items = []
        for row in relevant_df.head(3).itertuples(index=False):
            row_d = row._asdict()
            phrases = [{"field": f, "phrase": str(p).strip()} for f in PHRASE_FIELDS for p in row_d[f] if str(p).strip()]
            if phrases:
                sample_items.append({"item_id": row_d["item_id"], "quote": row_d["representative_quote"] or "", "phrases": phrases})
        print(f"\n--- CLASSIFICATION PROMPT (batch of {len(sample_items)}) ---")
        print("--- SYSTEM ---")
        print(system_prompt)
        print("--- USER ---")
        print(_build_classification_user_prompt(sample_items))
        return

    load_dotenv(common.REPO_ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[synthesize] ERROR: GROQ_API_KEY not set in .env — cannot classify phrases into themes (edge-case 8.3).")
        print("[synthesize] Add it to .env and re-run, or use --dry-run to preview without a key.")
        sys.exit(1)
    client = groq.Groq(api_key=api_key)

    run_start = datetime.now(timezone.utc)
    print("[synthesize] classifying phrases into fixed opportunity themes...")
    assignments, prompt_tokens, completion_tokens = _classify_phrases_into_themes(
        client, classification_model, themes, relevant_df, synthesis_cfg["classification_batch_size"], synthesis_cfg["classification_pacing_seconds"]
    )

    mentions = []
    unmatched = 0
    for m in pre_filter_mentions:
        theme_id = assignments.get((m["item_id"], m["phrase"]))
        if theme_id is None:
            unmatched += 1
            continue
        mentions.append({**m, "theme_id": theme_id})
    print(
        f"[synthesize] {len(mentions)}/{len(pre_filter_mentions)} phrase mentions matched a fixed theme "
        f"({unmatched} matched none and were dropped, edge-case 9.2)"
    )

    # Computed from the matched mention list so quote selection can tell
    # whether an item's one quote unambiguously backs the phrase it's
    # attached to in any given theme.
    item_phrase_count: Counter = Counter(m["item_id"] for m in mentions)

    # Denominator for pct_of_relevant_items. Deliberately NOT
    # total_relevant_items (the full wishlist-scope corpus, 234 in the
    # first fixed-taxonomy run) — per explicit user feedback, that made
    # every area's percentage read as misleadingly small, since most of
    # that corpus is items whose phrases didn't match any of the current
    # fixed themes at all (dropped at classification, edge-case 9.2) and
    # so could never contribute to ANY area's percentage. Scoping to items
    # that landed in at least one theme makes the percentage answer "of
    # the items we could actually bucket, how much of this specific
    # theme is there" instead of being diluted by content this taxonomy
    # doesn't cover.
    total_classified_items = len({m["item_id"] for m in mentions})
    print(
        f"[synthesize] {total_classified_items}/{total_relevant_items} relevant items had at least one "
        f"theme-matched phrase — this is the denominator for each area's pct_of_relevant_items"
    )

    themes_by_id = {t["id"]: t for t in themes}
    by_theme: dict[str, list[dict]] = {}
    for m in mentions:
        by_theme.setdefault(m["theme_id"], []).append(m)

    quantified = [
        _quantify_theme(themes_by_id[theme_id], members, total_classified_items, all_sources, item_phrase_count)
        for theme_id, members in by_theme.items()
    ]

    # Deterministic rank: score desc, then pct desc, then mention_count desc,
    # then name asc — never left to dict/set iteration order (edge-case 9.6).
    quantified.sort(key=lambda a: (-a["score"], -a["pct_of_relevant_items"], -a["mention_count"], a["opportunity_area"]))
    for i, area in enumerate(quantified, start=1):
        area["rank"] = i

    log_path = _write_run_log(run_start, prompt_tokens, completion_tokens, len(quantified), classification_model, pricing)
    cost = (prompt_tokens / 1_000_000) * pricing.get("input_per_million", 0.0) + (completion_tokens / 1_000_000) * pricing.get("output_per_million", 0.0)
    print(f"[synthesize] classification tokens: {prompt_tokens} prompt + {completion_tokens} completion (~${cost:.4f})")
    print(f"[synthesize] {len(quantified)}/{len(themes)} fixed themes found at least one mention")
    print(f"[synthesize] run log: {log_path}")

    _write_output(quantified, total_relevant_items, total_classified_items, all_sources, low_sample_warning, len(themes))


def _write_output(
    opportunity_areas: list[dict], total_relevant_items: int, total_classified_items: int, all_sources: set[str], low_sample_warning: bool, theme_count: int
) -> None:
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_relevant_items": total_relevant_items,
        "total_classified_items": total_classified_items,
        "sources_represented": sorted(all_sources),
        "low_sample_warning": low_sample_warning,
        "note": (
            "Sample size is below the configured confidence floor — treat rankings as illustrative, "
            "not a final result." if low_sample_warning else None
        ),
        "methodology": {
            "taxonomy_size": theme_count,
            "ranking_formula": "score = mention_count * source_diversity_weight, where source_diversity_weight = distinct_sources_in_theme / distinct_sources_in_corpus",
            "corpus_scope": "Two-stage filter: (1) restricted to items where extraction flagged mentions_wishlist_or_save_for_later — not every purchase-decision-relevant item that was extracted; (2) within those items, individual reason/blocker/info phrases are classified into one of a fixed set of named wishlist opportunity themes (defined by manual review of the corpus, not open-ended clustering) — a phrase that doesn't clearly match one of those themes is dropped rather than forced into the nearest one.",
            "pct_of_relevant_items_basis": "Each area's pct_of_relevant_items is mention_count / total_classified_items (items with at least one theme-matched phrase) — NOT / total_relevant_items (the full wishlist-scope corpus). total_relevant_items includes items whose phrases didn't match any current theme, so dividing by it would understate every area's share of the content this taxonomy actually covers.",
        },
        "opportunity_areas": opportunity_areas,
    }
    common.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[synthesize] wrote {len(opportunity_areas)} opportunity areas to {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 4 — fixed-taxonomy classification & quantification via Groq")
    parser.add_argument("--dry-run", action="store_true", help="Print the first classification prompt; make zero API calls, no key required")
    args = parser.parse_args()

    run(dry_run=args.dry_run)

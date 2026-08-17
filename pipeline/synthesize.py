"""Stage 4 — Clustering & Quantification (architecture.md §6).

Embed the free-text fields (reasons_for_saving, blockers_to_purchase,
info_sought_outside_app) from Stage 3's extracted.jsonl -> cluster with
HDBSCAN -> label each cluster with one Groq call -> quantify -> rank ->
write data/processed/opportunity_areas.json.

Embedding + clustering is local/free (sentence-transformers + hdbscan);
only the per-cluster labeling call spends Groq budget, and architecture.md
§5 already notes that's "a small number of calls (tens, not thousands)" —
so unlike Stage 3 there's no --limit needed for cost control, only
--dry-run to preview a labeling prompt without spending anything.

Edge cases this deliberately handles (see docs/edge-case.md §9):
- 9.1/9.2: cluster count and the noise fraction (unique phrases that never
  joined a cluster) are logged, not silently absorbed.
- 9.3: below `clustering.min_relevant_items_for_confidence` relevant items,
  the output is still written (so the rest of the pipeline stays
  exercisable) but flagged with `low_sample_warning` at the top level,
  not presented as a confident final ranking.
- 9.6: ranking ties are broken deterministically (score, then
  pct_of_relevant_items, then mention_count, then name) — never dict/set
  iteration order.
- 9.7: phrases are deduplicated and sorted before embedding, and
  embeddings are unit-normalized before a deterministic HDBSCAN pass, so
  a re-run against unchanged input reproduces the same clusters.
- 9.8: segment_breakdown is a per-cluster mention count per segment
  signal, explicitly not expected to sum to 100% (items can carry
  multiple inferred segment signals) — labeled as such in the output.
- 9.9: the labeling prompt explicitly requires a specific behavior/blocker
  name, not a generic category.
- 9.4/9.5: cross-cluster de-duplication and near-duplicate mention
  inflation are Stage 2's job (already applied upstream); not re-solved
  here.
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
import hdbscan
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PHRASE_FIELDS = ("reasons_for_saving", "blockers_to_purchase", "info_sought_outside_app")
MAX_LABELING_PHRASES = 15
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
    trust it for a given cluster when it actually shares wording with that
    cluster's phrase, rather than showing it as evidence for all of them.
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

    # A `url` column that's all-None in the source data (e.g. every row so
    # far is play_store, whose url is always None) gets silently coerced to
    # float64 NaN by pandas on load/merge. json.dump() then serializes NaN
    # as the bare token `NaN`, which is not valid JSON — every non-Python
    # consumer (including JSON.parse) rejects it. Force real None back.
    merged["url"] = merged["url"].apply(lambda v: v if isinstance(v, str) else None)

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


# --- embedding & clustering --------------------------------------------------

def _cluster_phrases(mentions: list[dict], model_name: str, min_cluster_size: int, min_samples: int) -> dict[str, int]:
    unique_phrases = sorted({m["phrase"] for m in mentions})
    if len(unique_phrases) < min_cluster_size:
        print(f"[synthesize] WARN: only {len(unique_phrases)} unique phrases, below min_cluster_size={min_cluster_size} — no clusters possible")
        return {}

    print(f"[synthesize] embedding {len(unique_phrases)} unique phrases with {model_name}...")
    model = SentenceTransformer(model_name)
    embeddings = model.encode(unique_phrases, normalize_embeddings=True, show_progress_bar=False)

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, metric="euclidean")
    labels = clusterer.fit_predict(np.asarray(embeddings))

    noise_count = int(np.sum(labels == -1))
    cluster_count = len(set(labels)) - (1 if -1 in labels else 0)
    print(f"[synthesize] HDBSCAN: {cluster_count} clusters, {noise_count}/{len(unique_phrases)} phrases unclustered (noise, edge-case 9.2)")

    return {phrase: int(label) for phrase, label in zip(unique_phrases, labels)}


# --- per-cluster quantification -----------------------------------------------

def _quantify_cluster(cluster_id: int, member_mentions: list[dict], total_relevant_items: int, all_sources: set[str], item_phrase_count: Counter) -> dict:
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

    phrase_counts = Counter(m["phrase"] for m in member_mentions)
    representative_phrases = [p for p, _ in phrase_counts.most_common(MAX_LABELING_PHRASES)]

    # Prefer verified quotes, one per item, capped. Extraction (Stage 3) only
    # captures ONE representative_quote per item, not one per phrase — an
    # item with multiple reasons/blockers might have a quote that only
    # supports ONE of them, but that same quote would otherwise get reused
    # as "evidence" for every cluster any of its phrases lands in (observed
    # live: a "payment options" mention showing a quote that was actually
    # about wishlist-saving, from the same item's other reason). An item that
    # contributed only one phrase overall is unambiguous — trust it outright.
    # An item with multiple phrases is only trusted for a given cluster when
    # its quote shares actual wording with that cluster's phrase — otherwise
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
        "cluster_id": cluster_id,
        "mention_count": mention_count,
        "pct_of_relevant_items": round(mention_count / total_relevant_items, 4) if total_relevant_items else 0.0,
        "source_breakdown": source_breakdown,
        "segment_breakdown": dict(segment_breakdown),
        "top_segment_signals": [s for s, _ in segment_breakdown.most_common(5)],
        "decision_factor_breakdown": dict(decision_factor_breakdown),
        "journey_stage_breakdown": journey_stage_breakdown,
        "cross_source_validation": len(source_breakdown) >= 2,
        "score": round(score, 4),
        "source_diversity_weight": round(source_diversity_weight, 4),
        "representative_phrases": representative_phrases,
        "sample_quotes": sample_quotes,
    }


# --- labeling (Groq) -----------------------------------------------------

def _build_labeling_system_prompt() -> str:
    return """You are naming a recurring theme found in real user reviews and comments about Myntra (an Indian online fashion shopping app), for wishlist-to-purchase conversion research.

You'll be given a set of short phrases and a few verbatim quotes that a clustering algorithm grouped together as one theme. Based only on that material:
- Produce a short, SPECIFIC opportunity-area name that states the actual behavior or blocker (e.g. "Uncertainty about fit blocks first-time-brand purchases") — never a vague category like "App Issues" or "Customer Feedback".
- Produce a one-paragraph description grounded only in the given phrases/quotes — do not invent detail beyond what's shown.

Return ONLY a JSON object: {"name": "...", "description": "..."}"""


def _build_labeling_user_prompt(phrases: list[str], quotes: list[dict]) -> str:
    lines = ["Representative phrases:"]
    lines.extend(f"- {p}" for p in phrases)
    if quotes:
        lines.append("\nSample quotes:")
        lines.extend(f'- "{q["quote"]}" (source: {q["source"]})' for q in quotes[:5])
    return "\n".join(lines)


def _call_groq_label(client: "groq.Groq", model: str, system_prompt: str, user_prompt: str):
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
                temperature=0.2,
                max_tokens=500,
            )
        except groq.RateLimitError:
            print(f"[synthesize] WARN: rate limited (attempt {attempt}/{MAX_RETRIES}), backing off {backoff}s")
        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as exc:
            print(f"[synthesize] WARN: transient error (attempt {attempt}/{MAX_RETRIES}): {exc}")
        time.sleep(backoff)
        backoff *= 2
    print(f"[synthesize] ERROR: labeling call failed after {MAX_RETRIES} retries")
    return None


def _label_cluster(client: "groq.Groq", model: str, system_prompt: str, cluster: dict) -> tuple[str, str, int, int]:
    user_prompt = _build_labeling_user_prompt(cluster["representative_phrases"], cluster["sample_quotes"])
    resp = _call_groq_label(client, model, system_prompt, user_prompt)
    fallback_name = f"Unlabeled theme ({', '.join(cluster['representative_phrases'][:3])})"
    if resp is None:
        return fallback_name, "", 0, 0

    usage = resp.usage
    prompt_tokens = usage.prompt_tokens or 0 if usage else 0
    completion_tokens = usage.completion_tokens or 0 if usage else 0

    try:
        parsed = json.loads(resp.choices[0].message.content)
        name = str(parsed["name"]).strip()
        description = str(parsed["description"]).strip()
        if not name or not description:
            raise ValueError("empty name/description")
    except (json.JSONDecodeError, KeyError, ValueError, AttributeError) as exc:
        print(f"[synthesize] WARN: cluster {cluster['cluster_id']} labeling response invalid ({exc}), using fallback name")
        return fallback_name, "", prompt_tokens, completion_tokens

    return name[:150], description, prompt_tokens, completion_tokens


# --- run log ---------------------------------------------------------------

def _write_run_log(run_start: datetime, prompt_tokens: int, completion_tokens: int, cluster_count: int, model: str, pricing: dict) -> Path:
    common.DATA_RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    input_rate = pricing.get("input_per_million", 0.0)
    output_rate = pricing.get("output_per_million", 0.0)
    estimated_cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    log = {
        "stage": "synthesize",
        "model": model,
        "run_started_at": run_start.isoformat(),
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "clusters_labeled": cluster_count,
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
    embedding_model = cfg["embedding"]["model"]
    labeling_model = cfg["models"]["synthesis_labeling"]
    pricing = cfg.get("pricing", {}).get(labeling_model, {})
    clustering_cfg = cfg["clustering"]

    relevant_df = _load_relevant_items()
    relevant_df = relevant_df[relevant_df["is_relevant"]]
    pre_wishlist_filter_count = len(relevant_df)
    # Scoped to wishlist/save-for-later mentions only, per explicit user
    # decision — the broader purchase-decision corpus (fit, price, returns,
    # trust, ...) is still extracted and available in extracted.jsonl, just
    # not what this run's opportunity areas are clustered from.
    relevant_df = relevant_df[relevant_df["mentions_wishlist_or_save_for_later"]]
    print(
        f"[synthesize] wishlist-scope filter: {len(relevant_df)}/{pre_wishlist_filter_count} "
        f"relevant items mention wishlist/save-for-later"
    )
    total_relevant_items = len(relevant_df)
    all_sources = set(relevant_df["source"].unique())
    print(f"[synthesize] {total_relevant_items} relevant items across sources: {sorted(all_sources)}")

    low_sample_warning = total_relevant_items < clustering_cfg["min_relevant_items_for_confidence"]
    if low_sample_warning:
        print(
            f"[synthesize] WARN: only {total_relevant_items} relevant items, below "
            f"clustering.min_relevant_items_for_confidence={clustering_cfg['min_relevant_items_for_confidence']} "
            f"— output will be flagged low_sample_warning (edge-case 9.3), not a confident final ranking"
        )

    mentions = _build_mentions(relevant_df)
    print(f"[synthesize] {len(mentions)} phrase mentions from {total_relevant_items} relevant items")
    # Computed from the FULL mention list (before per-cluster grouping) so
    # quote selection can tell whether an item's one quote unambiguously
    # backs the phrase it's attached to in any given cluster.
    item_phrase_count: Counter = Counter(m["item_id"] for m in mentions)

    if not mentions:
        print("[synthesize] no phrases to cluster — writing an empty opportunity_areas.json")
        _write_output([], total_relevant_items, all_sources, low_sample_warning, embedding_model)
        return

    phrase_to_cluster = _cluster_phrases(
        mentions, embedding_model, clustering_cfg["min_cluster_size"], clustering_cfg["min_samples"]
    )
    if not phrase_to_cluster:
        _write_output([], total_relevant_items, all_sources, low_sample_warning, embedding_model)
        return

    clusters_raw: dict[int, list[dict]] = {}
    for m in mentions:
        label = phrase_to_cluster.get(m["phrase"], -1)
        if label == -1:
            continue
        clusters_raw.setdefault(label, []).append(m)

    quantified = [
        _quantify_cluster(cid, members, total_relevant_items, all_sources, item_phrase_count)
        for cid, members in clusters_raw.items()
    ]
    print(f"[synthesize] {len(quantified)} clusters quantified")

    system_prompt = _build_labeling_system_prompt()

    if dry_run:
        print("[synthesize] --dry-run: no API calls made, no API key required.")
        if quantified:
            sample = quantified[0]
            print(f"\n--- LABELING PROMPT for cluster {sample['cluster_id']} (mention_count={sample['mention_count']}) ---")
            print("--- SYSTEM ---")
            print(system_prompt)
            print("--- USER ---")
            print(_build_labeling_user_prompt(sample["representative_phrases"], sample["sample_quotes"]))
        return

    load_dotenv(common.REPO_ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[synthesize] ERROR: GROQ_API_KEY not set in .env — cannot label clusters (edge-case 8.3).")
        print("[synthesize] Add it to .env and re-run, or use --dry-run to preview a labeling prompt without a key.")
        sys.exit(1)

    client = groq.Groq(api_key=api_key)
    run_start = datetime.now(timezone.utc)
    total_prompt_tokens = 0
    total_completion_tokens = 0

    labeled_areas = []
    for cluster in quantified:
        name, description, p_tok, c_tok = _label_cluster(client, labeling_model, system_prompt, cluster)
        total_prompt_tokens += p_tok
        total_completion_tokens += c_tok
        labeled_areas.append({**cluster, "opportunity_area": name, "description": description})
        print(f"[synthesize] cluster {cluster['cluster_id']} -> \"{name}\" (mention_count={cluster['mention_count']}, score={cluster['score']})")

    # Deterministic rank: score desc, then pct desc, then mention_count desc,
    # then name asc — never left to dict/set iteration order (edge-case 9.6).
    labeled_areas.sort(key=lambda a: (-a["score"], -a["pct_of_relevant_items"], -a["mention_count"], a["opportunity_area"]))
    for i, area in enumerate(labeled_areas, start=1):
        area["rank"] = i
        del area["cluster_id"]
        del area["representative_phrases"]  # internal labeling input, not part of the public schema

    log_path = _write_run_log(run_start, total_prompt_tokens, total_completion_tokens, len(labeled_areas), labeling_model, pricing)
    estimated_cost = (total_prompt_tokens / 1_000_000) * pricing.get("input_per_million", 0.0) + (
        total_completion_tokens / 1_000_000
    ) * pricing.get("output_per_million", 0.0)
    print(f"[synthesize] tokens: {total_prompt_tokens} prompt + {total_completion_tokens} completion, estimated cost ~${estimated_cost:.4f} (unverified pricing, see config.yaml)")
    print(f"[synthesize] run log: {log_path}")

    _write_output(labeled_areas, total_relevant_items, all_sources, low_sample_warning, embedding_model)


def _write_output(opportunity_areas: list[dict], total_relevant_items: int, all_sources: set[str], low_sample_warning: bool, embedding_model: str) -> None:
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_relevant_items": total_relevant_items,
        "sources_represented": sorted(all_sources),
        "low_sample_warning": low_sample_warning,
        "note": (
            "Sample size is below the configured confidence floor — treat rankings as illustrative, "
            "not a final result." if low_sample_warning else None
        ),
        "methodology": {
            "embedding_model": embedding_model,
            "ranking_formula": "score = mention_count * source_diversity_weight, where source_diversity_weight = distinct_sources_in_cluster / distinct_sources_in_corpus",
            "corpus_scope": "Restricted to items where the LLM extraction flagged mentions_wishlist_or_save_for_later — not every purchase-decision-relevant item that was extracted.",
        },
        "opportunity_areas": opportunity_areas,
    }
    common.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[synthesize] wrote {len(opportunity_areas)} opportunity areas to {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 4 — clustering & quantification via Groq")
    parser.add_argument("--dry-run", action="store_true", help="Cluster locally and print the first labeling prompt; make zero API calls, no key required")
    args = parser.parse_args()

    run(dry_run=args.dry_run)

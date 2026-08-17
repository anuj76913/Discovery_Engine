# Architecture — AI Discovery Engine

Scope: implements the Part 1 deliverable defined in
[problemStatement.md](problemStatement.md) only — collection, AI extraction,
clustering/quantification, and a testable output. No scraping/API budget is
paid; no downstream parts (metric decomposition, interviews, MVP) are built
here.

---

## 1. Design Goals (from the problem statement)

1. Pull real public conversation about Myntra / online fashion shopping from
   multiple free sources.
2. Go beyond sentiment/summary — extract *why* (reasons, blockers,
   uncertainties), not just *what* (positive/negative).
3. Turn thousands of unstructured snippets into a small number of ranked,
   **quantified**, evidence-backed opportunity areas.
4. Ship something a reviewer can open as a link and actually explore —
   not a static PDF of findings.
5. Stay operable on free-tier data access and a modest Groq API budget
   (this is a discovery tool, not a production data platform).

---

## 2. High-Level Pipeline

```
┌──────────────┐   ┌──────────────┐   ┌───────────────────┐   ┌────────────────┐   ┌──────────────┐
│  1. COLLECT  │──▶│  2. NORMALIZE │──▶│  3. EXTRACT (LLM)  │──▶│ 4. CLUSTER &     │──▶│ 5. SERVE      │
│  per-source  │   │  common schema│   │  per-item themes/  │   │    QUANTIFY      │   │  dashboard    │
│  scrapers    │   │  + dedup      │   │  reasons/blockers  │   │  opportunity     │   │  (public link)│
└──────────────┘   └──────────────┘   └───────────────────┘   │  areas + scoring │   └──────────────┘
                                                                 └────────────────┘
        raw/*.jsonl        normalized.parquet      extracted.jsonl        opportunity_areas.json
```

Each stage writes its output to disk before the next stage runs. This keeps
the pipeline resumable and keeps Groq API cost visible and re-runnable
per stage instead of re-collecting/re-analyzing everything on every change.

---

## 3. Stage 1 — Collection

Goal: get raw, source-tagged text into a common landing format with zero
paid APIs.

| Source | Method | Library / endpoint | Notes |
|---|---|---|---|
| Google Play reviews | Scrape | `google-play-scraper` (Python) | Pull Myntra app reviews, sorted by "most relevant" and "newest"; paginate up to a capped count per run |
| Apple App Store reviews | Scrape | `app-store-scraper` | Same pattern, iTunes RSS review feed under the hood |
| Reddit | Public JSON | `old.reddit.com/r/<sub>/search.json?q=...` or PRAW with a free read-only app-only token | Target fashion/shopping/India-shopping subreddits; search "Myntra wishlist", "Myntra return", "Myntra size", etc. |
| YouTube comments | Scrape | `youtube-comment-downloader` (no API key) or free YouTube Data API quota | Target Myntra haul/unboxing/review videos found via YouTube search |
| Forums / communities | Manual seed list + `requests` + `BeautifulSoup` | e.g. IndianFashionForum-style threads if crawlable | Best-effort; lowest-volume source, keep scope small |

**Landing format** — every collector emits the same row shape, appended to
`data/raw/<source>.jsonl`:

```json
{
  "source": "play_store | app_store | reddit | youtube | forum",
  "source_id": "unique id from the source (review id, comment id, post id)",
  "text": "raw text",
  "author_meta": "anonymized/aggregate only (e.g. account age bucket) — no PII",
  "rating": "1-5 or null (only app store/play store have this)",
  "timestamp": "ISO 8601 or null if unavailable",
  "url": "permalink if available",
  "collected_at": "ISO 8601 run timestamp"
}
```

Collectors are independent scripts (`collectors/play_store.py`,
`collectors/app_store.py`, `collectors/reddit.py`, `collectors/youtube.py`,
`collectors/forums.py`) runnable individually or via one entrypoint
(`collectors/run_all.py`). Each is idempotent — re-running skips
`source_id`s already on disk.

**Guardrails:**
- Rate-limit / sleep between requests to stay within free/public usage norms
  and avoid IP blocks.
- Cap items per run (config, e.g. 500/source/run) — this is a discovery
  sample, not an exhaustive crawl.
- No PII stored: usernames dropped or hashed, only text + coarse metadata
  kept.

---

## 4. Stage 2 — Normalization

Goal: one clean, deduplicated corpus ready for LLM extraction.

Script: `pipeline/normalize.py`

Steps:
1. **Load** all `data/raw/*.jsonl`.
2. **Filter** to fashion/shopping relevance — drop obviously off-topic rows
   (e.g. a Play Store review that's just "app crashes on login" with no
   product/wishlist/purchase content) using a cheap keyword pre-filter
   before spending LLM budget on it.
3. **Dedup** near-identical text (copy-pasted reviews, repeated comments)
   via exact-match + simple text-similarity hashing (e.g. MinHash or a
   normalized-text fingerprint).
4. **Language filter** — keep English (+ optionally Hinglish, common in
   this domain) since the extraction prompts are English; flag/drop the
   rest.
5. **Chunk long text** (rare for reviews/comments, but Reddit posts can be
   long) to stay well under per-call token limits.
6. **Write** `data/processed/normalized.parquet` — the single input to
   Stage 3, with a stable `item_id` per row.

---

## 5. Stage 3 — LLM Extraction (Groq API)

Goal: convert each raw text snippet into **structured signal**, not prose.
This is what makes the engine "beyond summarization."

Script: `pipeline/extract.py`

For each normalized item, call the Groq API with a fixed extraction
schema (using tool-use / forced structured output — e.g. Groq's JSON
mode — so results are machine-parseable, not free text to re-parse):

```json
{
  "item_id": "...",
  "is_relevant": true,
  "mentions_wishlist_or_save_for_later": true,
  "mentions_purchase_decision": true,
  "user_journey_stage": "browsing | saved_not_bought | compared_alternatives | bought | returned | abandoned",
  "reasons_for_saving": ["liked style", "waiting for price drop", "..."],
  "blockers_to_purchase": ["size/fit uncertainty", "price too high", "wanted more reviews", "..."],
  "info_sought_outside_app": ["influencer reviews", "friend opinion", "..."],
  "decision_factors": ["fit", "price", "reviews", "occasion", "styling", "social_validation"],
  "inferred_segment_signals": ["price-sensitive", "occasion-driven", "repeat buyer", "..."],
  "sentiment": "positive | negative | neutral | mixed",
  "representative_quote": "verbatim short excerpt supporting the above",
  "confidence": 0.0
}
```

Notes on this design:
- **Controlled vocabulary where possible** (e.g. `decision_factors` from a
  fixed enum list mirrored from the problem statement's question list),
  plus a small **free-text field** (`blockers_to_purchase`,
  `reasons_for_saving`) so novel themes aren't forced into a box —
  clustering in Stage 4 is what turns the free text into a stable taxonomy.
- **`representative_quote`** is mandatory — every downstream opportunity
  area must trace back to real evidence, not an LLM paraphrase.
- **`is_relevant: false`** short-circuits the row out of Stage 4 (handles
  anything the keyword pre-filter missed).
- Batch multiple items per API call (e.g. 5–10 short reviews per request)
  where possible to cut cost/latency, falling back to 1-per-call for long
  items.
- Model choice: a fast/cheap Groq-hosted model (e.g. `llama-3.1-8b-instant`)
  for this high-volume, per-item pass; reserve a stronger Groq-hosted model
  (e.g. `llama-3.3-70b-versatile`) for Stage 4 synthesis where reasoning
  quality matters more than throughput.
- Output: `data/processed/extracted.jsonl`, one structured record per
  input item, plus a run log of token usage/cost for transparency.

---

## 6. Stage 4 — Clustering & Quantification

Goal: turn thousands of structured-but-still-granular extractions into a
short, ranked list of **opportunity areas** — the actual output the
business decomposition and interviews (later, out of scope here) will
consume.

Script: `pipeline/synthesize.py`

Steps:
1. **Embed** the free-text fields (`blockers_to_purchase`,
   `reasons_for_saving`, `info_sought_outside_app`) using an embedding
   model, to group semantically similar phrases (e.g. "not sure about my
   size", "sizing runs small", "no size chart" → one cluster:
   *size/fit uncertainty*).
2. **Cluster** (e.g. HDBSCAN or agglomerative clustering over embeddings)
   into candidate opportunity-area groups.
3. **Label each cluster** with a Groq call: given N representative
   phrases + quotes from the cluster, produce a short opportunity-area
   name and one-paragraph description. This is the one place a stronger
   model is worth it — it's a small number of calls (tens, not thousands).
4. **Quantify** each opportunity area:
   - `mention_count` — number of source items mapped into this cluster
   - `pct_of_relevant_items` — mention_count ÷ total relevant items
   - `source_breakdown` — mention_count per source (Play Store, Reddit, …)
   - `segment_breakdown` — cross-tab against `inferred_segment_signals`
   - `cross_source_validation` — flags whether the theme appears in ≥2
     independent sources (protects against one noisy source dominating)
5. **Rank** opportunity areas by a simple transparent score, e.g.
   `score = mention_count × source_diversity_weight`, not a black-box
   metric — the ranking logic must be inspectable in the output.
6. **Attach evidence** — each opportunity area keeps its top 5–10
   `representative_quote`s with source/link, so the dashboard can show
   proof, not just a number.
7. Write `data/processed/opportunity_areas.json` — the final artifact.

Example shape of one opportunity area in the output:

```json
{
  "opportunity_area": "Size/fit uncertainty blocks wishlist conversion",
  "description": "Users save items they like but hesitate to buy because they can't confirm fit, especially for brands they haven't bought before...",
  "mention_count": 184,
  "pct_of_relevant_items": 0.22,
  "source_breakdown": {"play_store": 61, "app_store": 40, "reddit": 70, "youtube": 13},
  "top_segment_signals": ["first-time-brand buyer", "price-sensitive"],
  "sample_quotes": [
    {"quote": "...", "source": "reddit", "url": "..."},
    {"quote": "...", "source": "play_store", "url": null}
  ]
}
```

---

## 7. Stage 5 — Serve (the testable deliverable)

Goal: a public link a reviewer can open and explore — filter, drill into
evidence, and see the quantification, not just read a static report.

**Approach:** a small Streamlit app (`app/dashboard.py`) reading the
precomputed `opportunity_areas.json` (+ `extracted.jsonl` for drill-down),
deployed free on **Streamlit Community Cloud**.

Dashboard views:
1. **Ranked opportunity areas** — bar chart of `mention_count` /
   `pct_of_relevant_items`, sortable, with description on hover/click.
2. **Source breakdown** — per opportunity area, stacked bar across sources,
   to show it's not a single-source artifact.
3. **Evidence drill-down** — click an opportunity area → see its sample
   quotes with source/link.
4. **Segment cross-tab** — table of opportunity area × inferred segment
   signal, to seed later segment-targeting for interviews.
5. **Methodology tab** — short static explanation of the 5-stage pipeline
   (collection → normalize → extract → cluster/quantify → serve), so the
   dashboard is self-explaining without needing this doc alongside it —
   this doubles as the "1 slide explaining how it works" content later.

The dashboard is **read-only over precomputed data** (no live Groq calls
triggered by public visitors) — this keeps the public link free to host and
avoids exposing API cost/keys to anonymous users. The pipeline itself is
re-run manually/on a schedule by the project owner to refresh the data the
dashboard reads.

---

## 8. Repository Layout

```
Discovery Engine/
├── docs/
│   ├── problemStatement.md
│   └── architecture.md
├── collectors/
│   ├── play_store.py
│   ├── app_store.py
│   ├── reddit.py
│   ├── youtube.py
│   ├── forums.py
│   └── run_all.py
├── pipeline/
│   ├── normalize.py
│   ├── extract.py
│   └── synthesize.py
├── app/
│   └── dashboard.py
├── data/
│   ├── raw/            # <source>.jsonl, gitignored
│   ├── processed/       # normalized.parquet, extracted.jsonl, opportunity_areas.json
│   └── run_logs/        # token usage / cost per pipeline run
├── config.yaml           # source lists, caps per run, model names, keyword filters
├── requirements.txt
└── .env.example           # GROQ_API_KEY, etc. (never committed)
```

---

## 9. Config & Secrets

- `config.yaml` — non-secret run parameters: subreddit list, app IDs,
  YouTube search seed terms, per-source item caps, keyword pre-filter list,
  decision-factor enum, model names per stage.
- `.env` (gitignored) — `GROQ_API_KEY` only. Never referenced from the
  deployed Streamlit app (which only reads static output files), so the
  key never needs to exist in the public deployment environment.

---

## 10. Cost & Rate-Limit Control

- Per-source item caps in `config.yaml` keep both scraping volume and LLM
  call volume bounded and predictable per run.
- Keyword pre-filter in Stage 2 avoids spending LLM calls on
  obviously-irrelevant rows (login/crash bugs, unrelated complaints).
- Cheap model for high-volume Stage 3 extraction; stronger model reserved
  for the low-volume Stage 4 cluster-labeling calls.
- Batched extraction calls (multiple short items per request) where safe.
- `data/run_logs/` records tokens + estimated cost per run so spend is
  visible before scaling up sample size.

---

## 11. Known Limitations (acceptable for a discovery-stage tool)

- Free scraping is best-effort — sources may throttle, change markup, or
  cap how far back review history goes. The pipeline should log skipped/
  failed items rather than fail the whole run.
- Segment inference (`inferred_segment_signals`) is LLM-inferred from text,
  not verified demographic data — treated as a directional signal to guide
  later interview targeting, not a hard segmentation.
- English/Hinglish-only coverage will under-represent other-language user
  conversations.
- Clustering quality depends on embedding + clustering hyperparameters;
  cluster labels should be spot-checked against sample quotes before being
  trusted as final opportunity areas.

---

## 12. What This Architecture Deliberately Excludes

Per `problemStatement.md`'s scope note: no metric decomposition logic, no
interview tooling, no MVP feature, no success-metric instrumentation, and
no risk/mitigation content live in this system. The only output this
architecture is responsible for is `opportunity_areas.json` and the
dashboard that renders it.

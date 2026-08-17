# Implementation Plan — AI Discovery Engine (Part 1)

Phase-wise build plan derived from [architecture.md](architecture.md) and
[problemStatement.md](problemStatement.md). Scope is Part 1 only: collection
→ normalization → LLM extraction → clustering/quantification → a public,
explorable dashboard. Parts 2–7 (metric decomposition, interviews, MVP,
etc.) are out of scope here.

## Decisions locked in before build

- **Frontend:** custom React/Next.js app instead of the Streamlit spec in
  architecture.md §7 — same dashboard content (ranked list, source
  breakdown, evidence drill-down, segment cross-tab, methodology tab), a
  different presentation layer, for a higher-quality reviewer-facing UI.
- **LLM provider:** Groq API (`GROQ_API_KEY`), per architecture.md's cost
  design — `llama-3.1-8b-instant` for extraction, `llama-3.3-70b-versatile`
  for cluster labeling.
- **Data:** the real 5-stage pipeline is being built, not mocked. Collectors
  run for real (free/keyless sources). Extraction and synthesis are
  LLM-gated — code is built and dry-run-tested now; the full-cost run
  happens once the user has added `GROQ_API_KEY` to `.env`.
- **Secrets:** the user adds their own `GROQ_API_KEY` to a local `.env`;
  only `.env.example` is ever committed.

## Environment notes discovered during setup

- This machine has two Python installs on `PATH`; the one that actually
  works is `AppData/Local/Python/pythoncore-3.14-64/python.exe` (Python
  3.14) — the `Program Files/Python313` install has an incomplete stdlib
  and the AppData `bin/python.exe` shim is broken. The project venv
  (`.venv/`) is built from the working 3.14 interpreter.
- `app-store-scraper` (the package named in architecture.md §3) is
  unmaintained and hard-pins `requests==2.23.0`, which conflicts with every
  other dependency. Superseded with a direct call to Apple's public iTunes
  RSS customer-reviews feed
  (`itunes.apple.com/in/rss/customerreviews/id=<id>/sortBy=mostRecent/json`)
  using `requests` — functionally identical, since that's what the package
  wraps internally per architecture.md's own description. Confirmed
  reachable and returning real review entries for Myntra's App Store ID
  (`907394059`, bundle `com.myntra.Myntra`).
- Connectivity confirmed from this environment: Play Store (200), iTunes
  (200), YouTube (200).
- Reddit's anonymous JSON endpoints are now fully login-gated, confirmed
  live during Phase 1: `www.reddit.com/*.json` returns 403, and
  `old.reddit.com/*.json` (including `/search.json`) redirects to
  `/login/?reason=lor2...` regardless of User-Agent — this is a platform
  change since architecture.md §3 was written, not a fixable header/UA
  issue. `reddit.py` uses architecture.md's own named fallback instead:
  PRAW in read-only app-only mode, gated on `REDDIT_CLIENT_ID` /
  `REDDIT_CLIENT_SECRET` in `.env` (free — a "script" app registered at
  reddit.com/prefs/apps, no Reddit account password involved). Missing
  credentials degrade to 0 rows collected with a clear log message rather
  than a crash, same pattern as youtube.py/forums.py with empty seed lists.
- The iTunes RSS customer-reviews feed (`app_store.py`) is real but flaky
  in practice: it returned 50 real review entries on the very first fetch
  during setup, then returned zero `entry` items on every retry afterward
  (across country/sort variants, and after a 20s cooldown) for the rest of
  the session. Parsing logic was verified correct by replaying the
  originally-captured response through `_to_row` — 50/50 entries parsed
  cleanly — so this is the endpoint throttling/degrading, not a code bug;
  matches architecture.md §11's "free scraping is best-effort" caveat.

---

## Phase 0 — Repo Scaffold

- `git init`, `.gitignore` (`.env`, `data/raw/*`, `data/processed/*`,
  `data/run_logs/*`, venv, `node_modules/`, `.next/`).
- Directory layout per architecture.md §8: `collectors/`, `pipeline/`,
  `data/{raw,processed,run_logs}/`, `frontend/` (replaces `app/dashboard.py`).
- `requirements.txt` (version-floored, not pinned, so pip resolves wheels
  compatible with the installed Python — the original architecture.md pins
  predate Python 3.14 and have no prebuilt wheels for it).
- `.env.example` with `GROQ_API_KEY=` only.
- `config.yaml`: Myntra Play Store package id, App Store track id, subreddit
  list, YouTube seed video list, per-source item caps (default 500),
  keyword pre-filter list, `decision_factors` enum (fit, price, reviews,
  occasion, styling, social_validation), model names per stage.
- Python venv + `pip install -r requirements.txt`.

**Verify:** all packages importable in the venv.

---

## Phase 1 — Collectors (real run, no API key needed)

`collectors/common.py` (shared landing-row schema + append-only JSONL
writer + idempotent `source_id` skip), then:

- **play_store.py** — `google_play_scraper.reviews`, sort
  `MOST_RELEVANT` then `NEWEST`, capped pagination.
- **app_store.py** — direct `requests` calls against the iTunes RSS
  customer-reviews feed (see environment note above), paginated.
- **reddit.py** — PRAW read-only app-only client (`REDDIT_CLIENT_ID`/
  `REDDIT_CLIENT_SECRET` in `.env`; see environment note above), searches
  each configured subreddit × search-term combination, skip-and-log a
  subreddit rather than aborting the run.
- **youtube.py** — `youtube-comment-downloader` against a curated seed
  list of Myntra haul/review video URLs from `config.yaml`.
- **forums.py** — best-effort stub, manual seed list + `requests` +
  `BeautifulSoup`, acceptable to yield near-zero rows.
- **run_all.py** — runs all five, isolates failures per collector, prints
  an item-count summary.

No PII stored: usernames dropped, only text + coarse metadata kept.

**Verify:** run with small caps, confirm `data/raw/*.jsonl` rows match the
landing schema; re-run and confirm no duplicate `source_id`s.

---

## Phase 2 — Normalize

`pipeline/normalize.py`: load all raw JSONL → keyword pre-filter →
exact + near-dup dedup (normalized-text fingerprint) → language filter
(`langdetect`, English kept, Hinglish flagged not hard-dropped since it's
mostly latin-script) → chunk long text → assign stable `item_id` → write
`data/processed/normalized.parquet`.

**Verify:** parquet loads, row count sane vs. raw input count.

---

## Phase 3 — Extract (Groq, LLM-gated)

`pipeline/extract.py`: forced JSON-mode Groq call per item using the exact
schema in architecture.md §5 (`is_relevant`, `user_journey_stage`,
`reasons_for_saving`, `blockers_to_purchase`, `info_sought_outside_app`,
`decision_factors`, `inferred_segment_signals`, `sentiment`,
`representative_quote`, `confidence`). Batches 5–10 short items/call, falls
back to 1/call for long items. Model: `llama-3.1-8b-instant`. Writes
`data/processed/extracted.jsonl` + a token/cost run log. `--dry-run` and
`--limit N` flags so the user can sanity-check before spending budget.
Exits with a clear message if `GROQ_API_KEY` is missing.

**Verify:** code + `--dry-run` output shape now; full run once the user has added `GROQ_API_KEY`.

---

## Phase 4 — Synthesize (Groq, LLM-gated)

`pipeline/synthesize.py`: embed free-text fields locally with
`sentence-transformers` → cluster with `hdbscan` → one Groq call per
cluster (`llama-3.3-70b-versatile`) to name + describe it → quantify
(`mention_count`, `pct_of_relevant_items`, `source_breakdown`,
`segment_breakdown`, `cross_source_validation`) → rank by the transparent
`score = mention_count × source_diversity_weight` formula → attach top
5–10 `sample_quotes` → write `data/processed/opportunity_areas.json`
matching architecture.md §6's example shape exactly (this is the
frontend's data contract).

**Verify:** same gating as Phase 3 — full run needs the API key and Phase 3's output.

---

## Phase 5 — Frontend (Next.js dashboard)

`frontend/`: Next.js (App Router) + TypeScript + Tailwind, reading
`data/processed/opportunity_areas.json` (+ `extracted.jsonl` for
drill-down) — no live Groq calls from the deployed app, per architecture.md
§7's "read-only over precomputed data" constraint.

Until Phase 3/4 produce real output, build against one clearly-labeled dev
fixture matching the exact schema, so the real file drops in later with no
code change.

Views (content spec from architecture.md §7, as real UI components):
1. Ranked opportunity areas — sortable bar chart of `mention_count` /
   `pct_of_relevant_items`, expandable description.
2. Source breakdown — stacked bar per opportunity area across sources.
3. Evidence drill-down — sample quotes with source/link.
4. Segment cross-tab — opportunity area × `inferred_segment_signals` table.
5. Methodology tab — static explanation of the 5-stage pipeline.

**Verify:** `npm run dev`, click through all 5 views against the dev fixture, confirm responsive layout and no console errors; re-verify against real data once Phase 3/4 are run.

---

## Phase 6 — Wire-up & Handoff

- Root `README.md`: how to run each stage in order, where `GROQ_API_KEY`
  goes, how to run the frontend.
- Once the user has added `GROQ_API_KEY`: run Phase 3 → Phase 4 for real
  (flag Groq spend before a large-cap run), then swap the frontend from
  dev fixture to real `opportunity_areas.json`.
- Deploy frontend to Vercel (free tier) for the public link — confirm with
  the user before the actual deploy/publish action.

---

## Execution order

Phases 0, 1, 2, and 5 (against the dev fixture) have no blockers. Phases
3–4's real runs, and swapping the frontend to real data, are blocked on
the user adding `GROQ_API_KEY` — flagged explicitly when reached rather
than silently left on fixture data.

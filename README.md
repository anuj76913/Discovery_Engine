# Myntra Wishlist-to-Purchase Discovery Engine

An AI-powered discovery pipeline that scrapes public conversation about
Myntra from free sources, extracts structured signal with an LLM (reasons,
blockers, journey stage — not just sentiment), clusters that signal into
ranked opportunity areas, and serves them in an explorable dashboard.

This is Part 1 only (the discovery engine itself), as scoped in
[docs/problemStatement.md](docs/problemStatement.md). See
[docs/architecture.md](docs/architecture.md) for the full design and
[docs/implementation-plan.md](docs/implementation-plan.md) for what was
actually built, phase by phase, including every real-world deviation from
the original design (dead endpoints, platform changes, bugs found and
fixed). [docs/edge-case.md](docs/edge-case.md) catalogs the corner cases
the pipeline is built to handle.

## Pipeline

```
collect → normalize → extract (Groq LLM) → synthesize (cluster + Groq LLM) → serve (Next.js)
```

Each stage writes its output to disk before the next stage runs, so it's
resumable and each stage's cost/output is inspectable independently.

## One-time setup

**Python** (collectors + pipeline):

```
# This repo's working interpreter — see implementation-plan.md's
# "Environment notes" if `python` on your PATH resolves to something else.
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Secrets** — copy `.env.example` to `.env` and fill in:

| Variable | Required for | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | Stage 3 (extract), Stage 4 (synthesize) | Free key at [console.groq.com](https://console.groq.com) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit collection only | Free "script" app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — read-only, no account password used |

Everything else (Play Store, App Store, YouTube, forums) needs no key.
Missing Reddit credentials just means 0 rows collected from that source,
not a crash — the run log tells you.

**Frontend:**

```
cd frontend
npm install
```

## Running the pipeline

```
# 1. Collect (real network calls, no API key needed)
.venv\Scripts\python.exe collectors\run_all.py --limit 500

# 2. Normalize
.venv\Scripts\python.exe pipeline\normalize.py

# 3. Extract (spends Groq budget — sanity-check first)
.venv\Scripts\python.exe pipeline\extract.py --dry-run
.venv\Scripts\python.exe pipeline\extract.py --limit 50   # small real test
.venv\Scripts\python.exe pipeline\extract.py              # full run, all remaining items

# 4. Synthesize (spends a small amount of Groq budget — one call per cluster)
.venv\Scripts\python.exe pipeline\synthesize.py --dry-run
.venv\Scripts\python.exe pipeline\synthesize.py
```

Both `extract.py` and `synthesize.py` are idempotent — re-running skips
items already processed, so an interrupted run resumes rather than
re-spending budget from scratch. Each also writes a token-usage/estimated-cost
run log to `data/run_logs/` (the cost estimate uses pricing pinned in
`config.yaml`, marked there as unverified against Groq's live rates — treat
it as directional).

Per-source item caps, the keyword pre-filter, model names, and clustering
thresholds all live in `config.yaml`.

## Running the frontend

```
cd frontend
npm run dev      # http://localhost:3000
```

Reads `data/processed/opportunity_areas.json` directly (a plain filesystem
read, no API route, no live model calls from the deployed app) — run the
pipeline at least through Stage 4 first, or the dashboard shows an empty
state explaining that.

`npm run build && npm run lint` before considering a change done.

## Current state of this repo

- **Collected:** 20,100 Play Store reviews, 30 YouTube comments, 5 forum
  threads — real data, verified. App Store's feed is flaky (works
  intermittently); Reddit needs your own API credentials (see above).
- **Extracted/synthesized:** verified correct end-to-end against a small
  real sample (48 items → 4 real, specific opportunity areas), but the
  full-corpus run over all ~20K collected items hasn't been run yet — see
  the `--limit`-free commands above. `opportunity_areas.json` currently
  reflects that small sample and is flagged `low_sample_warning: true`
  accordingly; the dashboard surfaces that warning rather than hiding it.
- **Frontend:** built and verified in a real browser (all 4 views, evidence
  drill-down, light/dark theme, mobile layout, zero console errors) against
  the current real (small-sample) data.
- **Not yet done:** the full-corpus Stage 3/4 run, and deployment (Vercel,
  free tier — the frontend's data file will need an explicit gitignore
  exception or a copy-into-`frontend/` step first, since `data/processed/*`
  is gitignored locally and Vercel doesn't see outside the deployed root).

## Repository layout

```
collectors/     one script per source + run_all.py entrypoint
pipeline/       normalize.py, extract.py, synthesize.py
frontend/       Next.js dashboard
data/           raw/, processed/, run_logs/ — all gitignored, regenerated by running the pipeline
config.yaml     source lists, item caps, keyword filter, models, clustering params
docs/           problemStatement.md, architecture.md, implementation-plan.md, edge-case.md
```

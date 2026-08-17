# Edge Cases — AI Discovery Engine

Corner scenarios across the 5-stage pipeline in
[architecture.md](architecture.md), organized to match
[implementation-plan.md](implementation-plan.md)'s phases. Each entry is a
scenario the code must not silently mishandle — either handle it
explicitly or fail loud (log + skip), never fail silent or crash the whole
run.

---

## 1. Collection — Google Play

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 1.1 | App has fewer reviews available than the configured cap | Naive pagination loop hangs or errors on the last page | Stop cleanly when the library returns an empty/short page; log actual count vs. cap |
| 1.2 | Review text is empty or whitespace-only (rating-only review) | Passes through as a zero-signal row, wastes Stage 3 budget | Keyword pre-filter in Stage 2 must drop empty-text rows before extraction |
| 1.3 | `google-play-scraper`'s internal pagination token expires mid-run | Partial page fetch raises, killing the whole collector | Wrap page fetches in try/except, keep what was collected so far, log the failure point |
| 1.4 | Google throttles/blocks the IP after sustained scraping | Whole run fails past a certain volume | Sleep between pages, cap per-run volume (config), treat a block as a soft stop not a crash |
| 1.5 | Review is emoji-only or non-Latin script (Hindi, Tamil, etc.) | Not useful to an English extraction prompt, but shouldn't be dropped at collection | Collect as-is; language filtering is Stage 2's job, not the collector's |
| 1.6 | Wrong package ID in `config.yaml` (typo pulls a different app entirely) | Silently poisons the whole corpus with off-topic data | Sanity-check collected app name/package against expected value at the start of a run |

## 2. Collection — Apple App Store (iTunes RSS)

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 2.1 | RSS pagination beyond ~10 pages returns empty/malformed feed (Apple's known limit) | Loop must terminate, not retry forever | Stop when a page has no `entry` array; don't treat it as a transient error |
| 2.2 | Storefront (`/in/` vs `/us/`) returns a different review set | "All reviews" is actually one-country's reviews unless multiple storefronts are queried | Document which storefront(s) are configured; note in run log which country the sample represents |
| 2.3 | First entry in the feed is the app metadata record, not a review (no `im:rating`/`im:voteCount`) | Naive parsing treats it as a malformed review | Skip entries missing the review-specific fields (`content`, `im:rating`) rather than erroring |
| 2.4 | Same review reappears across two page fetches (feed reordering during pagination) | Duplicate rows inflate mention counts downstream | `source_id` = review's own `id` field, dedup on write (already the idempotency contract) |
| 2.5 | Apple changes the RSS feed's JSON shape | Silent parse failures | Fail loud on unexpected shape (missing `feed.entry` key) instead of returning zero rows silently |

## 3. Collection — Reddit

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 3.1 | `www.reddit.com` returns 403 without a browser-like User-Agent (confirmed during setup) | Silent zero-result run looks like "no discussion found" | Use `old.reddit.com` + descriptive UA; treat a 403/429 as a logged skip for that subreddit, not proof of no data |
| 3.2 | Search term "myntra" matches an unrelated Reddit username or an off-topic post that happens to contain the word | Off-topic rows enter the corpus | Keyword pre-filter in Stage 2, not the collector, is the relevance gate — collector stays dumb |
| 3.3 | Post/comment shows `[deleted]` or `[removed]` as its body | Zero-signal row that still has a valid `source_id` | Drop rows where `text` is exactly `[deleted]`/`[removed]` before writing to `data/raw/` |
| 3.4 | Subreddit is private, banned, or doesn't exist | Request fails for that one subreddit | Skip-and-log per subreddit; don't abort the full Reddit collector run |
| 3.5 | A single post is copy-pasted by the same account across multiple subreddits (cross-posting) or duplicated by bots | Inflates `mention_count` for whatever theme it contains | Stage 2's near-duplicate dedup (not just exact-match) must catch this across sources, not just within one |
| 3.6 | Long-form Reddit post (1000+ words) far exceeds a typical review's length | Breaks the assumption that items are short; wastes extraction budget on mostly-irrelevant paragraphs | Stage 2's chunking step explicitly targets this case per architecture.md §4.5 |

## 4. Collection — YouTube

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 4.1 | Seed video is deleted, made private, or region-locked after being added to `config.yaml` | Collector errors on that video | Catch per-video, skip and log, continue with the rest of the seed list |
| 4.2 | Comments are disabled on a video | `youtube-comment-downloader` returns nothing | Not an error — log zero comments and move on |
| 4.3 | Bot/spam comments (unrelated engagement-farming text, link spam) | Pollutes the corpus with noise | Keyword pre-filter in Stage 2 catches most; not a collector-level concern |
| 4.4 | Comment is Hinglish in Latin script mixed with Devanagari mid-sentence | Common in this domain; a naive language filter drops real signal | Stage 2 language filter flags rather than hard-drops (per architecture.md §4.4) |
| 4.5 | `youtube-comment-downloader` breaks because YouTube changed its page structure | Whole collector fails silently or errors | Fail loud with a clear message so it's caught in code review/CI, not discovered as "zero YouTube data" downstream |

## 5. Collection — Forums

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 5.1 | Seeded forum site has changed its HTML structure since the selector was written | `BeautifulSoup` selectors silently return empty results | Log a warning if a scrape yields zero items from a previously-productive source, so it's noticed, not just absorbed as "low-volume source" |
| 5.2 | `robots.txt` disallows scraping the target path | Legal/ToS risk even on a "free" source | Check `robots.txt` before scraping; skip sources that disallow it rather than ignoring the signal |
| 5.3 | Forum requires login to view thread content | Nothing to scrape | Treat as out of scope for this best-effort source, don't block the run |

## 6. Collection — Cross-cutting

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 6.1 | Two different sources independently produce the same `source_id` value (e.g., both use small integers) | ID collision causes silent overwrite/skip across sources | Namespace `source_id` uniqueness by `source` — dedup logic must key on `(source, source_id)`, not `source_id` alone |
| 6.2 | Collector process crashes mid-write, leaving a truncated final line in the JSONL file | Corrupt line breaks every downstream reader | Append-only writer flushes/writes one full JSON object per line; normalize.py should skip-and-log unparseable lines instead of crashing the whole load |
| 6.3 | Two collectors (or two manual re-runs) write to the same `data/raw/<source>.jsonl` concurrently | Interleaved writes corrupt the file | Document that collectors are not safe to run concurrently against the same source file; run sequentially (as `run_all.py` already does) |
| 6.4 | A user's review/comment text itself contains PII (email, phone number, full name) even though the *account* metadata is dropped | "No PII stored" guardrail (architecture.md §3) is violated via the free-text field itself | This can only be fully caught after extraction — flag as a known limitation, and consider a regex pass (email/phone patterns) before any evidence is surfaced publicly on the dashboard |
| 6.5 | `collected_at` timestamps use inconsistent timezone awareness (naive vs. UTC) across collectors | Breaks any later "within N days" style analysis | All collectors write ISO 8601 with explicit UTC offset, no naive datetimes |
| 6.6 | One collector fails entirely (exception) | Should not block the other four | `run_all.py` isolates exceptions per collector, per implementation-plan.md Phase 1 |

## 7. Normalization

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 7.1 | Keyword pre-filter drops a genuinely relevant row that doesn't use expected vocabulary (e.g., "saved it for later" vs. the literal word "wishlist") | Silent false-negative shrinks the corpus without anyone noticing | Keep the filter list broad and log the drop-rate per run so a sudden jump is visible; treat the filter as a cost-control net, not a precision tool — Stage 3's `is_relevant` field is the real gate |
| 7.2 | Keyword pre-filter keeps an irrelevant row because it happens to contain a filter word out of context (e.g., "price" in a shipping-cost complaint unrelated to product decisions) | Wastes Stage 3 budget on noise | Acceptable — Stage 3's LLM `is_relevant` flag is the precision backstop, per architecture.md §5 |
| 7.3 | Two different users independently write near-identical short text ("Great app!", "Love it") | Near-dup hashing merges genuinely independent signal into one row, undercounting real volume | Tune similarity threshold conservatively for short text — exact-match dedup only below some length floor, fuzzy dedup only above it |
| 7.4 | `langdetect` misclassifies short strings (known instability under ~20 characters) | Real English/Hinglish rows get dropped, or non-English rows get kept | Don't hard-drop on a single low-confidence call for short text; flag instead of dropping, per architecture.md §4.4 |
| 7.5 | Chunking splits a sentence or a cause-effect clause mid-thought | Extraction loses the "why," which is the entire point of Stage 3 | Chunk on paragraph/sentence boundaries, never mid-sentence; only chunk items that actually exceed the token threshold (rare per architecture.md §4.5) |
| 7.6 | All rows from a given run get filtered out (e.g., a source returned only off-topic content) | `normalize.py` writing a zero-row parquet must not crash Stage 3 | Handle the zero-row case explicitly; log it loudly rather than letting Stage 3 silently process nothing |
| 7.7 | A collector's row schema drifts (field added/renamed) without normalize.py being updated | Silent `KeyError` or silently-null fields | Validate incoming rows against the landing schema (architecture.md §3) at load time; fail loud on unexpected shape |
| 7.8 | `item_id` changes across re-runs if input ordering isn't stable | Breaks resumability and any external reference to an `item_id` | Derive `item_id` deterministically from `(source, source_id)`, never from row position |

## 8. Extraction (Groq LLM)

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 8.1 | Model returns JSON that doesn't conform to the schema despite JSON mode (missing field, wrong type, extra prose) | Downstream parsing crashes | Validate every response against the schema before writing; on failure, log the item as extraction-failed and continue, don't abort the batch |
| 8.2 | `representative_quote` is a paraphrase, not a verbatim substring of the source text | Violates the "must trace back to real evidence" requirement (architecture.md §5) — the whole point of quoting evidence | Verify the quote is a substring of the original `text` before accepting the extraction; reject/retry if not |
| 8.3 | `GROQ_API_KEY` missing or invalid | Script should fail immediately and clearly, not burn through a batch first | `extract.py` checks the key at startup and exits with a clear message, per implementation-plan.md Phase 3 |
| 8.4 | Groq rate limit or quota hit mid-run | Partial batch loss if not handled | Exponential backoff on 429; checkpoint progress so a re-run resumes rather than restarts from item 0 |
| 8.5 | One malformed item in a batched call (5–10 items/request) poisons the whole batch's response parsing | Losing 10 items' extraction because 1 was bad is wasteful | Parse defensively per-item within a batch response; a single item's failure shouldn't invalidate the other 9 |
| 8.6 | Very short/low-signal text (e.g., a 1-star rating with no review body) | Model may hallucinate reasons/blockers to fill the schema rather than returning empty arrays | Prompt explicitly allows/expects empty arrays and low `confidence` for low-signal input; low-confidence extractions should be visibly down-weighted in Stage 4, not treated equally to high-confidence ones |
| 8.7 | Re-running `extract.py` after adding more raw data | Should not re-spend budget on already-extracted items | Skip `item_id`s already present in `data/processed/extracted.jsonl`, matching the idempotency pattern used in Stage 1 |
| 8.8 | User's original text contains PII or toxic/offensive language | Gets propagated verbatim into `representative_quote`, which is designed to be shown publicly on the dashboard | Known limitation to flag explicitly (see §11); at minimum, a regex-based email/phone scrub before quotes are surfaced |
| 8.9 | Per-source item cap misconfigured very high in `config.yaml` | Runaway Groq spend past the "modest budget" design goal | `--dry-run` and `--limit N` flags (implementation-plan.md Phase 3) exist specifically so a cost estimate happens before a full run |

## 9. Clustering & Quantification

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 9.1 | HDBSCAN hyperparameters produce one giant cluster (under-clustering) | Opportunity areas become meaningless ("everything is one theme") | Spot-check cluster count and size distribution against a sane range before accepting a run's output, per architecture.md §11's own caveat |
| 9.2 | HDBSCAN marks most points as noise (label `-1`, over-fragmentation) | Most of the corpus silently disappears from the final output | Report the noise fraction in the run log; a high noise fraction is a signal to retune, not a silent data loss |
| 9.3 | Too few relevant items survive Stage 2/3 for embeddings+clustering to be meaningful (e.g., a source dries up) | Clustering on a tiny N produces unstable, overfit "opportunity areas" | Set a minimum-N floor below which synthesize.py warns rather than producing a misleadingly confident ranked list |
| 9.4 | Two separate clusters describe the same underlying theme with different wording (e.g., "size uncertainty" vs. "fit concerns" as separate areas) | Splits what should be one opportunity area's mention count, understating its importance | Cluster-labeling prompt should be given neighboring cluster labels for de-duplication awareness, or a manual merge pass on the labeled output |
| 9.5 | A cluster is dominated by one source because a single Reddit thread was heavily cross-posted or copy-pasted | `cross_source_validation` should catch this — but only if Stage 2/7.5's dedup already collapsed the copies; otherwise the copies inflate `mention_count` too | Dedup (§7.3) must run before clustering, not just within a source but across sources, so the count reflects independent mentions |
| 9.6 | Ranking score ties between multiple opportunity areas | Ambiguous "#1 finding" undermines the deck's key-message requirement (problemStatement.md's deck guidelines) | Deterministic tie-break (e.g., secondary sort by `pct_of_relevant_items`), documented in the output, not arbitrary dict ordering |
| 9.7 | Re-running `synthesize.py` on the same `extracted.jsonl` produces different cluster labels/counts (embedding/clustering non-determinism) | Dashboard link isn't stable across refreshes if a reviewer revisits it after a re-run | Fix random seeds where the libraries allow it; treat this as a known limitation to note in the methodology tab otherwise |
| 9.8 | `inferred_segment_signals` is multi-label per item, so `segment_breakdown` percentages don't sum to 100% | Could be misread as a bug by a reviewer looking at the cross-tab | Label the segment cross-tab explicitly as "mentions per segment," not "% of items," to avoid a false expectation of summing to 100 |
| 9.9 | Cluster-labeling Groq call produces a name too generic to be useful ("App Issues," "General Feedback") | Undermines the "state the key finding" requirement | Prompt the labeling call to require the name state a *specific* behavior/blocker, not a category; spot-check the labeled output before treating it as final (architecture.md §11) |

## 10. Frontend / Dashboard

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 10.1 | `opportunity_areas.json` is missing, empty, or malformed at build/deploy time | Page crashes for every visitor | Validate the file at build time; render an explicit "no data yet" state rather than a runtime error |
| 10.2 | A `sample_quotes[].url` is `null` (architecture.md's own example shows this — App Store reviews have no permalink) | Broken link or dead click-through if not handled | Render quote without a link affordance when `url` is null, don't emit a broken `<a href="null">` |
| 10.3 | Raw scraped user text (a quote) contains HTML/script-like content | XSS risk — this is untrusted user-generated content being rendered to arbitrary public visitors | Render all quotes/descriptions as escaped text, never `dangerouslySetInnerHTML` or equivalent |
| 10.4 | Extremely long description or quote | Breaks card/table layout | Truncate with expand-on-click; never let one row blow out the whole layout |
| 10.5 | `extracted.jsonl` is large (thousands of rows) and loaded for drill-down | Slow initial load or a frozen UI | Paginate or lazy-load drill-down evidence rather than shipping the full file to the client at once |
| 10.6 | Narrow/mobile viewport with a multi-source stacked bar or a wide segment cross-tab table | Layout breaks or becomes unreadable | Responsive layout with horizontal scroll containers for wide tables/charts, per the artifact/dataviz design constraints already in use |
| 10.7 | A filter/sort interaction produces zero matching opportunity areas | Blank screen with no explanation reads as broken | Explicit empty state, not a silently blank panel |
| 10.8 | Dashboard is redeployed without re-running the pipeline (stale data) or the pipeline is re-run without redeploying (new data not live) | Reviewer sees outdated or inconsistent findings | Methodology tab should surface the pipeline's last-run timestamp so staleness is visible, not hidden |
| 10.9 | Color palette used for source/segment breakdowns isn't colorblind-safe | Violates the deck guideline in problemStatement.md §6 ("colorblind-safe palettes") which the dashboard content doubles into | Use the `dataviz` skill's validated palette rather than ad hoc chart colors |

## 11. Cross-cutting / Operational

| # | Scenario | Why it matters | Handling |
|---|---|---|---|
| 11.1 | A real API key gets pasted into `.env.example` instead of `.env` (happened once already during this project's setup) | `.env.example` is tracked by git — `.env` is the only gitignored secrets file | Always verify secrets land in `.env`, confirm with `git check-ignore` before any commit; rotate the key if it's ever actually pushed |
| 11.2 | Pipeline stage crashes partway through a large run (e.g., extract.py dies at item 8,000 of 10,000) | Restarting from zero re-spends Groq budget already spent | Every LLM-gated stage must skip already-processed `item_id`s on re-run, not just on first run |
| 11.3 | `config.yaml` (keyword list, caps, model names) is edited between two runs of the same pipeline | Corpus from run N and run N+1 are inconsistent, but nothing records which config produced which output | `data/run_logs/` should capture the config snapshot used per run, not just token/cost counts |
| 11.4 | Scraping any of these sources may violate that platform's Terms of Service even though no paid API is used | Legal/reputational exposure beyond "budget" concerns | Explicitly out of scope for this doc to resolve, but should be flagged to the user as a known risk of the free-scraping approach, not silently assumed fine |
| 11.5 | This repo lives on Windows; JSONL files may pick up CRLF line endings from an editor | A `\r` at the end of a line can break naive `json.loads` per line | Normalize line endings on write (`\n` only) and strip trailing whitespace before parsing on read |
| 11.6 | Two Python interpreters exist on this machine's `PATH`; the first-resolved one is broken (confirmed during setup — missing stdlib) | Any contributor running a bare `python` command silently hits a different, broken interpreter | Document the working interpreter path in the README; always invoke via the project's `.venv`, never a bare `python` on `PATH` |
| 11.7 | Vercel deploy doesn't include the precomputed `opportunity_areas.json` (e.g., it's gitignored under `data/processed/*`) | Public link ships with no data | The frontend's data file needs an explicit exception from the `data/processed/*` gitignore rule, or a separate copy step into `frontend/` before deploy |
| 11.8 | `score = mention_count × source_diversity_weight` is trivially high for a large source with low diversity, or low for a genuinely important but low-volume cross-source theme | The "transparent" ranking (architecture.md §6) can still mislead if read as a single number without context | Show `mention_count`, `pct_of_relevant_items`, and source count alongside the score, not the score alone, so a reviewer can sanity-check the ranking themselves |

---

## How to use this doc

Not every row here needs a dedicated automated test — treat §6, §8, §10, and
§11 (collection integrity, extraction correctness, frontend robustness,
operational safety) as the highest-priority rows to actually cover with
tests or explicit code-level guards, since those are the ones most likely
to silently corrupt the final `opportunity_areas.json` or leak something
that shouldn't be public. §9 (clustering) is inherently harder to
unit-test and is better handled by the manual spot-check step architecture.md
§11 already calls for.

# Problem Statement — AI Discovery Engine

**Scope note:** The full assignment (linked in `problemStatement.txt`) spans 7
parts — discovery engine, metric decomposition, primary research, problem
definition, MVP, success metrics, and risks. **We are only building Part 1
right now: the AI-Powered Discovery Engine.** Everything below is scoped to
that deliverable alone.

## Product & Role
Myntra. Acting as a Product Manager on the Growth Team.

## Business Context (why this engine needs to exist)
Myntra's growth goal is to increase the percentage of users who purchase at
least one item from their wishlist within 30 days of adding it. The
underlying user problem behind low wishlist-to-purchase conversion is not
known yet — it has to be discovered from real user conversations before any
solution can be proposed. That discovery is what this engine does.

## What the Discovery Engine Must Do
Analyze public conversations about online fashion shopping at scale, and go
**beyond summarization or sentiment analysis** — it must identify, quantify
where possible, and compare opportunity areas that could plausibly move
wishlist-to-purchase conversion.

### Sources to pull from (free/public only, no paid APIs)
- Google Play Store reviews (Myntra app)
- Apple App Store reviews (Myntra app)
- Reddit (fashion, shopping, India-shopping subreddits, etc.)
- Fashion/shopping community forums
- YouTube comments (on relevant unboxing/review/haul videos)
- Public product Q&A / review text where accessible
- Other public conversations about online fashion shopping

### Questions the engine's output should help answer
- Why do users add fashion products to their wishlist in the first place?
- What prevents wishlisted products from eventually being purchased?
- What uncertainties remain after a user has already identified a product
  they like?
- What causes users to postpone a purchase?
- How do users compare multiple shortlisted products?
- What information do users seek outside Myntra before purchasing?
- What role do fit, size, styling, price, reviews, occasion, and social
  validation play?
- When is the wishlist genuine purchase intent vs. just a bookmarking habit?
- How do these behaviors differ across user segments?
- What unmet needs emerge consistently (i.e. show up across multiple
  independent sources, not one-off complaints)?

## Approach
- **Stack:** Python pipeline + Claude API.
- **Collection:** free/public scraping — e.g. `google-play-scraper` /
  `app-store-scraper` libraries for app reviews, Reddit's public JSON
  endpoints or a free PRAW app-only token, YouTube comment scraping via
  `youtube-comment-downloader` or the free YouTube Data API quota.
- **Analysis:** Claude API used to extract themes/reasons/blockers from raw
  text at scale, cluster them into opportunity areas, and quantify frequency
  (e.g. "% of wishlist-related mentions citing fit/size uncertainty") so
  opportunity areas can be compared, not just listed.
- **Output:** a report/dashboard that surfaces ranked, quantified opportunity
  areas with supporting quotes/evidence — this becomes the input to metric
  decomposition and interview targeting later (out of scope for now).

## Deliverable (for this phase)
A testable link to the discovery engine's output (report/dashboard), plus a
clear internal explanation of how the pipeline works end to end — collection
→ extraction → clustering/quantification → ranked opportunity areas.

## Explicitly Out of Scope Right Now
Metric decomposition, user interviews, problem definition, MVP build,
success metrics, risks & mitigation — all deferred until the discovery
engine has produced findings.

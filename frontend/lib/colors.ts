// Fixed source -> categorical color-slot mapping (never reassigned based on
// data order, per the dataviz skill's "color follows the entity" rule) so a
// given source reads the same color everywhere in the dashboard.

export const SOURCE_ORDER = ["play_store", "app_store", "reddit", "youtube", "forum"] as const;

export const SOURCE_LABELS: Record<string, string> = {
  play_store: "Play Store",
  app_store: "App Store",
  reddit: "Reddit",
  youtube: "YouTube",
  forum: "Forum",
};

export const SOURCE_VAR: Record<string, string> = {
  play_store: "var(--series-1)",
  app_store: "var(--series-2)",
  reddit: "var(--series-3)",
  youtube: "var(--series-4)",
  forum: "var(--series-5)",
};

// Paired text color for each series fill — these swing from dark (light
// mode) to light (dark mode), so a single hardcoded text color can't stay
// legible against them across both themes.
export const ON_SOURCE_VAR: Record<string, string> = {
  play_store: "var(--on-series-1)",
  app_store: "var(--on-series-2)",
  reddit: "var(--on-series-3)",
  youtube: "var(--on-series-4)",
  forum: "var(--on-series-5)",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function sourceColor(source: string): string {
  return SOURCE_VAR[source] ?? "var(--text-muted)";
}

export function onSourceColor(source: string): string {
  return ON_SOURCE_VAR[source] ?? "var(--page-plane)";
}

/** Sorts a set of source keys into the fixed palette order, unknowns last. */
export function orderSources(sources: string[]): string[] {
  const known = SOURCE_ORDER.filter((s) => sources.includes(s));
  const unknown = sources.filter((s) => !(SOURCE_ORDER as readonly string[]).includes(s)).sort();
  return [...known, ...unknown];
}

// Mirrors pipeline/config.yaml's decision_factors controlled vocabulary
// (architecture.md's decision-factor question list).
export const DECISION_FACTOR_ORDER = ["fit", "price", "reviews", "occasion", "styling", "social_validation"] as const;

export const DECISION_FACTOR_LABELS: Record<string, string> = {
  fit: "Fit",
  price: "Price",
  reviews: "Reviews",
  occasion: "Occasion",
  styling: "Styling",
  social_validation: "Social Validation",
};

export function decisionFactorLabel(factor: string): string {
  return DECISION_FACTOR_LABELS[factor] ?? factor;
}

/** Sorts a set of decision-factor keys into the fixed vocabulary order, unknowns last. */
export function orderDecisionFactors(factors: string[]): string[] {
  const known = DECISION_FACTOR_ORDER.filter((f) => factors.includes(f));
  const unknown = factors.filter((f) => !(DECISION_FACTOR_ORDER as readonly string[]).includes(f)).sort();
  return [...known, ...unknown];
}

// Mirrors pipeline/extract.py's VALID_JOURNEY_STAGES, ordered along the
// funnel (early browsing -> outcome) rather than alphabetically.
export const JOURNEY_STAGE_ORDER = [
  "browsing",
  "compared_alternatives",
  "saved_not_bought",
  "abandoned",
  "returned",
  "bought",
] as const;

export const JOURNEY_STAGE_LABELS: Record<string, string> = {
  browsing: "Browsing",
  compared_alternatives: "Compared Alternatives",
  saved_not_bought: "Saved, Not Bought",
  abandoned: "Abandoned",
  returned: "Returned",
  bought: "Bought",
};

export function journeyStageLabel(stage: string): string {
  return JOURNEY_STAGE_LABELS[stage] ?? stage;
}

/** Sorts a set of journey-stage keys into the funnel order, unknowns last. */
export function orderJourneyStages(stages: string[]): string[] {
  const known = JOURNEY_STAGE_ORDER.filter((s) => stages.includes(s));
  const unknown = stages.filter((s) => !(JOURNEY_STAGE_ORDER as readonly string[]).includes(s)).sort();
  return [...known, ...unknown];
}

// Mirrors pipeline/synthesize.py's exact output shape — see docs/architecture.md
// §6 and the `_write_output` / `_quantify_cluster` functions. Keep in sync with
// that file if the pipeline's schema changes.

export interface SampleQuote {
  quote: string;
  source: string;
  url: string | null;
}

export interface OpportunityArea {
  rank: number;
  opportunity_area: string;
  description: string;
  category: "behavioral" | "technical";
  mention_count: number;
  pct_of_relevant_items: number;
  source_breakdown: Record<string, number>;
  segment_breakdown: Record<string, number>;
  top_segment_signals: string[];
  decision_factor_breakdown: Record<string, number>;
  journey_stage_breakdown: Record<string, number>;
  cross_source_validation: boolean;
  score: number;
  source_diversity_weight: number;
  sample_quotes: SampleQuote[];
}

export interface Methodology {
  taxonomy_size: number;
  ranking_formula: string;
  corpus_scope: string;
}

export interface OpportunityAreasFile {
  generated_at: string;
  total_relevant_items: number;
  sources_represented: string[];
  low_sample_warning: boolean;
  note: string | null;
  methodology: Methodology;
  opportunity_areas: OpportunityArea[];
}

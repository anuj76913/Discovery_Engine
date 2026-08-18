import type { OpportunityAreasFile } from "@/lib/types";

function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function datedFilename(base: string, generatedAt: string, ext: string): string {
  const date = generatedAt.slice(0, 10); // YYYY-MM-DD
  return `${base}-${date}.${ext}`;
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

function breakdownToString(breakdown: Record<string, number>): string {
  return Object.entries(breakdown)
    .map(([k, v]) => `${k}:${v}`)
    .join("; ");
}

const CSV_COLUMNS = [
  "rank",
  "opportunity_area",
  "category",
  "description",
  "mention_count",
  "pct_of_relevant_items",
  "cross_source_validation",
  "score",
  "source_diversity_weight",
  "source_breakdown",
  "segment_breakdown",
  "decision_factor_breakdown",
  "journey_stage_breakdown",
  "sample_quotes",
] as const;

export function exportAsCsv(data: OpportunityAreasFile) {
  const rows = data.opportunity_areas.map((a) => {
    const quotes = a.sample_quotes.map((q) => `[${q.source}] "${q.quote}"`).join(" || ");
    const values: Record<(typeof CSV_COLUMNS)[number], string> = {
      rank: String(a.rank),
      opportunity_area: a.opportunity_area,
      category: a.category,
      description: a.description,
      mention_count: String(a.mention_count),
      pct_of_relevant_items: `${(a.pct_of_relevant_items * 100).toFixed(1)}%`,
      cross_source_validation: String(a.cross_source_validation),
      score: String(a.score),
      source_diversity_weight: String(a.source_diversity_weight),
      source_breakdown: breakdownToString(a.source_breakdown),
      segment_breakdown: breakdownToString(a.segment_breakdown),
      decision_factor_breakdown: breakdownToString(a.decision_factor_breakdown),
      journey_stage_breakdown: breakdownToString(a.journey_stage_breakdown),
      sample_quotes: quotes,
    };
    return CSV_COLUMNS.map((c) => csvCell(values[c])).join(",");
  });

  const csv = [CSV_COLUMNS.join(","), ...rows].join("\r\n");
  triggerDownload(csv, datedFilename("myntra-wishlist-opportunity-areas", data.generated_at, "csv"), "text/csv;charset=utf-8");
}

export function exportAsJson(data: OpportunityAreasFile) {
  triggerDownload(
    JSON.stringify(data, null, 2),
    datedFilename("myntra-wishlist-opportunity-areas", data.generated_at, "json"),
    "application/json"
  );
}

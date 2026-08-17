import { InsightsIcon } from "@/components/icons";

export default function EmptyState() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-surface-raised px-6 py-16 text-center shadow-sm">
      <InsightsIcon className="h-8 w-8 text-primary" />
      <h2 className="font-display text-xl font-bold text-text-primary">No pipeline output yet</h2>
      <p className="text-base text-text-secondary">
        This dashboard reads{" "}
        <code className="rounded bg-surface-1 px-1 py-0.5 font-mono-data text-sm">data/processed/opportunity_areas.json</code>,
        which is written by <code className="rounded bg-surface-1 px-1 py-0.5 font-mono-data text-sm">pipeline/synthesize.py</code>.
        Run the pipeline (collect → normalize → extract → synthesize) and reload this page.
      </p>
    </div>
  );
}

"use client";

import { useState } from "react";
import type { OpportunityArea } from "@/lib/types";
import RankedBarChart from "@/components/charts/RankedBarChart";
import OpportunityDetailPanel from "@/components/OpportunityDetailPanel";

interface Props {
  areas: OpportunityArea[];
}

type Metric = "mention_count" | "pct_of_relevant_items";

export default function RankedAreasView({ areas }: Props) {
  const [metric, setMetric] = useState<Metric>("mention_count");
  // Sorted by whichever metric is selected — the list (and its displayed
  // position numbers) should match what the toggle says, not the pipeline's
  // fixed score-based rank (which factors in cross-source weighting, so a
  // higher-mention area can legitimately sit below a lower-mention one
  // there). `area.rank` itself is preserved as a stable identity for
  // selection and is still shown as-is in the detail panel's "RANK #N"
  // badge, since that's a documented fact about the area, not its position
  // in this particular view.
  const byRank = [...areas].sort((a, b) => a.rank - b.rank);
  const sorted = [...areas].sort((a, b) => b[metric] - a[metric]);
  const [selectedRank, setSelectedRank] = useState<number>(byRank[0]?.rank ?? 1);
  const selected = sorted.find((a) => a.rank === selectedRank) ?? sorted[0];

  return (
    <div className="grid grid-cols-12 gap-6">
      <section className="col-span-12 flex flex-col gap-3 lg:col-span-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-2xl font-bold text-text-primary">Top Opportunity Areas</h2>
          <div className="flex shrink-0 rounded-full border border-border bg-surface-1 p-1">
            {(
              [
                ["mention_count", "Mentions"],
                ["pct_of_relevant_items", "% Relevant"],
              ] as [Metric, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setMetric(value)}
                className={`rounded-full px-3 py-1.5 text-sm font-bold transition-colors ${
                  metric === value ? "bg-primary text-on-primary" : "text-text-secondary hover:text-primary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="max-h-[720px] overflow-y-auto rounded-xl border border-border bg-surface-raised p-3 shadow-sm">
          <RankedBarChart areas={sorted} metric={metric} selectedRank={selected?.rank ?? 1} onSelect={setSelectedRank} />
        </div>
        <p className="text-center text-xs font-bold uppercase tracking-wider text-text-muted">
          {sorted.length} identified opportunity area{sorted.length === 1 ? "" : "s"}
        </p>
      </section>

      <section className="col-span-12 lg:col-span-8">
        {selected && <OpportunityDetailPanel area={selected} />}
      </section>
    </div>
  );
}

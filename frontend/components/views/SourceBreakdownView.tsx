"use client";

import { useState } from "react";
import type { OpportunityArea } from "@/lib/types";
import SourceStackedBarChart from "@/components/charts/SourceStackedBarChart";
import { orderSources, sourceColor, sourceLabel } from "@/lib/colors";

interface Props {
  areas: OpportunityArea[];
}

type Mode = "relative" | "raw";

export default function SourceBreakdownView({ areas }: Props) {
  const [mode, setMode] = useState<Mode>("relative");
  const sorted = [...areas].sort((a, b) => a.rank - b.rank);

  const totals = new Map<string, number>();
  for (const area of areas) {
    for (const [source, count] of Object.entries(area.source_breakdown)) {
      totals.set(source, (totals.get(source) ?? 0) + count);
    }
  }
  const grandTotal = [...totals.values()].reduce((a, b) => a + b, 0) || 1;
  const legendSources = orderSources([...totals.keys()]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className="col-span-12 lg:col-span-3">
        <div className="rounded-lg border border-border bg-surface-raised p-4 shadow-sm">
          <h3 className="mb-3 flex items-center justify-between text-[11px] font-bold uppercase tracking-wide text-text-secondary">
            Channel Legend
          </h3>
          <ul className="flex flex-col gap-3">
            {legendSources.map((s) => (
              <li key={s} className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2 text-text-primary">
                  <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: sourceColor(s) }} />
                  {sourceLabel(s)}
                </span>
                <span className="font-mono-data text-sm text-text-secondary">
                  {(((totals.get(s) ?? 0) / grandTotal) * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <section className="col-span-12 lg:col-span-9">
        <div className="rounded-lg border border-border bg-surface-raised p-6 shadow-sm">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl font-bold text-text-primary">Opportunity Area Source Origin</h2>
              <p className="mt-1 text-base text-text-secondary">
                Whether a theme is corroborated across independent sources, or is one source dominating.
              </p>
            </div>
            <div className="flex shrink-0 rounded-full border border-border bg-surface-1 p-1">
              {(
                [
                  ["relative", "Relative %"],
                  ["raw", "Raw Count"],
                ] as [Mode, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMode(value)}
                  className={`rounded-full px-4 py-1.5 text-sm font-bold transition-colors ${
                    mode === value ? "bg-primary text-on-primary" : "text-text-secondary hover:text-primary"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <SourceStackedBarChart areas={sorted} mode={mode} />
        </div>
      </section>
    </div>
  );
}

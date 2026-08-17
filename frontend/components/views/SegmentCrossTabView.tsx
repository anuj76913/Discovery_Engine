"use client";

import { useState } from "react";
import type { OpportunityArea } from "@/lib/types";
import { SearchIcon } from "@/components/icons";

interface Props {
  areas: OpportunityArea[];
}

const MAX_COLUMNS = 8;

// 5-step monochromatic pink scale, low -> high (dataviz skill: magnitude
// comparison within one metric -> sequential single hue, not categorical).
// Uses dedicated --heat-* tokens (see globals.css) rather than --primary-*,
// since those are re-derived per theme for text contrast and don't stay
// monotonically ordered by intensity across light/dark.
const HEAT_STEPS = [
  "bg-heat-1 text-on-heat-low",
  "bg-heat-2 text-on-heat-low",
  "bg-heat-3 text-on-heat-low",
  "bg-heat-4 text-on-heat-high",
  "bg-heat-5 text-on-heat-high",
];

function heatClass(value: number, max: number): string {
  if (value <= 0 || max <= 0) return HEAT_STEPS[0];
  const ratio = value / max;
  const step = Math.min(HEAT_STEPS.length - 1, Math.floor(ratio * (HEAT_STEPS.length - 1)) + (ratio > 0 ? 1 : 0));
  return HEAT_STEPS[Math.max(1, step)];
}

export default function SegmentCrossTabView({ areas }: Props) {
  const [filter, setFilter] = useState("");

  const globalCounts = new Map<string, number>();
  for (const area of areas) {
    for (const [signal, count] of Object.entries(area.segment_breakdown)) {
      globalCounts.set(signal, (globalCounts.get(signal) ?? 0) + count);
    }
  }
  const topSignals = [...globalCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_COLUMNS)
    .map(([signal]) => signal);
  const hasOther = globalCounts.size > topSignals.length;

  const sorted = [...areas]
    .sort((a, b) => a.rank - b.rank)
    .filter((a) => a.opportunity_area.toLowerCase().includes(filter.trim().toLowerCase()));

  const maxCell = Math.max(1, ...areas.flatMap((a) => topSignals.map((s) => a.segment_breakdown[s] ?? 0)));

  if (topSignals.length === 0) {
    return <p className="text-sm text-text-secondary">No inferred segment signals in the current data yet.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h2 className="font-display text-2xl font-bold text-text-primary">Audience Matrix</h2>
          <p className="mt-2 max-w-2xl text-base text-text-secondary">
            Cross-referencing opportunity areas against inferred user segments. Color intensity indicates mention
            density. A single item can carry multiple segment signals, so rows don&apos;t sum to the area&apos;s
            total mention count.
            {topSignals.length < globalCounts.size && ` Showing the top ${MAX_COLUMNS} signals by overall frequency.`}
          </p>
        </div>
        <div className="relative w-full md:w-72">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter opportunity areas..."
            className="w-full rounded-md border border-border bg-surface-raised py-2.5 pl-10 pr-4 text-base text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface-raised p-3 shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse text-left">
            <thead>
              <tr>
                <th className="w-[260px] border-b border-border p-3 text-xs font-bold uppercase tracking-wide text-text-secondary">
                  Opportunity Area
                </th>
                {topSignals.map((signal) => (
                  <th key={signal} className="border-b border-border p-3 text-center text-xs font-bold uppercase tracking-wide text-text-secondary">
                    {signal}
                  </th>
                ))}
                {hasOther && (
                  <th className="border-b border-border p-3 text-center text-xs font-bold uppercase tracking-wide text-text-muted">other</th>
                )}
                <th className="border-b border-border bg-page-plane p-3 text-center text-xs font-bold uppercase tracking-wide text-text-primary">
                  Segment Mentions
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((area) => {
                const shown = new Set(topSignals);
                const otherCount = Object.entries(area.segment_breakdown)
                  .filter(([s]) => !shown.has(s))
                  .reduce((sum, [, c]) => sum + c, 0);
                const rowTotal = topSignals.reduce((sum, s) => sum + (area.segment_breakdown[s] ?? 0), 0) + otherCount;

                return (
                  <tr key={area.rank} className="group hover:bg-surface-1">
                    <td className="max-w-xs truncate border-b border-gridline p-3 font-medium text-text-primary group-hover:text-primary">
                      #{area.rank} {area.opportunity_area}
                    </td>
                    {topSignals.map((signal) => {
                      const count = area.segment_breakdown[signal] ?? 0;
                      return (
                        <td key={signal} className="border-b border-gridline p-2">
                          <div className={`rounded p-2 text-center font-mono-data text-sm ${heatClass(count, maxCell)}`}>
                            {count || "—"}
                          </div>
                        </td>
                      );
                    })}
                    {hasOther && (
                      <td className="border-b border-gridline p-2 text-center font-mono-data text-sm text-text-muted">
                        {otherCount || "—"}
                      </td>
                    )}
                    <td className="border-b border-gridline bg-page-plane p-3 text-center font-mono-data text-sm font-bold text-text-primary">
                      {rowTotal || "—"}
                    </td>
                  </tr>
                );
              })}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={topSignals.length + (hasOther ? 2 : 1) + 1} className="p-6 text-center text-sm text-text-muted">
                    No opportunity areas match &ldquo;{filter}&rdquo;.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-end gap-3 border-t border-border pt-3 text-xs font-bold uppercase tracking-wide text-text-secondary">
          <span>Mention Density:</span>
          <div className="flex items-center gap-1">
            <span>Low</span>
            {HEAT_STEPS.map((cls, i) => (
              <div key={i} className={`h-4 w-4 rounded border border-border ${cls.split(" ")[0]}`} />
            ))}
            <span>High</span>
          </div>
        </div>
      </div>
    </div>
  );
}

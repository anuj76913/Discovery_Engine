import type { OpportunityArea } from "@/lib/types";
import { formatNumber } from "@/lib/format";

interface Props {
  areas: OpportunityArea[];
  metric: "mention_count" | "pct_of_relevant_items";
  selectedRank: number;
  onSelect: (rank: number) => void;
}

// Magnitude comparison across named entities -> sequential single hue
// (dataviz skill: "compare magnitude, low -> high" -> one hue). Doubles as
// navigation: each row selects that area's detail panel.
export default function RankedBarChart({ areas, metric, selectedRank, onSelect }: Props) {
  const values = areas.map((a) => a[metric]);
  const max = Math.max(...values, 0.0001);

  return (
    <div className="flex flex-col gap-1" role="list">
      {areas.map((area) => {
        const value = area[metric];
        const pct = Math.max((value / max) * 100, 3);
        const display = metric === "pct_of_relevant_items" ? `${(value * 100).toFixed(1)}%` : formatNumber(value);
        const selected = area.rank === selectedRank;

        return (
          <button
            key={area.rank}
            type="button"
            role="listitem"
            onClick={() => onSelect(area.rank)}
            aria-current={selected ? "true" : undefined}
            className={`group -mx-2 rounded-md px-2 py-2 text-left transition-colors ${
              selected ? "" : "hover:bg-surface-1"
            }`}
          >
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className={`min-w-0 flex-1 truncate text-base ${selected ? "font-bold text-text-primary" : "font-medium text-text-secondary group-hover:text-text-primary"}`}>
                {area.rank}. {area.opportunity_area}
              </span>
              <span className={`shrink-0 font-mono-data text-sm ${selected ? "font-bold text-primary" : "text-text-secondary"}`}>
                {display}
              </span>
            </div>
            <div className={`w-full overflow-hidden rounded-sm bg-gridline ${selected ? "h-2.5 border-l-2 border-primary" : "h-1.5"}`}>
              <div
                className={`h-full transition-[width] duration-300 ${selected ? "bg-primary-bright" : "bg-text-muted opacity-60"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}

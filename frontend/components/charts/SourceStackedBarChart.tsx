import type { OpportunityArea } from "@/lib/types";
import { orderSources, sourceColor, sourceLabel, onSourceColor } from "@/lib/colors";

interface Props {
  areas: OpportunityArea[];
  mode: "relative" | "raw";
}

// Part-to-whole across named sources -> categorical, fixed hue order
// (dataviz skill: "tell distinct series apart" -> categorical; "color
// follows the entity, never its rank").
export default function SourceStackedBarChart({ areas, mode }: Props) {
  const maxCount = Math.max(...areas.map((a) => a.mention_count), 1);

  return (
    <div className="flex flex-col gap-4">
      {mode === "relative" && (
        <div className="flex items-center border-b border-border pb-2 text-xs font-bold uppercase tracking-wide text-text-secondary">
          <div className="w-1/4">Opportunity Area</div>
          <div className="flex w-3/4 justify-between px-1">
            <span>0%</span>
            <span>25%</span>
            <span>50%</span>
            <span>75%</span>
            <span>100%</span>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {areas.map((area) => {
          const total = area.mention_count || 1;
          const segments = orderSources(Object.keys(area.source_breakdown)).map((s) => ({
            source: s,
            count: area.source_breakdown[s],
            pct: (area.source_breakdown[s] / total) * 100,
          }));
          // In raw mode the whole bar's width (not each segment) is scaled
          // to this area's mention_count relative to the largest area, so
          // absolute volume stays visually comparable across rows.
          const barScale = mode === "raw" ? Math.max((total / maxCount) * 100, 4) : 100;

          return (
            <div key={area.rank} className="group flex items-center">
              <div className="w-1/4 pr-4">
                <span className="block truncate text-base font-semibold text-text-primary group-hover:text-primary" title={area.opportunity_area}>
                  {area.opportunity_area}
                </span>
                <span className="font-mono-data text-sm text-text-secondary">n={area.mention_count}</span>
              </div>
              <div className="flex w-3/4">
                <div className="flex h-9 overflow-hidden rounded shadow-sm" style={{ width: `${barScale}%` }}>
                  {segments.map((seg) => (
                    <div
                      key={seg.source}
                      className="flex h-full items-center justify-center font-mono-data text-sm transition-all duration-500 ease-out"
                      style={{ width: `${seg.pct}%`, backgroundColor: sourceColor(seg.source), color: onSourceColor(seg.source) }}
                      title={`${sourceLabel(seg.source)}: ${seg.count} (${seg.pct.toFixed(0)}%)`}
                    >
                      {seg.pct > 12 ? (mode === "relative" ? `${seg.pct.toFixed(0)}%` : seg.count) : null}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

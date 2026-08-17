import type { ReactNode } from "react";
import type { OpportunityArea } from "@/lib/types";
import { sourceColor, sourceLabel, orderDecisionFactors, decisionFactorLabel, orderJourneyStages, journeyStageLabel } from "@/lib/colors";
import { QuoteIcon, ExternalLinkIcon } from "@/components/icons";
import { formatNumber } from "@/lib/format";

interface Props {
  area: OpportunityArea;
}

export default function OpportunityDetailPanel({ area }: Props) {
  const sourceCount = Object.keys(area.source_breakdown).length;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-surface-raised shadow-sm">
      <div className="border-b border-border bg-page-plane p-6">
        <div className="mb-3 flex items-center gap-3">
          <span className="rounded-md bg-primary-container px-2 py-1 text-xs font-extrabold uppercase tracking-wider text-on-primary-container">
            Rank #{area.rank}
          </span>
          <span className="text-base text-text-secondary">
            {area.cross_source_validation ? "Confirmed across multiple sources" : "Single source signal"}
          </span>
        </div>
        <h3 className="mb-3 font-display text-4xl font-bold leading-tight text-text-primary">{area.opportunity_area}</h3>
        <p className="mb-6 max-w-3xl text-base leading-relaxed text-text-secondary">{area.description}</p>

        <div className="mb-6 grid grid-cols-3 gap-3">
          <StatTile label="Mentions" value={formatNumber(area.mention_count)} accent />
          <StatTile label="% of Relevant Items" value={`${(area.pct_of_relevant_items * 100).toFixed(1)}%`} />
          <StatTile label="Sources" value={String(sourceCount)} />
        </div>

        <div className="flex flex-col gap-3">
          {area.top_segment_signals.length > 0 && (
            <TagRow label="User Segments">
              {area.top_segment_signals.map((signal) => (
                <Chip key={signal}>{signal}</Chip>
              ))}
            </TagRow>
          )}
          {Object.keys(area.decision_factor_breakdown).length > 0 && (
            <TagRow label="Decision Factors">
              {orderDecisionFactors(Object.keys(area.decision_factor_breakdown)).map((factor) => (
                <Chip key={factor} emphasis>
                  {decisionFactorLabel(factor)} · {area.decision_factor_breakdown[factor]}
                </Chip>
              ))}
            </TagRow>
          )}
          {Object.keys(area.journey_stage_breakdown).length > 0 && (
            <TagRow label="Journey Stage">
              {orderJourneyStages(Object.keys(area.journey_stage_breakdown)).map((stage) => (
                <Chip key={stage}>
                  {journeyStageLabel(stage)} · {area.journey_stage_breakdown[stage]}
                </Chip>
              ))}
            </TagRow>
          )}
        </div>
      </div>

      <div className="flex h-[420px] flex-col bg-surface-raised p-6">
        <div className="mb-4 flex items-center justify-between">
          <h4 className="flex items-center gap-2 font-display text-xl font-bold text-text-primary">
            <QuoteIcon className="h-5 w-5 text-primary" />
            Evidence
          </h4>
          <span className="text-sm text-text-muted">
            {area.sample_quotes.length > 0
              ? `${area.sample_quotes.length} sample quote${area.sample_quotes.length === 1 ? "" : "s"}`
              : "No unambiguous quotes"}
          </span>
        </div>

        {area.sample_quotes.length === 0 ? (
          <p className="text-base text-text-muted">
            No single item&apos;s quote could be unambiguously matched to this specific theme — evidence is withheld
            here rather than shown as a misleading guess.
          </p>
        ) : (
          <div className="verbatim-scroll flex flex-col gap-3 overflow-y-auto pr-1">
            {area.sample_quotes.map((q, i) => (
              <div key={i} className="rounded-lg border border-border bg-primary-soft p-4">
                <p className="mb-3 text-base italic leading-relaxed text-text-primary">&ldquo;{q.quote}&rdquo;</p>
                <div className="flex items-center gap-1.5 font-mono-data text-sm text-text-muted">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: sourceColor(q.source) }} />
                  {q.url ? (
                    <a href={q.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline hover:text-primary">
                      {sourceLabel(q.source)} <ExternalLinkIcon />
                    </a>
                  ) : (
                    <span>{sourceLabel(q.source)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatTile({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-gridline bg-surface-raised px-4 py-3">
      <div className="mb-1 text-xs font-bold uppercase tracking-wide text-text-secondary">{label}</div>
      <div className={`font-display text-3xl font-bold ${accent ? "text-primary" : "text-text-primary"}`}>{value}</div>
    </div>
  );
}

function TagRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-32 shrink-0 pt-1.5 text-xs font-bold uppercase tracking-wide text-text-muted">{label}</span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function Chip({ children, emphasis = false }: { children: ReactNode; emphasis?: boolean }) {
  return (
    <span
      className={`rounded-full border px-3 py-1.5 font-mono-data text-sm ${
        emphasis
          ? "border-primary-fixed-dim bg-primary-soft text-primary"
          : "border-border bg-surface-1 text-text-secondary"
      }`}
    >
      {children}
    </span>
  );
}

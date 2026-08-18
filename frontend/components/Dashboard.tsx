"use client";

import { useState } from "react";
import type { OpportunityAreasFile } from "@/lib/types";
import ThemeToggle from "@/components/ThemeToggle";
import ExportMenu from "@/components/ExportMenu";
import RankedAreasView from "@/components/views/RankedAreasView";
import SourceBreakdownView from "@/components/views/SourceBreakdownView";
import MethodologyView from "@/components/views/MethodologyView";
import { InsightsIcon, RankedIcon, SourceIcon, MethodologyIcon } from "@/components/icons";
import { formatDateTime } from "@/lib/format";

interface Props {
  data: OpportunityAreasFile;
}

const TABS = [
  { id: "ranked", label: "Ranked Areas", icon: RankedIcon },
  { id: "sources", label: "Source Breakdown", icon: SourceIcon },
  { id: "methodology", label: "Methodology", icon: MethodologyIcon },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Dashboard({ data }: Props) {
  const [tab, setTab] = useState<TabId>("ranked");
  const hasAreas = data.opportunity_areas.length > 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="w-full border-b border-border bg-surface-raised">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-4 px-6 pt-8 pb-4 sm:px-10">
          <div className="flex items-center gap-3">
            <InsightsIcon className="h-6 w-6 text-primary" />
            <div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-text-primary">
                Myntra Wishlist-to-Purchase Discovery Engine
              </h1>
              <p className="mt-1 text-base text-text-secondary">
                Ranked, quantified, evidence-backed opportunity areas from public conversation about Myntra.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ExportMenu data={data} />
            <ThemeToggle />
          </div>
        </div>

        <nav className="mx-auto flex max-w-[1680px] flex-wrap gap-6 overflow-x-auto px-6 sm:px-10">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center gap-2 border-b-2 py-3 text-base transition-colors ${
                  active
                    ? "border-primary font-bold text-primary"
                    : "border-transparent text-text-secondary hover:text-primary"
                }`}
              >
                <Icon />
                <span>{t.label}</span>
              </button>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1680px] flex-grow px-6 py-8 sm:px-10">
        {data.low_sample_warning && (
          <div className="mb-6 rounded-lg border border-status-warning/40 bg-status-warning/10 px-4 py-3 text-base text-text-primary">
            Small sample ({data.total_relevant_items} relevant items) — treat these rankings as illustrative, not final.
            See the Methodology tab for details.
          </div>
        )}

        {!hasAreas && tab !== "methodology" ? (
          <p className="py-12 text-center text-base text-text-secondary">
            No opportunity areas in this run yet — see the Methodology tab for run details.
          </p>
        ) : (
          <>
            {tab === "ranked" && <RankedAreasView areas={data.opportunity_areas} />}
            {tab === "sources" && <SourceBreakdownView areas={data.opportunity_areas} sourcesRepresented={data.sources_represented} />}
          </>
        )}
        {tab === "methodology" && <MethodologyView data={data} />}
      </main>

      <footer className="w-full border-t border-border bg-surface-1">
        <div className="mx-auto flex max-w-[1680px] flex-col items-center justify-between gap-2 px-6 py-4 text-sm text-text-muted sm:flex-row sm:px-10">
          <span className="font-semibold uppercase tracking-wide">Myntra Wishlist-to-Purchase Discovery Engine — research use only</span>
          <span>Data generated {formatDateTime(data.generated_at)}</span>
        </div>
      </footer>
    </div>
  );
}

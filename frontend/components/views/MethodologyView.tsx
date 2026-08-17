import type { OpportunityAreasFile } from "@/lib/types";
import { sourceLabel } from "@/lib/colors";
import { formatDateTime, formatNumber } from "@/lib/format";

interface Props {
  data: OpportunityAreasFile;
}

const STAGES = [
  {
    name: "Collect",
    detail:
      "Independent scrapers pull public conversation from Play Store, App Store, Reddit, YouTube comments, and shopping/community forums — free/public sources only, no paid APIs.",
  },
  {
    name: "Normalize",
    detail:
      "Keyword pre-filter, exact + near-duplicate dedup, language flagging, and long-text chunking turn the raw scrape into one clean corpus with a stable id per item.",
  },
  {
    name: "Extract",
    detail:
      "Each item is sent to an LLM for structured extraction — reasons for saving, blockers to purchase, journey stage, decision factors, sentiment — not just a sentiment label.",
  },
  {
    name: "Cluster & Quantify",
    detail:
      "Free-text reasons/blockers are embedded and clustered (HDBSCAN); each cluster is named by one LLM call, then quantified: mention count, source spread, segment cross-tab, and a transparent rank score.",
  },
  {
    name: "Serve",
    detail: "This dashboard reads the pipeline's precomputed output only — no live model calls are triggered by visiting this page.",
  },
];

export default function MethodologyView({ data }: Props) {
  return (
    <div className="flex flex-col gap-8 lg:flex-row">
      <aside className="w-full shrink-0 lg:w-80">
        <div className="sticky top-6 rounded-xl border border-border bg-surface-raised p-4">
          <h2 className="mb-4 text-xs font-bold uppercase tracking-widest text-text-secondary">Data Pipeline</h2>
          <div className="relative flex flex-col gap-4">
            <div className="absolute bottom-6 left-[15px] top-6 w-[2px] bg-gridline" />
            {STAGES.map((stage, i) => (
              <div key={stage.name} className="relative z-10 flex items-start gap-3">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 font-mono-data text-sm font-bold ${
                    i === 0 ? "border-primary bg-primary-soft text-primary" : "border-gridline bg-surface-1 text-text-secondary"
                  }`}
                >
                  {i + 1}
                </div>
                <div>
                  <h3 className="font-display text-base font-bold text-text-primary">{stage.name}</h3>
                  <p className="mt-0.5 text-sm leading-relaxed text-text-secondary">{stage.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      <article className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <section>
          <h2 className="mb-3 font-display text-3xl font-bold text-text-primary">Engine Methodology</h2>
          <p className="text-base leading-relaxed text-text-secondary">
            This page documents the analytical framework behind the Discovery Engine — the scope of data analyzed,
            the ranking formula, and the caveats necessary to interpret the dashboard&apos;s numbers honestly.
          </p>
        </section>

        <div className="h-px w-full bg-border" />

        <section>
          <SectionHeading>Ranking Score Formula</SectionHeading>
          <p className="mb-4 text-base leading-relaxed text-text-secondary">
            Each opportunity area is ranked by a transparent score that rewards themes corroborated across
            independent sources over themes that are just one noisy source dominating.
          </p>
          <div className="relative mb-4 overflow-hidden rounded-lg bg-[#12141c] p-4 font-mono-data text-sm text-white shadow-sm">
            <div className="absolute left-0 top-0 h-full w-1 bg-primary" />
            <div className="mb-3 text-xs uppercase tracking-wider text-white/50">Formula</div>
            <code className="block whitespace-pre-wrap leading-relaxed">
              <span className="text-primary-fixed-dim">score</span> = mention_count × source_diversity_weight
              {"\n"}
              <span className="text-white/50">{"// where:"}</span>
              {"\n"}
              source_diversity_weight = distinct_sources_in_cluster / distinct_sources_in_corpus
            </code>
          </div>
          <p className="text-base leading-relaxed text-text-secondary">
            A theme mentioned equally often but confirmed across more independent sources ranks higher than one
            confined to a single source — the ranking is inspectable, not a black box.
          </p>
        </section>

        <div className="h-px w-full bg-border" />

        <section>
          <SectionHeading>Corpus Scope</SectionHeading>
          <div className="rounded-lg border border-border bg-surface-raised p-4">
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Stat label="Generated" value={formatDateTime(data.generated_at)} />
              <Stat label="Relevant items analyzed" value={formatNumber(data.total_relevant_items)} />
              <Stat label="Sources represented" value={data.sources_represented.map(sourceLabel).join(", ") || "none yet"} />
              <Stat label="Embedding model" value={data.methodology.embedding_model} />
            </dl>
            <p className="mt-4 border-t border-gridline pt-4 text-base leading-relaxed text-text-secondary">
              {data.methodology.corpus_scope}
            </p>
          </div>
        </section>

        <section className="mb-4">
          <SectionHeading>Caveats &amp; Limitations</SectionHeading>
          <div className="rounded-r-lg border-l-4 border-primary-fixed-dim bg-page-plane p-4">
            <p className="mb-2 text-base text-text-secondary">Read these rankings with the following in mind:</p>
            <ul className="list-disc space-y-2 pl-5 text-base leading-relaxed text-text-secondary">
              <li>
                <strong className="text-text-primary">Corpus scope:</strong> restricted to items where extraction
                flagged a wishlist/save-for-later mention — not the full purchase-decision corpus that was collected
                and extracted.
              </li>
              <li>
                <strong className="text-text-primary">Source concentration:</strong> areas marked &ldquo;single
                source signal&rdquo; haven&apos;t been independently corroborated — check the Source Breakdown tab
                before treating a single-source theme as broadly representative.
              </li>
              <li>
                <strong className="text-text-primary">Clustering noise:</strong> phrases HDBSCAN couldn&apos;t
                confidently group into a theme are dropped rather than forced into a misleading cluster.
              </li>
              {data.low_sample_warning && data.note && (
                <li>
                  <strong className="text-text-primary">Small-sample run:</strong> {data.note}
                </li>
              )}
            </ul>
          </div>
        </section>
      </article>
    </div>
  );
}

function SectionHeading({ children }: { children: string }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="h-6 w-1 rounded-full bg-primary" />
      <h3 className="font-display text-xl font-bold text-text-primary">{children}</h3>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-bold uppercase tracking-wide text-text-muted">{label}</dt>
      <dd className="mt-1 text-base text-text-primary">{value}</dd>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import type { OpportunityAreasFile } from "@/lib/types";
import { exportAsCsv, exportAsJson } from "@/lib/export";
import { DownloadIcon } from "@/components/icons";

interface Props {
  data: OpportunityAreasFile;
}

export default function ExportMenu({ data }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const disabled = data.opportunity_areas.length === 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full border border-border bg-surface-1 px-4 py-2 text-sm font-bold text-text-secondary transition-colors hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        <DownloadIcon className="h-4 w-4" />
        Export
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-56 overflow-hidden rounded-lg border border-border bg-surface-raised shadow-lg">
          <button
            type="button"
            onClick={() => {
              exportAsCsv(data);
              setOpen(false);
            }}
            className="block w-full px-4 py-3 text-left text-base text-text-primary hover:bg-primary-soft"
          >
            <span className="block font-semibold">CSV (spreadsheet)</span>
            <span className="block text-sm text-text-secondary">Ranked areas table, one row per area</span>
          </button>
          <div className="h-px bg-border" />
          <button
            type="button"
            onClick={() => {
              exportAsJson(data);
              setOpen(false);
            }}
            className="block w-full px-4 py-3 text-left text-base text-text-primary hover:bg-primary-soft"
          >
            <span className="block font-semibold">JSON (full data)</span>
            <span className="block text-sm text-text-secondary">Everything the dashboard reads, unmodified</span>
          </button>
        </div>
      )}
    </div>
  );
}

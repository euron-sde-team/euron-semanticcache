"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { formatUsd } from "@/lib/format";
import type { SeriesPoint } from "@/lib/types";

/** Per-minute stacked bars: hits (served from cache) over misses (went to the provider). */
export function TrafficChart({ series, height = 176 }: { series: SeriesPoint[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(4, ...series.map((p) => p.hits + p.misses));
  const ticks = [max, Math.round(max / 2), 0];
  const hp = hover !== null ? series[hover] : undefined;
  const total = series.reduce((n, p) => n + p.hits + p.misses, 0);

  return (
    <div>
      <div className="relative flex" style={{ height }}>
        <div className="flex w-8 shrink-0 flex-col justify-between pb-0.5 pr-2 text-right font-mono text-[10px] text-subtle">
          {ticks.map((t, i) => <span key={i}>{t}</span>)}
        </div>
        <div className="relative flex-1">
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" aria-hidden>
            {ticks.map((_, i) => <div key={i} className="border-t border-dashed border-line/70" />)}
          </div>
          <div className="relative flex h-full items-end gap-[3px]" role="img" aria-label={`Requests per minute over the last ${series.length} minutes`} onMouseLeave={() => setHover(null)}>
            {series.map((p, i) => (
              <div key={p.minute} className="group flex h-full flex-1 flex-col justify-end" onMouseEnter={() => setHover(i)}>
                <div className={cn("flex flex-col-reverse overflow-hidden rounded-[3px] transition-opacity", hover !== null && hover !== i && "opacity-50")}>
                  {p.hits > 0 && <div className="bg-completed" style={{ height: `${(p.hits / max) * (height - 4)}px` }} />}
                  {p.misses > 0 && <div className="bg-waiting" style={{ height: `${(p.misses / max) * (height - 4)}px` }} />}
                </div>
              </div>
            ))}
          </div>
          {hp && hover !== null && (
            <div className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-[11px] shadow-pop" style={{ left: `${((hover + 0.5) / series.length) * 100}%` }}>
              <div className="mb-0.5 font-mono text-subtle">{new Date(hp.minute * 60_000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}</div>
              <div className="whitespace-nowrap"><Dot c="bg-completed" /> {hp.hits} from cache</div>
              <div className="whitespace-nowrap"><Dot c="bg-waiting" /> {hp.misses} to the provider</div>
              <div className="whitespace-nowrap text-completed">{formatUsd(hp.cost_saved_usd)} saved</div>
            </div>
          )}
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between pl-8 text-[11px] text-subtle">
        <span>{series.length} min ago</span>
        <span className="flex items-center gap-3">
          <span><Dot c="bg-completed" /> served from cache</span>
          <span><Dot c="bg-waiting" /> sent to the provider</span>
        </span>
        <span>{total === 0 ? "now · no traffic yet" : "now"}</span>
      </div>
    </div>
  );
}

function Dot({ c }: { c: string }) {
  return <span className={cn("mr-1 inline-block size-2 rounded-sm align-middle", c)} aria-hidden />;
}

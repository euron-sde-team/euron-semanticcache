"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock, Coins, Database, Gauge, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { TrafficChart } from "@/components/charts/traffic";
import { useApi } from "@/components/providers";
import { Button, ErrorBanner, PageHeader, ProgressBar, Skeleton } from "@/components/ui/primitives";
import { StatTile } from "@/components/ui/stat-tile";
import { formatDuration, formatNumber, formatPct, formatUsd } from "@/lib/format";
import type { Totals } from "@/lib/types";

function Breakdown({ t }: { t: Totals }) {
  const rows = [
    { label: "Exact hits", n: t.hits_exact, tone: "bg-completed" },
    { label: "Semantic hits", n: t.hits_semantic, tone: "bg-delayed" },
    { label: "Coalesced", n: t.coalesced, tone: "bg-active" },
    { label: "Misses", n: t.misses, tone: "bg-waiting" },
    { label: "Bypassed", n: t.bypass, tone: "bg-cancelled" },
  ];
  const total = Math.max(1, rows.reduce((n, r) => n + r.n, 0));
  return (
    <ul className="space-y-3" data-testid="breakdown">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="mb-1 flex justify-between text-[13px]"><span>{r.label}</span><span className="tabular-nums text-muted">{formatNumber(r.n)}</span></div>
          <ProgressBar value={(r.n / total) * 100} tone={r.tone} />
        </li>
      ))}
    </ul>
  );
}

export default function OverviewPage() {
  const api = useApi();
  const { data: o, error, refetch } = useQuery({ queryKey: ["overview", 30], queryFn: () => api.overview(30), refetchInterval: 3000 });
  const t = o?.totals;

  return (
    <>
      <PageHeader
        title="Overview"
        description="What the cache is saving you, live. Every hit is a provider call you did not pay for or wait on."
        actions={<Link href="/playground"><Button variant="primary"><Sparkles className="size-3.5" />Try it in the playground</Button></Link>}
      />
      {error && <div className="mb-4"><ErrorBanner error={error} onRetry={() => void refetch()} /></div>}

      <div className="card mb-5 overflow-hidden">
        <div className="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0 xl:grid-cols-6" data-testid="tiles">
          {!t ? (
            Array.from({ length: 6 }).map((_, i) => <div key={i} className="p-4"><Skeleton className="h-16" /></div>)
          ) : (
            <>
              <StatTile label="Saved" value={formatUsd(t.cost_saved_usd)} tone="text-completed" hint={`${formatPct(t.savings_pct)} of spend avoided`} icon={<Coins className="size-3.5" />} />
              <StatTile label="Hit rate" value={formatPct(t.hit_rate)} hint={`${formatNumber(t.hits)} of ${formatNumber(t.requests)} requests`} icon={<Gauge className="size-3.5" />} />
              <StatTile label="Tokens saved" value={formatNumber(t.tokens_saved)} hint="input + output" icon={<Sparkles className="size-3.5" />} />
              <StatTile label="Time saved" value={formatDuration(t.latency_saved_ms)} hint={`~${formatDuration(t.avg_latency_saved_ms)} per hit`} icon={<Clock className="size-3.5" />} />
              <StatTile label="Entries" value={formatNumber(t.entries)} hint={`${formatNumber(t.evictions)} evicted`} icon={<Database className="size-3.5" />} />
              <StatTile label="Look-alikes blocked" value={formatNumber(t.rejected_guard)} hint="numbers · IDs · negation" icon={<ShieldCheck className="size-3.5" />} />
            </>
          )}
        </div>
      </div>

      <div className="mb-5 grid gap-5 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[13px] font-semibold">Traffic</h2>
            <span className="text-xs text-subtle">requests per minute, last 30 min</span>
          </div>
          {o ? <TrafficChart series={o.series} /> : <Skeleton className="h-48" />}
        </div>
        <div className="card p-4">
          <h2 className="mb-4 text-[13px] font-semibold">Where requests were answered</h2>
          {t ? <Breakdown t={t} /> : <Skeleton className="h-40" />}
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-[13px] font-semibold">Namespaces</h2>
          <Link href="/namespaces" className="text-xs text-muted hover:text-fg">Manage →</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-[13px]">
            <thead><tr className="border-b border-line">{["Namespace", "Entries", "Requests", "Hit rate", "Saved", "Threshold"].map((h) => <th key={h} className="label px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {(o?.namespaces ?? []).map((n) => (
                <tr key={n.name} className="border-b border-line/60 last:border-0" data-testid="namespace-row">
                  <td className="px-4 py-3 font-medium">{n.name}{!n.config.enabled && <span className="ml-2 rounded bg-waiting/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-waiting">off</span>}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{formatNumber(n.entries)}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{formatNumber(n.requests)}</td>
                  <td className="w-48 px-4 py-3"><div className="mb-1 text-xs tabular-nums">{formatPct(n.hit_rate)}</div><ProgressBar value={n.hit_rate * 100} tone="bg-completed" /></td>
                  <td className="px-4 py-3 tabular-nums text-completed">{formatUsd(n.cost_saved_usd)}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{n.config.threshold.toFixed(2)}</td>
                </tr>
              ))}
              {o && o.namespaces.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-muted">Namespaces appear with the first request. Try the playground.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

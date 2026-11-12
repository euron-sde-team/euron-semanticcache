"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, FlaskConical, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { useApi, useToast } from "@/components/providers";
import { Button, EmptyState, Field, Input, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { MODELS, PRESETS } from "@/lib/presets";
import type { Explain, Neighbor } from "@/lib/types";

function verdict(n: Neighbor, threshold: number): { label: string; tone: string; icon: React.ReactNode } {
  if (n.would_hit) return { label: "Would hit", tone: "text-completed", icon: <Check className="size-3.5" /> };
  if (!n.in_scope) return { label: "Different scope", tone: "text-cancelled", icon: <X className="size-3.5" /> };
  if (n.guard) return { label: `Blocked: ${n.guard}`, tone: "text-waiting", icon: <ShieldAlert className="size-3.5" /> };
  return { label: n.similarity < threshold ? "Below threshold" : "No match", tone: "text-muted", icon: <X className="size-3.5" /> };
}

export default function LabPage() {
  const api = useApi();
  const toast = useToast();
  const [namespace, setNamespace] = useState("playground");
  const [model, setModel] = useState(MODELS[0]!);
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState("How do I reset my password?");
  const [result, setResult] = useState<Explain | null>(null);

  const run = useMutation({
    mutationFn: async () => {
      const messages = [...(system.trim() ? [{ role: "system", content: system.trim() }] : []), { role: "user", content: prompt }];
      return api.explain({ model, messages }, namespace);
    },
    onSuccess: setResult,
    onError: (e) => toast("error", e.message),
  });

  return (
    <>
      <PageHeader title="Similarity lab" description="Tune your threshold with evidence: see the nearest cached prompts for any question, how close each is, and exactly why it would or would not be served." />
      <form className="card mb-5 space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); run.mutate(); }} aria-label="Analyze">
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => <button type="button" key={p.label} onClick={() => setPrompt(p.prompt)} className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:border-subtle/60 hover:text-fg">{p.label}</button>)}
        </div>
        <Field label="Prompt"><Textarea rows={2} value={prompt} onChange={(e) => setPrompt(e.target.value)} name="prompt" className="!font-sans !text-[13px]" /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Namespace"><Input value={namespace} onChange={(e) => setNamespace(e.target.value)} name="namespace" required /></Field>
          <Field label="Model"><Select value={model} onChange={(e) => setModel(e.target.value)}>{MODELS.map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="System prompt"><Input value={system} onChange={(e) => setSystem(e.target.value)} placeholder="(none)" /></Field>
        </div>
        <div className="flex justify-end"><Button type="submit" variant="primary" loading={run.isPending} disabled={!prompt.trim()}><FlaskConical className="size-3.5" />Analyze</Button></div>
      </form>

      {!result ? (
        <div className="card"><EmptyState icon={<FlaskConical className="size-5" />} title="Nothing analysed yet" hint="Fill the cache from the Playground, then analyse a question here to see its nearest neighbours." /></div>
      ) : (
        <div className="card" data-testid="neighbors">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3 text-[13px]">
            <h2 className="font-semibold">Nearest cached prompts</h2>
            <span className="text-muted">threshold <b className="tabular-nums text-fg">{result.threshold.toFixed(2)}</b> · guards {result.guards ? "on" : "off"}</span>
          </div>
          {result.neighbors.length === 0 ? <EmptyState icon={<FlaskConical className="size-5" />} title="The namespace is empty" hint="Nothing is cached here yet." /> : (
            <ul className="divide-y divide-line/60">
              {result.neighbors.map((n) => {
                const v = verdict(n, result.threshold);
                return (
                  <li key={n.id} className="px-4 py-3" data-testid="neighbor" data-hit={n.would_hit}>
                    <div className="mb-2 flex items-start justify-between gap-3">
                      <span className="min-w-0 break-words text-[13px]">{n.prompt}</span>
                      <span className={cn("inline-flex shrink-0 items-center gap-1 text-xs font-medium", v.tone)}>{v.icon}{v.label}</span>
                    </div>
                    <div className="relative h-2 rounded-full bg-raised">
                      <div className={cn("h-full rounded-full", n.would_hit ? "bg-completed" : n.in_scope ? "bg-waiting" : "bg-cancelled")} style={{ width: `${Math.max(1, n.similarity * 100)}%` }} />
                      <div className="absolute -top-1 h-4 w-0.5 rounded bg-fg/70" style={{ left: `${result.threshold * 100}%` }} title={`threshold ${result.threshold}`} />
                    </div>
                    <div className="mt-1 text-right font-mono text-[11px] tabular-nums text-subtle">{n.similarity.toFixed(3)}</div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </>
  );
}

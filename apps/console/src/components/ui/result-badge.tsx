import { cn } from "@/lib/cn";
import type { ChatResult } from "@/lib/types";

const STYLE: Record<ChatResult["result"], { dot: string; text: string; bg: string }> = {
  HIT: { dot: "bg-completed", text: "text-completed", bg: "bg-completed/12" },
  COALESCED: { dot: "bg-completed", text: "text-completed", bg: "bg-completed/12" },
  MISS: { dot: "bg-waiting", text: "text-waiting", bg: "bg-waiting/12" },
  BYPASS: { dot: "bg-cancelled", text: "text-cancelled", bg: "bg-cancelled/15" },
  ERROR: { dot: "bg-failed", text: "text-failed", bg: "bg-failed/12" },
};

/** HIT / MISS / BYPASS with the match type: "HIT · semantic". */
export function ResultBadge({ result, type, className }: { result: ChatResult["result"]; type?: string | null; className?: string }) {
  const s = STYLE[result];
  return (
    <span data-result={result} className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold tracking-wide", s.bg, s.text, className)}>
      <span className={cn("size-1.5 rounded-full", s.dot)} aria-hidden />
      {result}
      {type ? <span className="font-normal opacity-80">· {type}</span> : null}
    </span>
  );
}

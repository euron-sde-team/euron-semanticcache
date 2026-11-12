"use client";

import { useQuery } from "@tanstack/react-query";
import { Database, FlaskConical, Gauge, Layers, LogOut, Moon, PlayCircle, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useTheme } from "@/hooks/use-theme";
import { cn } from "@/lib/cn";
import { formatUsd } from "@/lib/format";
import { ConnectScreen } from "./connect-screen";
import { Logo } from "./logo";
import { useApi, useConnection } from "./providers";
import { Spinner } from "./ui/primitives";

const NAV = [
  { group: "Insight", items: [
    { href: "/", label: "Overview", icon: Gauge },
    { href: "/playground", label: "Playground", icon: PlayCircle },
    { href: "/lab", label: "Similarity lab", icon: FlaskConical },
  ] },
  { group: "Cache", items: [
    { href: "/entries", label: "Entries", icon: Database },
    { href: "/namespaces", label: "Namespaces", icon: Layers },
  ] },
  { group: "Admin", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
];

function isActive(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href);
}

function Sidebar() {
  const path = usePathname();
  const api = useApi();
  const { data } = useQuery({ queryKey: ["overview", 30], queryFn: () => api.overview(30), refetchInterval: 4000 });
  const saved = data?.totals.cost_saved_usd ?? 0;
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface md:flex">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <Logo />
        <div className="leading-tight">
          <div className="text-[13px] font-semibold">Euron SemanticCache</div>
          <div className="text-[11px] text-subtle">AI response cache</div>
        </div>
      </div>
      <div className="mx-3 mb-2 rounded-lg border border-completed/25 bg-completed/10 px-3 py-2" data-testid="sidebar-saved">
        <div className="label !text-completed/80">Saved so far</div>
        <div className="mt-0.5 text-lg font-semibold tabular-nums text-completed">{formatUsd(saved)}</div>
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-2.5 py-2" aria-label="Main">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="label px-2.5 pb-1.5">{g.group}</div>
            <ul className="space-y-0.5">
              {g.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(path, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition",
                        active ? "bg-raised font-medium text-fg" : "text-muted hover:bg-raised/60 hover:text-fg",
                      )}
                    >
                      <Icon className="size-4" aria-hidden />
                      <span className="flex-1">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <ConnectionFooter />
    </aside>
  );
}

function ConnectionFooter() {
  const { conn, disconnect } = useConnection();
  const { theme, toggle } = useTheme();
  const api = useApi();
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.namespaces(), refetchInterval: 8000, retry: false });
  const online = !health.isError;
  return (
    <div className="flex items-center gap-2 border-t border-line p-3">
      <div className="min-w-0 flex-1">
        <span className="inline-flex items-center gap-1.5 text-xs" data-online={online}>
          <span className={cn("size-2 rounded-full", online ? "animate-pulseDot bg-completed" : "bg-failed")} aria-hidden />
          <span className={online ? "text-fg" : "text-failed"}>{online ? "Connected" : "Unreachable"}</span>
        </span>
        <div className="mt-0.5 truncate font-mono text-[11px] text-subtle" title={conn?.apiUrl}>{conn?.apiUrl.replace(/^https?:\/\//, "")}</div>
      </div>
      <button onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-fg">
        {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>
      <button onClick={disconnect} aria-label="Disconnect" className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-fg">
        <LogOut className="size-4" />
      </button>
    </div>
  );
}

function MobileBar() {
  const path = usePathname();
  return (
    <nav aria-label="Main (mobile)" className="sticky top-0 z-30 flex gap-1 overflow-x-auto border-b border-line bg-surface/95 px-3 py-2 backdrop-blur md:hidden">
      {NAV.flatMap((g) => g.items).map(({ href, label }) => (
        <Link key={href} href={href} className={cn("whitespace-nowrap rounded-lg px-3 py-1.5 text-[13px]", isActive(path, href) ? "bg-raised font-medium" : "text-muted")}>
          {label}
        </Link>
      ))}
    </nav>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { ready, conn } = useConnection();
  if (!ready) return <div className="flex min-h-screen items-center justify-center"><Spinner className="size-6" /></div>;
  if (!conn) return <ConnectScreen />;
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <MobileBar />
        <main className="mx-auto max-w-[1280px] px-5 py-7 md:px-8">{children}</main>
      </div>
    </div>
  );
}

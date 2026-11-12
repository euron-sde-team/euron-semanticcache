import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrafficChart } from "@/components/charts/traffic";
import { ResultBadge } from "@/components/ui/result-badge";
import { StatTile } from "@/components/ui/stat-tile";
import type { SeriesPoint } from "@/lib/types";

describe("ResultBadge", () => {
  it.each(["HIT", "MISS", "BYPASS", "COALESCED", "ERROR"] as const)("renders %s", (r) => {
    render(<ResultBadge result={r} />);
    expect(screen.getByText(r)).toBeInTheDocument();
  });
  it("shows the match type", () => {
    render(<ResultBadge result="HIT" type="semantic" />);
    expect(screen.getByText(/semantic/)).toBeInTheDocument();
    expect(document.querySelector("[data-result=HIT]")).not.toBeNull();
  });
});

describe("StatTile", () => {
  it("shows label, value and hint", () => {
    render(<StatTile label="Hit rate" value="60%" hint="3 of 5 requests" />);
    expect(screen.getByTestId("stat-hit-rate")).toHaveTextContent("Hit rate60%3 of 5 requests");
  });
});

describe("TrafficChart", () => {
  const series: SeriesPoint[] = Array.from({ length: 30 }, (_, i) => ({ minute: 29_000_000 + i, hits: i % 5, misses: i % 3 === 0 ? 2 : 0, cost_saved_usd: (i % 5) * 0.0004, tokens_saved: 0 }));
  it("renders an accessible chart", () => {
    render(<TrafficChart series={series} />);
    expect(screen.getByRole("img", { name: /last 30 minutes/ })).toBeInTheDocument();
  });
  it("shows what a minute saved on hover", () => {
    const { container } = render(<TrafficChart series={series} />);
    fireEvent.mouseEnter(container.querySelectorAll(".group")[4]!);
    expect(screen.getByText(/\d+ from cache/)).toBeInTheDocument();
    expect(screen.getByText(/saved/, { selector: "div.text-completed" })).toBeInTheDocument();
  });
  it("says so when there is no traffic", () => {
    render(<TrafficChart series={series.map((p) => ({ ...p, hits: 0, misses: 0 }))} />);
    expect(screen.getByText(/no traffic yet/)).toBeInTheDocument();
  });
});

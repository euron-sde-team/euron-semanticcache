import { describe, expect, it } from "vitest";
import { formatDuration, formatNumber, formatPct, formatTtl, formatUsd, relativeTime } from "@/lib/format";

describe("formatUsd", () => {
  it.each([
    [null, "-"], [0, "$0.00"], [0.0042, "$0.0042"], [0.000045, "<$0.0001"], [-0.00001, "-<$0.0001"], [0.0001, "$0.0001"], [0.5, "$0.50"], [12.345, "$12.35"], [1840, "$1.8k"],
  ])("formats %s as %s", (input, expected) => expect(formatUsd(input as number | null)).toBe(expected));
});

describe("formatPct", () => {
  it("renders ratios as percentages", () => {
    expect(formatPct(0.6)).toBe("60%");
    expect(formatPct(0.8567, 1)).toBe("85.7%");
    expect(formatPct(null)).toBe("-");
    expect(formatPct(Number.NaN)).toBe("-");
  });
});

describe("formatTtl", () => {
  it.each([[30, "30s"], [90, "90s"], [120, "2m"], [3600, "1h"], [21_600, "6h"], [86_400, "1d"], [604_800, "7d"]])("%s -> %s", (s, e) => expect(formatTtl(s)).toBe(e));
});

describe("formatDuration", () => {
  it("formats milliseconds up to days", () => {
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(1500)).toBe("1.5 s");
    expect(formatDuration(75_000)).toBe("1m 15s");
    expect(formatDuration(null)).toBe("-");
  });
});

describe("relativeTime / formatNumber", () => {
  it("handles past, future and abbreviation", () => {
    expect(relativeTime(1_000_000 - 5000, 1_000_000)).toBe("5.0 s ago");
    expect(relativeTime(1_000_000 + 120_000, 1_000_000)).toBe("in 2m 0s");
    expect(formatNumber(25_400)).toBe("25.4k");
    expect(formatNumber(3_200_000)).toBe("3.2M");
  });
});

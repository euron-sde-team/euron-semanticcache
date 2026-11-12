import { beforeEach, describe, expect, it } from "vitest";
import { clearConnection, loadConnection, normalizeApiUrl, saveConnection } from "@/lib/connection";

describe("connection storage", () => {
  beforeEach(() => window.localStorage.clear());
  it("round-trips and clears", () => {
    expect(loadConnection()).toBeNull();
    saveConnection({ apiUrl: "http://x:1", apiKey: "sc_a_b" });
    expect(loadConnection()).toEqual({ apiUrl: "http://x:1", apiKey: "sc_a_b" });
    clearConnection();
    expect(loadConnection()).toBeNull();
  });
  it("ignores corrupt or key-less entries", () => {
    window.localStorage.setItem("semanticcache.connection", "{nope");
    expect(loadConnection()).toBeNull();
    window.localStorage.setItem("semanticcache.connection", JSON.stringify({ apiUrl: "http://x", apiKey: "" }));
    expect(loadConnection()).toBeNull();
  });
  it("normalizes the URL", () => expect(normalizeApiUrl(" http://x:8180/// ")).toBe("http://x:8180"));
});

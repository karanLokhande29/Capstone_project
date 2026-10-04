import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// jsdom lacks these browser APIs used by React Flow, Radix and Recharts.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver ??= RO;
if (typeof window !== "undefined") {
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false })) as never;
  window.scrollTo = (() => {}) as never;
  Element.prototype.scrollIntoView ??= function scrollIntoView() {};
  (window as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly ??= class { m22 = 1; constructor() {} };
}

// The demo pages fetch per-route JSON shards from /data/*.json (public/data on disk). Tests serve them from the
// filesystem; /api/* is offline unless a test installs its own fetch.
const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
  if (path.startsWith("/data/")) {
    try {
      const body = readFileSync(resolve(process.cwd(), "public", path.slice(1).split("?")[0]), "utf-8");
      return new Response(body, { status: 200, headers: { "content-type": "application/json" } });
    } catch {
      return new Response("not found", { status: 404 });
    }
  }
  if (path.startsWith("/api/")) return new Response(JSON.stringify({ message: "offline in tests" }), { status: 503 });
  return realFetch ? realFetch(input, init) : new Response("", { status: 404 });
}) as typeof fetch;

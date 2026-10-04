import "@testing-library/jest-dom/vitest";

// jsdom lacks these browser APIs used by React Flow, Radix and Recharts.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver ??= RO;
if (typeof window !== "undefined") {
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false })) as never;
  window.scrollTo = (() => {}) as never;
  (window as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly ??= class { m22 = 1; constructor() {} };
}

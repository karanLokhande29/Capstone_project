import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { readJson } from "@/test/files";
import type { ConfidenceModel, Snapshot } from "@/domain/types";
import { useData } from "@/data/store";
import { routes } from "@/App";

const s = readJson<Snapshot>("src/data/snapshot.json");
const model = readJson<ConfidenceModel>("src/data/confidence_model_v1.json");

const CASES: [string, RegExp][] = [
  ["/", /Is it really the same rule|Can AI tell|Compliance teams compare/], ["/findings", /Six things we learned/], ["/demo", /Compare your institution/],
  ["/how-it-works", /How the benchmark was built/], ["/trust", /How we keep the results honest/],
  ["/workspace", /Seven headline findings/], ["/rq/RQ2", /Research Question Explorer/], ["/results/t1", /Results Lab/], ["/results/paired", /Pre-registered only/],
  ["/results/t3", /circular/i], ["/results/t4", /RePASs/], ["/different?def=A", /Failure Explorer/], ["/construction", /Benchmark Construction/],
  ["/reliability", /Gold is single-expert/], ["/atlas", /Corpus Atlas/], ["/architecture", /System Architecture Map/], ["/claims", /Pre-submission gate/],
  ["/gaps", /Gap Analysis/], ["/provenance", /Freeze Ledger/], ["/diff", /Snapshot diff/], ["/readiness", /Submission Readiness/], ["/next", /build next/i],
  ["/review-queue", /Human-review queue/], ["/workbench", /Annotation workbench/], ["/tour/1", /Chain 1/], ["/product", /compliance intelligence/],
  ["/explorer", /Obligation Explorer/], ["/assistant?q=comparator-vs-class-aware", /comparator − class-aware/],
];

describe("pitch pages tell the truth about the results", () => {
  beforeAll(() => useData.getState().setLoaded(s, model, "repo"));
  it("results page explains the date finding with the after-change numbers, not the misleading 48/52", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/findings"] });
    render(<RouterProvider router={router} />);
    await screen.findAllByText(/Six things we learned/);
    expect(document.body.textContent).toMatch(/23 of 26 already-changed rules/);
    expect(document.body.textContent).not.toMatch(/48 of 52 amended/);
    expect(document.body.textContent).toMatch(/38 of 78 real differences/);
  });
  it("public pages never show internal pipeline ids", async () => {
    for (const path of ["/", "/findings", "/demo", "/how-it-works", "/trust"]) {
      const router = createMemoryRouter(routes, { initialEntries: [path] });
      const { unmount } = render(<RouterProvider router={router} />);
      await screen.findAllByRole("heading", { level: 1 });
      expect(document.body.textContent).not.toMatch(/P2-00\d|P3-00\d|P4-001|ablation_a|class_blind|t2_xclass|RePASs composite/);
      unmount();
    }
  });
});

describe("every §7 screen renders from the real snapshot", () => {
  beforeAll(() => useData.getState().setLoaded(s, model, "repo"));
  it.each(CASES)("%s", async (path, text) => {
    const router = createMemoryRouter(routes, { initialEntries: [path] });
    render(<RouterProvider router={router} />);
    expect((await screen.findAllByText(text, {}, { timeout: 4000 })).length).toBeGreaterThan(0);
  });
  it("the T3 circular 1.000 never appears without its caveat on the Showcase (R3)", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/product"] });
    render(<RouterProvider router={router} />);
    await screen.findAllByText(/compliance intelligence/);
    expect(document.body.textContent).not.toMatch(/1\.000/);
    expect(document.body.textContent).toMatch(/circular by construction and is not shown/);
  });
  it("every T2 +0.451 appears with the by-construction caveat", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/results/t2"] });
    render(<RouterProvider router={router} />);
    await screen.findAllByText(/t2_xclass_t1/);
    expect(document.body.textContent).toMatch(/partly by construction/);
  });
});

describe("FixtureAdapter", () => {
  it("renders the fixture home with a watermark flag and blocks other screens", async () => {
    const { FixtureAdapter } = await import("@/data/repository");
    const { snapshot } = await new FixtureAdapter().load();
    useData.getState().setLoaded(snapshot, null, "fixture");
    const router = createMemoryRouter(routes, { initialEntries: ["/workspace"] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByText(/synthetic fixture/i, { selector: "h1" })).toBeInTheDocument();
    expect(snapshot.meta.fixture).toBe(true);
    useData.getState().setLoaded(s, model, "repo");
  });
});

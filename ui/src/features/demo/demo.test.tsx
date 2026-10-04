import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routes } from "@/App";
import { TooltipProvider } from "@/components/ui/primitives";
import { readSse, type CompareEvent } from "./api";
import { diffWithSealed } from "./lab/live";
import { Round, score } from "./play/Round";
import { cellOf } from "./cases/FailureMap";
import type { CasesIndex, Home, Judgement, Shard } from "./types";

const data = <T,>(rel: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data", rel), "utf8")) as T;
const home = data<Home>("home.json");
const index = data<CasesIndex>("cases/index.json");
const go = (path: string) => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
const hero = encodeURIComponent(home.hero.id);

const PAGES: [string, RegExp][] = [
  ["/", /These two rules look the same/], ["/cases", /412 expert-labelled comparisons/], ["/cases/failures", /Where do the models fail/],
  ["/cases/play", /Can you spot the difference/], ["/cases/atlas", /Which institution types have a Direction/], [`/case/${hero}`, /field by field/],
  ["/lab", /Run the frozen comparator yourself/], ["/lab/paste", /Do not paste confidential or internal text/], ["/lab/edit", /control-run gate/],
  ["/triage", /How much could a team let the system handle/], ["/results", /Six results, explained/], ["/method", /Two lanes, evaluated separately/],
  ["/present", /Presenter preflight/],
];

describe("every demo route renders from the public data shards", () => {
  it.each(PAGES)("%s", async (path, text) => {
    go(path);
    expect((await screen.findAllByText(text, {}, { timeout: 5000 })).length).toBeGreaterThan(0);
  });
  it("old pitch URLs redirect to their new homes", () => {
    const children = (routes[0] as { children: { path?: string; element?: { props?: { to?: string } } }[] }).children;
    const to = (p: string) => children.find((c) => c.path === p)?.element?.props?.to;
    expect([to("findings"), to("how-it-works"), to("trust"), to("demo")]).toEqual(["/results", "/method", "/method#limits", "/cases"]);
  });
});

describe("honesty invariants on the rendered pages", () => {
  it("results: date finding uses the after-change numbers; system names follow B2; Result 5 explains our first pipeline", async () => {
    go("/results");
    await screen.findAllByText(/Six results, explained/, {}, { timeout: 5000 });
    const t = document.body.textContent ?? "";
    expect(t).toMatch(/23 of 26 already-changed rules/);
    expect(t).not.toMatch(/48 of 52 amended/);
    expect(t).toMatch(/38 of 78 real differences/);
    expect(t).toMatch(/This was the system we originally built\. It scored lowest on differences, which is why we designed the structured comparator\./);
    expect(t).not.toMatch(/(?<!Our first pipeline \(institution filter \+ )automatic fact-checker/i);
    expect(t).not.toMatch(/ablation_a|class_blind|t2_xclass/);
  });
  it("a comparator DIFFERENT verdict shows 'Flagged for review', never a band badge", async () => {
    go(`/case/${hero}`);
    expect(await screen.findByText("Flagged for review", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(await screen.findByText(/expert agreed 35% of the time \(38 of 108\).*caught 49% of all real differences \(38 of 78\)/)).toBeInTheDocument();
    expect(screen.queryByText(/^Low confidence$/)).toBeNull();
  });
  it("triage at the frozen High boundary shows 162 units, 156 correct, and never says recommended/optimal/safe", async () => {
    go("/triage");
    expect(await screen.findByText(/156 of 162 correct/, {}, { timeout: 5000 })).toBeInTheDocument();
    const t = (document.body.textContent ?? "").replace("not a recommended threshold", "");
    expect(t).not.toMatch(/\b(recommended|optimal|safe)\b/i);
  });
  it("Method & Trust labels the sensitivity analysis next to its numbers", async () => {
    go("/method");
    const label = await screen.findByText(/Post-paper sensitivity analysis — frozen benchmark result unchanged\./, {}, { timeout: 5000 });
    const block = label.closest("section")!;
    expect(within(block).getByText(/37 of 38 remain/)).toBeInTheDocument();
    expect(within(block).getByText(/62 of 70 remain/)).toBeInTheDocument();
  });
});

describe("Failure Map", () => {
  it("per-column error counts match the published retrieval-vs-reasoning table", () => {
    const diff = index.units.filter((u) => u.gold === "different");
    expect(diff).toHaveLength(78);
    const errors = (s: Parameters<typeof cellOf>[1]) => diff.filter((u) => ["reasoning", "retrieval", "abstained"].includes(cellOf(u, s))).length;
    expect([errors("class_blind"), errors("class_aware"), errors("final_agentic"), errors("ablation_a"), errors("long_context"), errors("comparator")]).toEqual([60, 71, 76, 70, 73, 40]);
    const retr = (s: Parameters<typeof cellOf>[1]) => diff.filter((u) => cellOf(u, s) === "retrieval").length;
    expect(retr("class_aware")).toBe(12);
    expect(diff.filter((u) => u.missedA).length).toBe(56);
    expect(diff.filter((u) => u.missedA && u.sys.comparator === "different").length).toBe(26);
  });
});

describe("Spot the difference", () => {
  const shard = data<Shard>(`cases/${home.hero.itemId.replace("::", "__")}.json`);
  it("no label leaks into the DOM before the guess", () => {
    const api = { status: "offline" as const, health: null };
    render(<TooltipProvider><Round unit={home.hero} pointers={shard.pointers} api={api} /></TooltipProvider>);
    const t = document.body.textContent ?? "";
    expect(t).not.toMatch(/Expert|Structured comparator|Standard search|Open in Microscope|What the comparator saw/);
    expect(document.body.innerHTML).not.toMatch(/goldJudgement|data-gold/);
  });
  it("scores only rounds played; best single AI system is the best of the five LLMs over the same rounds", () => {
    const units = index.units.filter((u) => u.missedA).slice(0, 5).map((u) => data<Shard>(`cases/${u.shard}.json`).units.find((x) => x.id === u.id)!);
    const guesses: Judgement[] = ["different", "same", "different", "none", "different"];
    const s = score(units.map((unit, i) => ({ unit, guess: guesses[i] })));
    expect(s.n).toBe(5);
    expect(s.you).toBe(guesses.filter((g, i) => g === units[i].goldJudgement).length);
    expect(s.best).toBe(0); // curated rounds: every LLM system missed each of them
    expect(s.cmp).toBe(units.filter((u) => u.predictions.comparator.judgement === u.goldJudgement).length);
  });
});

describe("live comparator client (mocked stream)", () => {
  it("parses SSE events and flags Live ≠ sealed only when a field or the verdict differs", async () => {
    const unit = home.hero;
    const rows = unit.comparator.rows.map((r) => ({ field: r.field, status: r.status }));
    const events = [
      { type: "status", data: { message: "receiving structured output", streaming: "incremental" } },
      { type: "field", data: { path: "candidates.0.field_comparison.frequency", candidate: unit.comparator.decisivePid, field: "frequency", kind: "comparison", value: "differs" } },
      { type: "verdict", data: { judgement: "different", matchedPid: unit.predictions.comparator.matchedPid, trace: [], rows, perCandidate: [] } },
    ];
    const text = events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
    const enc = new TextEncoder().encode(text);
    const stream = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc.slice(0, 50)); c.enqueue(enc.slice(50)); c.close(); } });
    const got: CompareEvent[] = [];
    await readSse(stream, (e) => got.push(e));
    expect(got.map((e) => e.type)).toEqual(["status", "field", "verdict"]);
    const v = got[2].data as Parameters<typeof diffWithSealed>[1];
    expect(diffWithSealed(unit, v)?.same).toBe(true);
    const changed = { ...v!, rows: rows.map((r) => (r.field === "frequency" ? { ...r, status: "equal" as const } : r)) };
    const d = diffWithSealed(unit, changed)!;
    expect(d.same).toBe(false);
    expect(d.rows.map((r) => r.field)).toEqual(["frequency"]);
  });
});

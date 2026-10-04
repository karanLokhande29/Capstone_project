// eslint-disable-next-line @typescript-eslint/no-explicit-any
type J = Record<string, any>;
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { createApp, chunksOf } from "./app";
import { MockLlm } from "./llm";
import { Cache, Quota } from "./store";
import { postCheck, numberSet, bm25Top } from "./grounding";
import type { Bridge } from "./bridge";

const UI = process.cwd();
const scratch = () => mkdtempSync(join(UI, "server/.cache/test-"));
const paths = { snapshotPath: join(UI, "src/data/snapshot.json"), modelPath: join(UI, "src/data/confidence_model_v1.json") };
const post = (app: ReturnType<typeof createApp>, url: string, body: unknown) =>
  app.request(url, { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json" } });

function makeApp(llm: MockLlm | null, cap = 50, bridge: Bridge | null = null) {
  const dir = scratch();
  return { app: createApp({ llm, bridge, quota: new Quota(join(dir, "state"), cap), cache: new Cache(join(dir, "cache")), ...paths }), dir };
}

describe("assistant proxy (mocked LLM, no network)", () => {
  it("is off without an ASSISTANT key", async () => {
    const { app, dir } = makeApp(null);
    const r = await post(app, "/api/assistant", { question: "Why does the verifier hurt T1?" });
    expect(r.status).toBe(200);
    expect(((await r.json()) as J).state).toBe("off");
    rmSync(dir, { recursive: true });
  });

  it("returns an Exact answer when every sentence is cited and every number matches", async () => {
    const llm = new MockLlm((m) => {
      const cite = m[1].content.match(/\[(phase4\.t1_paired[^\]]+)\]/)?.[1] ?? "MD §10";
      return `The verifier lowers 3-way flag F1 by -0.068 on T1 [${cite}].`;
    });
    const { app, dir } = makeApp(llm);
    const r = await post(app, "/api/assistant", { question: "Ablation C verifier final agentic class-aware flag F1" });
    const j = (await r.json()) as J;
    expect(j.state).toBe("ok");
    expect(j.grounding).toBe("Exact");
    expect(llm.calls).toHaveLength(1);
    rmSync(dir, { recursive: true });
  });

  it("blocks an answer whose number is not in the snapshot (R6)", async () => {
    const llm = new MockLlm(() => "The verifier hurts T1 by 0.4242 [MD §10].");
    const { app, dir } = makeApp(llm);
    const j = (await (await post(app, "/api/assistant", { question: "Discussion verifier hurts T1" })).json()) as J;
    expect(j.state).toBe("blocked");
    expect(j.answer).toBeNull();
    expect(j.reason).toMatch(/R6/);
    rmSync(dir, { recursive: true });
  });

  it("refuses rather than guesses", async () => {
    const llm = new MockLlm(() => "Not in the project record.");
    const { app, dir } = makeApp(llm);
    const j = (await (await post(app, "/api/assistant", { question: "What is the verifier's coverage on T1?" })).json()) as J;
    expect(j.grounding).toBe("Unsupported");
    rmSync(dir, { recursive: true });
  });

  it("caches by prompt hash and enforces the daily cap", async () => {
    const llm = new MockLlm(() => "Not in the project record.");
    const { app, dir } = makeApp(llm, 1);
    await post(app, "/api/assistant", { question: "verifier coverage" });
    const again = (await (await post(app, "/api/assistant", { question: "verifier coverage" })).json()) as J;
    expect(llm.calls).toHaveLength(1);
    expect(again.quota.used).toBe(1);
    const third = await post(app, "/api/assistant", { question: "different failure reasoning" });
    expect(third.status).toBe(200);
    expect(((await third.json()) as J).state).toBe("quota");
    rmSync(dir, { recursive: true });
  });
});

describe("grounding helpers", () => {
  it("BM25 finds the verifier finding", () => {
    const chunks = chunksOf(JSON.parse(readFileSync(paths.snapshotPath, "utf8")));
    expect(bm25Top(chunks, "verifier hurts T1").map((c) => c.id).join(" ")).toMatch(/F4|Ablation C|verifier/i);
  });
  it("postCheck flags uncited sentences as Partial", () => {
    const chunks = [{ id: "a", cite: "MD §10", text: "x" }];
    const pc = postCheck("Long-context is competitive [MD §10]. It answered 102 items.", chunks, numberSet({ a: 102 }));
    expect(pc.grounding).toBe("Partial");
    expect(pc.blocked).toBe(false);
  });
});

describe("pipeline route", () => {
  it("runs prepare → model → decide and scores with the frozen M2", async () => {
    const calls: string[] = [];
    const bridge: Bridge = {
      async call(req) {
        calls.push(String(req.cmd));
        if (req.cmd === "prepare") return { ok: true, candidate_ids: ["md_1::p1", "md_1::p2"], messages: [{ role: "system", content: "s" }, { role: "user", content: "u" }], pointers: [], retrieval: {}, source_class: "Commercial Banks" } as never;
        return { ok: true, judgement: "same", matched_paragraph_id: "md_1::p1", per_candidate: [], rule: "comparator-rule-v1", parse_problems: [], fields: [], features_m2: [0, 0, 5, 0, 0, 1, 0, 0] } as never;
      },
      close() {},
    };
    const llm = new MockLlm(() => "{}");
    const { app, dir } = makeApp(llm, 50, bridge);
    const j = (await (await post(app, "/api/pipeline", { targetClass: "Commercial Banks", text: "a new query about outsourcing policy" })).json()) as J;
    expect(calls).toEqual(["prepare", "decide"]);
    expect(j.state).toBe("ok");
    expect(j.confidence.model).toBe("M2");
    expect(j.confidenceNote).toBe("calibrated on benchmark; new queries may differ");
    rmSync(dir, { recursive: true });
  });
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type J = Record<string, any>;
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { createApp } from "./app";
import { PythonBridge } from "./bridge";
import { MockLlm } from "./llm";
import { Cache, Quota } from "./store";

const FIELDS = ["actor", "action", "object", "scope", "condition", "threshold", "amount", "percentage", "frequency", "deadline", "exception", "documentation", "reporting"];

// End to end through the real Python bridge: unseen query string → local bge encode (pinned revision) → class-aware RRF →
// frozen comparator prompt → MOCKED model reply → frozen rule → M2 band. No network, no key.
describe("live pipeline end to end (real bridge, mocked LLM)", () => {
  it("handles a new, unseen query string", async () => {
    const UI = process.cwd();
    const dir = mkdtempSync(join(UI, "server/.cache/e2e-"));
    const bridge = new PythonBridge(UI);
    const llm = new MockLlm((m) => {
      const ids = [...m[1].content.matchAll(/\[(md_\d+::p\d+)\]/g)].map((x) => x[1]);
      return JSON.stringify({ source: {}, candidates: ids.map((id, i) => ({ paragraph_id: id, addresses_same_duty: i === 0, fields: {},
        field_comparison: Object.fromEntries(FIELDS.map((f) => [f, "equal"])) })) });
    });
    const app = createApp({ llm, bridge, quota: new Quota(join(dir, "s"), 5), cache: new Cache(join(dir, "c")),
      snapshotPath: join(UI, "src/data/snapshot.json"), modelPath: join(UI, "src/data/confidence_model_v1.json") });
    const query = `An unseen e2e query ${Date.now()}: a non-bank lender outsourcing its IT systems must keep a board-approved outsourcing policy.`;
    const r = await app.request("/api/pipeline", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ targetClass: "Non-Banking Financial Companies", text: query, sourceClass: "Commercial Banks" }) });
    const j = (await r.json()) as J;
    bridge.close();
    rmSync(dir, { recursive: true });
    expect(j.state).toBe("ok");
    expect(j.retrieval.dense_query).toMatch(/encoded locally.*a5beb1e3/);
    expect(j.retrieval.class_filter_applied).toBe(true);
    expect(j.candidates).toHaveLength(2);
    expect(j.judgement).toBe("same");
    expect(j.rule).toBe("comparator-rule-v1");
    expect(["High", "Medium", "Low"]).toContain(j.confidence.band);
    expect(llm.calls).toHaveLength(1);
  }, 240_000);
});

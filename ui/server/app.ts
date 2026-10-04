import { Hono } from "hono";
import { readFileSync } from "node:fs";
import type { Bridge } from "./bridge";
import { bm25Top, groundedMessages, numberSet, postCheck, type Chunk } from "./grounding";
import { LlmError, type LlmClient } from "./llm";
import { Cache, Quota, sha256 } from "./store";

interface Snap {
  results: unknown;
  findings: { id: string; statement: string; sourceKey: string; ciLabel?: string; count?: number }[];
  caveats: { id: string; text: string }[];
  masterSections: { id: string; title: string; text: string }[];
  paired: { label: string; metric: string; ciLabel: string; sourceKey: string; n: number }[];
  gaps: { id: string; expected: string; actual: string; suggestedFix: string }[];
  reliability: { statistic: string; target: string; ciLabel: string; sourceKey: string; design: string }[];
}
interface Model {
  bandThresholds: { high: number; low: number };
  models: { M2: { id: string; label: string; intercept: number; weights: number[]; means: number[]; sds: number[]; features: string[];
    eval: { bands: { band: string; n: number; accuracy: number | null; wilsonCI: [number, number] | null }[]; experimental: boolean } } };
}

export interface Deps { llm: LlmClient | null; bridge: Bridge | null; quota: Quota; cache: Cache; snapshotPath: string; modelPath: string }

export function chunksOf(s: Snap): Chunk[] {
  const out: Chunk[] = [];
  s.findings.forEach((f) => out.push({ id: `finding:${f.id}`, cite: f.sourceKey, text: `Finding ${f.id}: ${f.statement} ${f.ciLabel ?? f.count ?? ""}` }));
  s.paired.forEach((p) => out.push({ id: p.sourceKey, cite: p.sourceKey, text: `${p.label} (${p.metric}, n = ${p.n}): ${p.ciLabel}` }));
  s.reliability.forEach((r) => out.push({ id: r.sourceKey, cite: r.sourceKey, text: `${r.design}: ${r.statistic} ${r.target} ${r.ciLabel}` }));
  s.caveats.forEach((c) => out.push({ id: `caveat:${c.id}`, cite: `caveat:${c.id}`, text: c.text }));
  s.gaps.forEach((g) => out.push({ id: `gap:${g.id}`, cite: `gap:${g.id}`, text: `${g.id}: expected ${g.expected}; actual ${g.actual}; fix ${g.suggestedFix}` }));
  s.masterSections.forEach((m) => {
    const paras = m.text.split(/\n\s*\n/).filter((p) => p.trim().length > 40);
    paras.forEach((p, i) => out.push({ id: `MD §${m.id}#${i}`, cite: `MD §${m.id}`, text: `${m.title}\n${p.slice(0, 1600)}` }));
  });
  return out;
}

function scoreM2(m: Model["models"]["M2"], x: number[]) {
  let z = m.intercept;
  m.weights.forEach((w, i) => { z += ((x[i] - m.means[i]) / m.sds[i]) * w; });
  return 1 / (1 + Math.exp(-z));
}

export function createApp(deps: Deps) {
  const app = new Hono();
  const snap = JSON.parse(readFileSync(deps.snapshotPath, "utf8")) as Snap;
  const model = JSON.parse(readFileSync(deps.modelPath, "utf8")) as Model;
  const chunks = chunksOf(snap);
  const known = numberSet(snap.results, chunks.map((c) => c.text).join(" "));

  const gate = () => {
    if (!deps.llm) return { state: "off" as const, message: "Assistant is off: no ASSISTANT_GEMINI_API_KEY on the proxy." };
    if (deps.quota.remaining() <= 0) return { state: "quota" as const, message: `Daily cap of ${deps.quota.cap} reached.` };
    return null;
  };
  const quota = () => ({ cap: deps.quota.cap, used: deps.quota.used(), remaining: deps.quota.remaining() });
  const ask = async (messages: { role: "system" | "user"; content: string }[], json: boolean) => {
    const key = sha256(JSON.stringify({ m: deps.llm!.name, messages, json }));
    const hit = deps.cache.get(key);
    if (hit !== null) return { text: hit, cached: true };
    deps.quota.consume();
    const text = await deps.llm!.generate(messages, { json });
    deps.cache.set(key, text);
    return { text, cached: false };
  };

  app.get("/api/status", (c) => c.json({ assistant: { enabled: !!deps.llm, ...quota() }, live: { available: !!deps.bridge && !!deps.llm } }));

  app.post("/api/assistant", async (c) => {
    const g = gate();
    if (g) return c.json({ ...g, quota: quota() }); // states are data (200), so the browser console stays clean
    const { question } = await c.req.json<{ question?: string }>();
    if (!question || question.trim().length < 3) return c.json({ state: "error", message: "Empty question." }, 400);
    const top = bm25Top(chunks, question, 6);
    if (!top.length) return c.json({ state: "blocked", grounding: "Unsupported", answer: null, reason: "No project chunk matches the question.", citations: [], quota: quota() });
    try {
      const { text, cached } = await ask(groundedMessages(question, top), false);
      const pc = postCheck(text, top, known);
      return c.json({ state: pc.blocked ? "blocked" : "ok", answer: pc.blocked ? null : text, grounding: pc.grounding, reason: pc.reason, citations: pc.citations,
        unmatchedNumbers: pc.unmatchedNumbers, chunks: top.map((t) => ({ cite: t.cite, id: t.id })), cached, quota: quota() });
    } catch (e) {
      const kind = e instanceof LlmError ? e.kind : "offline";
      return c.json({ state: kind === "quota" ? "quota" : "offline", message: kind === "quota" ? "Provider quota reached." : "The model could not be reached.", quota: quota() });
    }
  });

  app.post("/api/pipeline", async (c) => {
    const g = gate();
    if (g) return c.json({ ...g, quota: quota() });
    if (!deps.bridge) return c.json({ state: "off", message: "Live retrieval bridge unavailable." });
    const body = await c.req.json<{ targetClass?: string; sourcePid?: string | null; text?: string | null; sourceClass?: string | null }>();
    if (!body.targetClass || (!body.sourcePid && !body.text)) return c.json({ state: "error", message: "Need a target class and a source paragraph id or text." }, 400);
    const prep = await deps.bridge.call<{ ok: boolean; error?: string; candidate_ids: string[]; messages: { role: "system" | "user"; content: string }[];
      pointers: unknown[]; source_pointer?: unknown; retrieval: unknown; source_class?: string }>({
      cmd: "prepare", target_class: body.targetClass, source_pid: body.sourcePid ?? null, text: body.text ?? null, source_class: body.sourceClass ?? null });
    if (!prep.ok) return c.json({ state: "error", message: prep.error }, 400);
    try {
      const { text, cached } = await ask(prep.messages, true);
      const dec = await deps.bridge.call<{ ok: boolean; judgement: string; matched_paragraph_id: string | null; per_candidate: [string, string][]; rule: string;
        parse_problems: string[]; fields: unknown[]; features_m2: number[] | null }>({ cmd: "decide", raw: text, candidate_ids: prep.candidate_ids,
        source_pid: body.sourcePid ?? null, source_class: prep.source_class ?? body.sourceClass ?? null });
      const m2 = model.models.M2;
      let confidence: Record<string, unknown> = { model: "M2", band: "Abstain", p: null, label: m2.label };
      if (dec.features_m2) {
        const p = scoreM2(m2, dec.features_m2);
        const band = p >= model.bandThresholds.high ? "High" : p >= model.bandThresholds.low ? "Medium" : "Low";
        confidence = { model: "M2", p, band, stat: m2.eval.bands.find((b) => b.band === band), label: m2.label, experimental: m2.eval.experimental };
      }
      return c.json({ state: "ok", judgement: dec.judgement, matchedPid: dec.matched_paragraph_id, perCandidate: dec.per_candidate, rule: dec.rule,
        parseProblems: dec.parse_problems, fields: dec.fields, candidates: prep.pointers, sourcePointer: prep.source_pointer ?? null, retrieval: prep.retrieval,
        confidence, confidenceNote: "calibrated on benchmark; new queries may differ", cached, quota: quota() });
    } catch (e) {
      const kind = e instanceof LlmError ? e.kind : "offline";
      return c.json({ state: kind === "quota" ? "quota" : "offline", message: String((e as Error).message) });
    }
  });
  return app;
}

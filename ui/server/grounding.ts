// Grounded-LLM route helpers: BM25 over local chunks, the grounded prompt, and the citation + number post-check.

export interface Chunk { id: string; cite: string; text: string }

const tok = (s: string) => (s.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => w.length > 1);

export function bm25Top(chunks: Chunk[], query: string, k = 6, k1 = 1.5, b = 0.75): Chunk[] {
  const docs = chunks.map((c) => tok(c.text + " " + c.cite));
  const avg = docs.reduce((a, d) => a + d.length, 0) / Math.max(1, docs.length);
  const df = new Map<string, number>();
  docs.forEach((d) => new Set(d).forEach((w) => df.set(w, (df.get(w) ?? 0) + 1)));
  const q = [...new Set(tok(query))];
  const scored = docs.map((d, i) => {
    const tf = new Map<string, number>();
    d.forEach((w) => tf.set(w, (tf.get(w) ?? 0) + 1));
    let s = 0;
    for (const w of q) {
      const f = tf.get(w) ?? 0;
      if (!f) continue;
      const idf = Math.log(1 + (docs.length - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      s += idf * ((f * (k1 + 1)) / (f + k1 * (1 - b + (b * d.length) / avg)));
    }
    return { i, s };
  });
  return scored.filter((x) => x.s > 0).sort((a, b2) => b2.s - a.s).slice(0, k).map((x) => chunks[x.i]);
}

export const NOT_IN_RECORD = "Not in the project record.";

export function groundedMessages(question: string, chunks: Chunk[]) {
  const ctx = chunks.map((c) => `[${c.cite}]\n${c.text}`).join("\n\n---\n\n");
  return [
    { role: "system" as const, content:
      "You answer questions about the RBI-ObliBench research project using ONLY the context chunks provided. Cite every sentence with the chunk label in square brackets, " +
      "exactly as given (for example [phase4.t1_paired] or [MD §9.2]). Copy numbers exactly as written in the chunks; never compute, round or invent a number. " +
      `If the chunks do not support an answer, reply exactly: ${NOT_IN_RECORD}` },
    { role: "user" as const, content: `Context chunks:\n\n${ctx}\n\nQuestion: ${question}` },
  ];
}

const NUM = /(?<![\w.])[-+−]?\d+(?:,\d{3})*(?:\.\d+)?%?/g;

export interface PostCheck {
  grounding: "Exact" | "Partial" | "Unsupported";
  blocked: boolean;
  reason: string;
  citations: string[];
  unmatchedNumbers: string[];
  uncitedSentences: number;
}

/** Every number must occur in the snapshot's number set (R6); every citation must be one of the chunks given. */
export function postCheck(answer: string, chunks: Chunk[], knownNumbers: Set<string>): PostCheck {
  const text = answer.trim();
  if (!text || text.startsWith(NOT_IN_RECORD)) {
    return { grounding: "Unsupported", blocked: true, reason: "The project record does not support an answer.", citations: [], unmatchedNumbers: [], uncitedSentences: 0 };
  }
  const allowed = new Set(chunks.map((c) => c.cite));
  const cites = [...text.matchAll(/\[([^\]]+)\]/g)].map((m) => m[1].trim());
  const badCites = cites.filter((c) => !allowed.has(c));
  const stripped = text.replace(/\[([^\]]+)\]/g, " ");
  const nums = (stripped.match(NUM) ?? []).map((n) => n.replace("−", "-").replace(/^\+/, ""));
  const unmatched = nums.filter((n) => !knownNumbers.has(n) && !knownNumbers.has(n.replace(/^-/, "")) && !/^(19|20)\d\d$/.test(n) && !/^[0-9]$/.test(n));
  const sentences = text.split(/(?<=[.!?])\s+/).filter((s) => s.replace(/\[[^\]]+\]/g, "").trim().length > 3);
  const uncited = sentences.filter((s) => !/\[[^\]]+\]/.test(s)).length;
  if (unmatched.length || badCites.length) {
    return { grounding: "Unsupported", blocked: true, citations: cites, unmatchedNumbers: unmatched, uncitedSentences: uncited,
      reason: unmatched.length ? `R6: number(s) ${unmatched.join(", ")} do not match any value in the snapshot; the answer is blocked.`
        : `Citation(s) ${badCites.join(", ")} are not among the retrieved chunks; the answer is blocked.` };
  }
  return { grounding: uncited === 0 && cites.length > 0 ? "Exact" : "Partial", blocked: false, citations: [...new Set(cites)], unmatchedNumbers: [], uncitedSentences: uncited,
    reason: uncited === 0 ? "Every sentence cites a retrieved chunk and every number matches the snapshot." : `${uncited} sentence(s) carry no citation.` };
}

/** All renderings of every number in the snapshot results (mirrors src/release/stale_numbers.renderings, simplified). */
export function numberSet(results: unknown, extraText = ""): Set<string> {
  const out = new Set<string>();
  const add = (v: number) => {
    for (const d of [0, 1, 2, 3, 4]) { out.add(v.toFixed(d)); out.add(Math.abs(v).toFixed(d)); }
    out.add(String(v));
    if (v >= 0 && v <= 1) { out.add(`${(v * 100).toFixed(0)}%`); out.add(`${(v * 100).toFixed(1)}%`); }
    if (Math.abs(v) >= 1000) out.add(Math.round(v).toLocaleString("en-US"));
  };
  const walk = (o: unknown) => {
    if (typeof o === "number") add(o);
    else if (Array.isArray(o)) o.forEach(walk);
    else if (o && typeof o === "object") Object.values(o).forEach(walk);
    else if (typeof o === "string") (o.match(NUM) ?? []).forEach((n) => out.add(n.replace("−", "-").replace(/^\+/, "").replace(/^-/, "")));
  };
  walk(results);
  (extraText.match(NUM) ?? []).forEach((n) => { const x = n.replace("−", "-").replace(/^\+/, ""); out.add(x); out.add(x.replace(/^-/, "")); });
  return out;
}

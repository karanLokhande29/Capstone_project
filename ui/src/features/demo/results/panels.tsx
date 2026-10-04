import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { useJson } from "../data";
import { Loading } from "../DemoLayout";
import { pct0 } from "../names";
import type { T2Query, T3Item, T4Shard } from "../types";

// ---- K2: T3 amendment timeline -----------------------------------------------------------------------------------

const STATUS: Record<string, string> = { in_force_original: "in force, original", amended: "amended", deleted: "deleted" };
const DAY = 86400000;

export function T3Timeline() {
  const d = useJson<{ items: T3Item[] }>("t3.json").data;
  const [id, setId] = useState<string | null>(null);
  const [offset, setOffset] = useState<number | null>(null);
  if (!d) return <Loading what="the date questions" />;
  const items = d.items;
  const it = items.find((x) => x.id === id) ?? items.find((x) => x.side === "after")!;
  const eff = it.effective ? Date.parse(it.effective) : null;
  const asOf = Date.parse(it.asOf);
  const lo = Math.min(asOf, eff ?? asOf) - 120 * DAY;
  const hi = Math.max(asOf, eff ?? asOf) + 120 * DAY;
  const marker = offset == null ? asOf : lo + offset * DAY;
  const at = (t: number) => `${((t - lo) / (hi - lo)) * 100}%`;
  const atStored = Math.abs(marker - asOf) < DAY / 2;
  const recordStatus = eff == null || marker < eff ? "in_force_original" : it.action === "delete" ? "deleted" : "amended";
  const ok = (s: string) => s === it.gold;
  return (
    <Card className="mt-5"><CardBody className="space-y-3 text-[13.5px]">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-0 flex-col gap-1 text-[12px] text-ink-3">Date question (52 scored)
          <select value={it.id} onChange={(e) => { setId(e.target.value); setOffset(null); }} className="h-9 max-w-full rounded-md border border-line bg-panel px-2 text-[13px] text-ink">
            {items.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.side === "after" ? "after" : "before"} a {x.action} · as of {x.asOf}</option>)}
          </select>
        </label>
        {it.url && <a href={it.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 pb-2 text-[12.5px] text-accent hover:underline">{it.pid} <ExternalLink size={12} /></a>}
      </div>
      <div className="relative mx-2 mt-6 h-12" aria-hidden>
        <div className="absolute left-0 right-0 top-6 h-0.5 bg-line" />
        {eff != null && <div className="absolute top-2 -translate-x-1/2 text-center" style={{ left: at(eff) }}>
          <div className="mx-auto h-4 w-4 rounded-full border-2 border-warn bg-bg" /><p className="mt-0.5 whitespace-nowrap text-[11px] text-warn">{it.action} effective {it.effective}</p></div>}
        <div className="absolute top-0 -translate-x-1/2" style={{ left: at(marker) }}><div className="mx-auto h-8 w-0.5 bg-accent" /><p className="whitespace-nowrap text-[11px] font-semibold text-accent">as of {new Date(marker).toISOString().slice(0, 10)}</p></div>
      </div>
      <label className="block text-[12px] text-ink-3">Drag the as-of date
        <input type="range" min={0} max={Math.round((hi - lo) / DAY)} value={Math.round((marker - lo) / DAY)} onChange={(e) => setOffset(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]"
          aria-valuetext={new Date(marker).toISOString().slice(0, 10)} />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-line p-3">
          <p className="font-semibold">With the date check</p>
          {atStored ? <p className="mt-1">Model answered <b>{STATUS[it.on] ?? it.on}</b> {ok(it.on) ? "✓" : "✗"} <span className="text-ink-3">(stored answer)</span></p>
            : <p className="mt-1">The amendment record says <b>{STATUS[recordStatus]}</b> on this date. <span className="text-ink-3">No stored model answer: the question was asked only as of {it.asOf}.</span></p>}
        </div>
        <div className="rounded-lg border border-line p-3">
          <p className="font-semibold">Without the date check</p>
          {atStored ? <p className="mt-1">Model answered <b>{STATUS[it.off] ?? it.off}</b> {ok(it.off) ? "✓" : "✗"} <span className="text-ink-3">(stored answer)</span></p>
            : <p className="mt-1 text-ink-3">No stored answer for this date. Across all 52 questions the model answered “in force, original” {items.filter((x) => x.off === "in_force_original").length} times.</p>}
        </div>
      </div>
      <p className="text-[12.5px] text-ink-2">Expert-derived status as of {it.asOf}: <b>{STATUS[it.gold] ?? it.gold}</b>. Earlier wording isn't available: RBI consolidates amendments in place, so the corpus has only current text. Caveat: the gold statuses and the date filter share one amendment parser.</p>
    </CardBody></Card>
  );
}

// ---- K3: T2 institution-filter animation -------------------------------------------------------------------------

const BUCKETS: [string, (r: number | null) => boolean][] = [
  ["1", (r) => r === 1], ["2–3", (r) => r != null && r >= 2 && r <= 3], ["4–10", (r) => r != null && r >= 4 && r <= 10],
  ["11–20", (r) => r != null && r >= 11 && r <= 20], ["21–100", (r) => r != null && r >= 21 && r <= 100], ["not in top 100", (r) => r == null],
];

export function T2FilterPanel() {
  const d = useJson<{ queries: T2Query[] }>("t2_rankings.json").data;
  const [on, setOn] = useState(false);
  const [qid, setQid] = useState<string | null>(null);
  const qs = useMemo(() => d?.queries ?? [], [d]);
  const dist = useMemo(() => {
    const f = (sys: string) => BUCKETS.map(([label, test]) => ({ label, n: qs.filter((q) => test(q.ranks[sys] ?? null)).length }));
    return { off: f("hybrid_rrf"), on: f("class_aware") };
  }, [qs]);
  if (!d) return <Loading what="the rankings" />;
  const q = qs.find((x) => x.id === qid) ?? qs.find((x) => (x.ranks.hybrid_rrf ?? 999) > 10 && x.ranks.class_aware === 1) ?? qs[0];
  const rank = (on ? q.ranks.class_aware : q.ranks.hybrid_rrf) ?? null;
  const pos = (r: number | null) => `${r == null ? 100 : (Math.log(r) / Math.log(100)) * 96}%`;
  const cur = on ? dist.on : dist.off;
  const max = Math.max(...dist.off.map((b) => b.n), ...dist.on.map((b) => b.n));
  return (
    <Card className="mt-5"><CardBody className="space-y-3 text-[13.5px]">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-[12px] text-ink-3">Search (a real benchmark query: source rule → target institution)
          <select value={q.id} onChange={(e) => setQid(e.target.value)} className="h-9 min-w-0 rounded-md border border-line bg-panel px-2 text-[13px] text-ink">
            {qs.map((x) => <option key={x.id} value={x.id}>{x.src} → {x.tgt} · {x.srcPid}</option>)}
          </select>
        </label>
        <button type="button" role="switch" aria-checked={on} onClick={() => setOn(!on)}
          className={cn("h-9 rounded-full border px-4 text-[13px] font-medium", on ? "border-accent bg-accent text-white dark:text-black" : "border-line bg-panel")}>
          Institution filter {on ? "ON" : "OFF"}
        </button>
      </div>
      <div>
        <p className="text-[12.5px] text-ink-2">Rank of the expert's matching paragraph for this query (log scale):</p>
        <div className="relative mx-3 mt-6 h-8">
          <div className="absolute left-0 right-0 top-3 h-0.5 bg-line" />
          {[1, 3, 10, 30, 100].map((t) => <span key={t} className="absolute top-5 -translate-x-1/2 text-[10.5px] text-ink-3" style={{ left: pos(t) }}>{t}</span>)}
          <div className="absolute -top-4 -translate-x-1/2 transition-[left] duration-700 ease-out" style={{ left: pos(rank) }}>
            <span className="whitespace-nowrap rounded bg-accent px-1.5 py-0.5 text-[11px] font-semibold text-white dark:text-black">{rank == null ? "not in top 100" : `rank ${rank}`}</span>
            <div className="mx-auto h-3 w-0.5 bg-accent" />
          </div>
        </div>
      </div>
      <div>
        <p className="text-[12.5px] text-ink-2">All {qs.length} scored queries: rank of the matching paragraph, filter {on ? "on" : "off"}</p>
        <div className="mt-2 grid grid-cols-6 items-end gap-1.5" style={{ height: 120 }} role="img" aria-label={cur.map((b) => `${b.label}: ${b.n}`).join(", ")}>
          {cur.map((b) => <div key={b.label} className="flex h-full flex-col justify-end"><span className="num text-center text-[11px]">{b.n}</span><div className="rounded-t bg-accent/80 transition-[height] duration-700" style={{ height: `${(b.n / max) * 85}%` }} /></div>)}
        </div>
        <div className="mt-1 grid grid-cols-6 gap-1.5 text-center text-[10.5px] text-ink-3">{cur.map((b) => <span key={b.label}>{b.label}</span>)}</div>
      </div>
      <p className="text-[12px] text-ink-3">Off = hybrid keyword + meaning search over all Directions; on = the same search restricted to the target institution type. Relevance labels cover only the target-class counterpart, so part of the gain is by construction.</p>
    </CardBody></Card>
  );
}

// ---- K7 (static): RePASs playground -------------------------------------------------------------------------------

const TYPES: [string, string][] = [["genuine", "Real answer"], ["concatenated", "Pasted rule sentences"], ["adv_negated", "Pasted, meaning reversed"], ["adv_offtopic", "Unrelated rule"]];

export function RePASsPanel() {
  const d = useJson<T4Shard>("t4.json").data;
  const [qid, setQid] = useState<string | null>(null);
  if (!d) return <Loading what="the RePASs scores" />;
  const q = d.questions.find((x) => x.id === qid) ?? d.questions[0];
  const f = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(3)}`;
  return (
    <Card className="mt-5"><CardBody className="space-y-3 text-[13.5px]">
      <p className="text-[15px] font-semibold">Copying the evidence − a genuine answer = <span className="num">{f(d.gap.mean)}</span> <span className="num text-[13px] font-normal text-ink-2">[{f(d.gap.ci[0])}, {f(d.gap.ci[1])}]</span></p>
      <label className="flex min-w-0 flex-col gap-1 text-[12px] text-ink-3">Question
        <select value={q.id} onChange={(e) => setQid(e.target.value)} className="h-9 min-w-0 rounded-md border border-line bg-panel px-2 text-[13px] text-ink">
          {d.questions.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.question}</option>)}
        </select>
      </label>
      <p className="text-ink-2">“{q.question}” <span className="text-ink-3">({q.entityClass})</span> {q.url && <a href={q.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">source <ExternalLink size={11} className="inline" /></a>}</p>
      <ul className="space-y-1.5">
        {TYPES.map(([k, label]) => {
          const s = q.scores[k];
          return s ? (
            <li key={k} className="grid grid-cols-[minmax(0,180px)_1fr_48px] items-center gap-2">
              <span className="text-ink-2">{label}</span>
              <span className="h-3 rounded bg-panel-2"><span className={cn("block h-3 rounded", k === "concatenated" ? "bg-accent" : "bg-ink-3/50")} style={{ width: pct0(Math.max(0.01, s.composite)) }} /></span>
              <span className="num text-right">{s.composite.toFixed(2)}</span>
            </li>
          ) : null;
        })}
      </ul>
      <p className="text-[12px] text-ink-3">Stored RePASs composite scores for this question. Answer texts are not shown (the pasted answers are RBI text). Live scoring is not offered.</p>
    </CardBody></Card>
  );
}

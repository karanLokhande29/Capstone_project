import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, Play } from "lucide-react";
import { useData, useSettings } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { fromBand, unitConfidence } from "@/data/confidence";
import { useProxyStatus } from "@/features/assistant/Assistant";
import { NO_PROXY } from "@/lib/env";
import { PageHeader } from "@/components/Page";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { Pointer } from "@/components/Pointer";
import type { Band } from "@/domain/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = { equal: "text-ink-3", differs: "bg-warn-soft text-warn", only_source: "bg-neg-soft text-neg", only_target: "bg-neg-soft text-neg", absent: "text-ink-3" };

function TemporalBadge({ inForceFrom, amendedBy, asOf }: { inForceFrom?: string | null; amendedBy: string[]; asOf: string }) {
  const notYet = inForceFrom && asOf < inForceFrom;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={notYet ? "neg" : "pos"}>{notYet ? `not in force on ${asOf} (from ${inForceFrom})` : `in force on ${asOf}${inForceFrom ? ` (from ${inForceFrom})` : ""}`}</Badge>
      {amendedBy.length > 0 && <Badge tone="warn">amended by {amendedBy.length}</Badge>}
      <Badge tone="outline" title="RBI consolidates amendments in place: only current text exists in the corpus.">amended text only</Badge>
    </span>
  );
}

export function FieldDiff({ rows }: { rows: { field: string; status: string; material?: boolean; sourceValue?: string | null; targetValue?: string | null }[] }) {
  if (!rows.length) return <p className="text-[12px] text-ink-3">No parsed field comparison.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px] text-[11.5px]"><tbody>
        {rows.map((r) => (
          <tr key={r.field} className="border-t border-line">
            <td className="py-0.5 pr-2">{r.material ? "• " : ""}{r.field}</td>
            {"sourceValue" in r && <td className="pr-2 text-ink-2">{r.sourceValue ?? "—"}</td>}
            {"targetValue" in r && <td className="pr-2 text-ink-2">{r.targetValue ?? "—"}</td>}
            <td><span className={cn("rounded px-1", STATUS_TONE[r.status])}>{r.status}</span></td>
          </tr>
        ))}
      </tbody></table>
    </div>
  );
}

interface LiveResult {
  state: string; message?: string; judgement?: string; matchedPid?: string | null; rule?: string; parseProblems?: string[];
  fields?: { field: string; status: string; material: boolean }[]; candidates?: { id: string; url?: string; harvestDate?: string; excerpt?: string | null; title?: string }[];
  retrieval?: { system: string; dense_query: string }; confidence?: { model: string; p: number | null; band: Band }; confidenceNote?: string; quota?: { used: number; cap: number };
}

function LivePanel({ classes }: { classes: string[] }) {
  const model = useData((st) => st.confidence);
  const [mode, setMode] = useState<"text" | "pid">("text");
  const [text, setText] = useState("");
  const [pid, setPid] = useState("");
  const [target, setTarget] = useState(classes[0] ?? "");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<LiveResult | null>(null);
  const { status, offline } = useProxyStatus(true);
  const ready = !!status?.live.available;
  const run = async () => {
    setBusy(true);
    setRes(null);
    try {
      const r = await fetch("/api/pipeline", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ targetClass: target, sourcePid: mode === "pid" ? pid.trim() : null, text: mode === "text" ? text.trim() : null, sourceClass: source || null }) });
      setRes(await r.json());
    } catch {
      setRes({ state: "offline", message: "The local proxy is not running (cd ui && npm run server)." });
    } finally { setBusy(false); }
  };
  const conf = res?.confidence && model ? fromBand(model.models.M2, res.confidence.band, res.confidence.p) : null;
  return (
    <Card className="border-product/40"><CardBody className="space-y-3 text-[13px]">
      <p className="font-semibold">Live mode <Badge tone="product">opt-in · uses ASSISTANT_GEMINI_API_KEY</Badge></p>
      <p className="text-[12px] text-ink-3">{offline ? "Proxy offline: start it with `npm run server`." : !status ? "Checking the local proxy…"
        : ready ? `Proxy ready · ${status.assistant.used}/${status.assistant.cap} calls today.` : "Proxy running but off: no ASSISTANT_GEMINI_API_KEY in ui/.env."}</p>
      <div className="flex gap-1">{(["text", "pid"] as const).map((m) => <Button key={m} size="sm" variant={mode === m ? "product" : "outline"} onClick={() => setMode(m)}>{m === "text" ? "New obligation text" : "Existing paragraph id"}</Button>)}</div>
      {mode === "text" ? <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="Describe or paste an obligation (it is embedded locally with bge-base-en-v1.5 @ a5beb1e3)…"
        className="w-full rounded-md border border-line bg-panel p-2 text-[13px]" aria-label="Obligation text" />
        : <input value={pid} onChange={(e) => setPid(e.target.value)} placeholder="md_12925::p00044" className="w-full rounded-md border border-line bg-panel p-2 font-mono text-[12px]" aria-label="Paragraph id" />}
      <div className="flex flex-wrap gap-3">
        <label>Compare against class <select value={target} onChange={(e) => setTarget(e.target.value)} className="rounded border border-line bg-panel px-1">{classes.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Your class (optional) <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border border-line bg-panel px-1"><option value="">—</option>{classes.map((c) => <option key={c}>{c}</option>)}</select></label>
        <Button variant="product" size="sm" disabled={busy || !ready || (mode === "text" ? text.trim().split(/\s+/).length < 3 : !pid.trim())} onClick={run}><Play size={13} />{busy ? "Running…" : "Run pipeline"}</Button>
      </div>
      {res && res.state !== "ok" && <p className="text-warn"><AlertTriangle size={13} className="mr-1 inline" />{res.state}: {res.message}</p>}
      {res?.state === "ok" && (
        <div className="space-y-2">
          <p>Verdict (frozen rule {res.rule}): <Badge tone="accent">{res.judgement}</Badge> {res.matchedPid && <>matched <code>{res.matchedPid}</code></>}</p>
          <div className="flex flex-wrap items-center gap-2"><ConfidenceBadge c={conf} /><span className="text-[11.5px] text-warn">{res.confidenceNote}</span></div>
          <p className="text-[11.5px] text-ink-3">Retrieval: {res.retrieval?.system}; dense query {res.retrieval?.dense_query}.</p>
          {res.candidates?.map((c) => (
            <div key={c.id} className="rounded-md border border-line p-2 text-[12px]"><code className="text-accent">{c.id}</code> {c.url && <a className="text-ink-3 hover:text-accent" href={c.url} target="_blank" rel="noreferrer">source</a>}
              <span className="text-ink-3"> · harvested {c.harvestDate}</span>{c.excerpt && <p className="text-ink-2">“{c.excerpt}”</p>}</div>
          ))}
          <FieldDiff rows={res.fields ?? []} />
          {res.quota && <p className="text-[11px] text-ink-3">{res.quota.used}/{res.quota.cap} calls today.</p>}
        </div>
      )}
    </CardBody></Card>
  );
}

export default function ObligationExplorer() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const live = useSettings((st) => st.liveEnabled);
  const open = useDrawer((st) => st.open);
  const [sp, setSp] = useSearchParams();
  const sourceClasses = useMemo(() => [...new Set(s.t1Items.map((i) => i.sourceClass))].sort(), [s.t1Items]);
  const cls = sp.get("class") ?? sourceClasses[0];
  const fams = [...new Set(s.t1Items.filter((i) => i.sourceClass === cls).map((i) => i.subjectFamily ?? ""))].sort();
  const fam = sp.get("family") && fams.includes(sp.get("family")!) ? sp.get("family")! : fams[0];
  const cmpClasses = [...new Set(s.t1Items.filter((i) => i.sourceClass === cls && (i.subjectFamily ?? "") === fam).flatMap((i) => i.comparedClasses))].sort();
  const vs = sp.get("vs") && cmpClasses.includes(sp.get("vs")!) ? sp.get("vs")! : cmpClasses[0];
  const asOf = sp.get("asof") ?? "2026-10-03";
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }); };
  const items = s.t1Items.filter((i) => i.sourceClass === cls && (i.subjectFamily ?? "") === fam && i.comparedClasses.includes(vs));
  const allClasses = s.entityClasses.map((c) => c.id);
  return (
    <div>
      <PageHeader title="Obligation Explorer" tier="COULD" product
        subtitle="What must your entity class do here, and what differs for another class? Offline mode browses the benchmark items and the frozen comparator's existing predictions." />
      <Card className="mb-3"><CardBody className="flex flex-wrap gap-3 text-[13px]">
        <label>Your entity class <select value={cls} onChange={(e) => set("class", e.target.value)} className="rounded border border-line bg-panel px-1">{sourceClasses.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Subject family <select value={fam} onChange={(e) => set("family", e.target.value)} className="max-w-[260px] rounded border border-line bg-panel px-1">{fams.map((f) => <option key={f}>{f}</option>)}</select></label>
        <label>Compare with <select value={vs} onChange={(e) => set("vs", e.target.value)} className="rounded border border-line bg-panel px-1">{cmpClasses.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>As-of date <input type="date" value={asOf} onChange={(e) => set("asof", e.target.value)} className="rounded border border-line bg-panel px-1" /></label>
      </CardBody></Card>
      <div className="space-y-3">
        {items.length === 0 && <p className="text-sm text-ink-3">No benchmark obligation for this combination.</p>}
        {items.map((it) => {
          const uid = `${it.id}|${vs}`;
          const u = d.unitById.get(uid)!;
          const cf = s.comparatorFields[uid];
          const cmp = u.predictions.comparator;
          return (
            <Card key={it.id}><CardBody className="space-y-2 text-[13px]">
              <div className="flex flex-wrap items-center gap-2"><b>{it.sourceClass}</b><span className="text-ink-3">clause {it.clausePath}</span>
                <TemporalBadge inForceFrom={it.inForceFrom} amendedBy={it.amendedBy} asOf={asOf} /></div>
              <Pointer pid={it.sourcePid} label="obligation" />
              <div className="rounded-md bg-panel-2 p-2">
                <p>Versus <b>{vs}</b>: comparator says <Badge tone={cmp.judgement === "different" ? "warn" : cmp.judgement === "same" ? "pos" : "neutral"}>{cmp.judgement}</Badge>
                  <span className="ml-2 inline-flex"><ConfidenceBadge c={unitConfidence(model, uid, "M2")} /></span></p>
                {cmp.matchedPid && <Pointer pid={cmp.matchedPid} label="counterpart" />}
                <p className="mt-1 text-[11.5px] text-ink-3">Benchmark label (single-expert gold): {u.goldJudgement}. <button type="button" className="cursor-pointer text-accent" onClick={() => open(`unit:${uid}`)}>View the evidence →</button></p>
              </div>
              {cf?.parseOk && <FieldDiff rows={cf.rows.filter((r) => r.status !== "absent")} />}
            </CardBody></Card>
          );
        })}
      </div>
      <div className="mt-4">
        {NO_PROXY ? (
          <Card><CardBody className="text-[12.5px] text-ink-2">Live mode runs the real class-aware retrieval and the frozen comparator on a new query. It needs the
            local proxy and its own <code>ASSISTANT_GEMINI_API_KEY</code>, so it is available only when the app runs locally (see <code>ui/README.md</code>). This hosted
            version browses the benchmark items and the comparator's existing predictions.</CardBody></Card>
        ) : live ? <LivePanel classes={allClasses} /> : (
          <Card><CardBody className="text-[12.5px] text-ink-2">Live mode is off. To run the real class-aware retrieval and the frozen comparator on a new query: enable it in Settings, put
            <code> ASSISTANT_GEMINI_API_KEY</code> (a separate Google Cloud project) in <code>ui/.env</code>, and run <code>npm run server</code>.</CardBody></Card>
        )}
      </div>
    </div>
  );
}

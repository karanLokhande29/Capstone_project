import { useEffect, useMemo, useState } from "react";
import { Download, Lock } from "lucide-react";
import { useData } from "@/data/store";
import { PageHeader } from "@/components/Page";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { Pointer } from "@/components/Pointer";
import { downloadText } from "@/lib/utils";
import { ARTIFACT } from "@/lib/env";
import { useNow } from "@/app/Countdown";

type Label = "same" | "different" | "none" | "unsure";
interface Store { rater: string; washoutDays: number; items: string[]; pass1: Record<string, { at: string; labels: Record<string, Label> }>; pass2: Record<string, { at: string; labels: Record<string, Label> }> }
const KEY = "cc-workbench";
const empty: Store = { rater: "rater_2", washoutDays: 7, items: [], pass1: {}, pass2: {} };
function load(): Store { try { return { ...empty, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { return empty; } }

/** Future Work #1–#2: second-rater labels and a retest with an enforced washout. Browser-local; never writes repository files. */
export default function Workbench() {
  const s = useData((st) => st.snapshot)!;
  const now = useNow(15_000);
  const [st, setSt] = useState<Store>(load);
  const [pass, setPass] = useState<1 | 2>(1);
  const [cur, setCur] = useState(0);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* memory only */ } }, [st]);
  const sample = useMemo(() => {
    if (st.items.length) return st.items;
    const ids = s.t1Items.map((i) => i.id).sort();
    return ids.filter((_, i) => i % 5 === 0).slice(0, 20); // deterministic stratum-agnostic draw of 20 items
  }, [s.t1Items, st.items]);
  const item = s.t1Items.find((i) => i.id === sample[cur]);
  const p1 = st.pass1[item?.id ?? ""];
  const p1Done = sample.filter((id) => st.pass1[id]).length;
  const p1Finished = sample.length > 0 && p1Done === sample.length;
  const lastP1 = Object.values(st.pass1).map((x) => x.at).sort().at(-1);
  const unlockAt = lastP1 ? new Date(new Date(lastP1).getTime() + st.washoutDays * 86_400_000) : null;
  const locked = pass === 2 && (!p1Finished || !unlockAt || now < unlockAt);
  const rec = (pass === 1 ? st.pass1 : st.pass2)[item?.id ?? ""];
  const [draft, setDraft] = useState<Record<string, Label>>({});
  useEffect(() => { setDraft(rec?.labels ?? {}); }, [rec, item?.id, pass]);
  const commit = () => {
    if (!item) return;
    const entry = { at: new Date().toISOString(), labels: draft };
    setSt((x) => ({ ...x, items: sample, [pass === 1 ? "pass1" : "pass2"]: { ...(pass === 1 ? x.pass1 : x.pass2), [item.id]: entry } }));
    setCur((c) => Math.min(sample.length - 1, c + 1));
  };
  const csv = () => {
    const rows = ["rater,pass,item_id,compared_class,label,labelled_at"];
    for (const [p, recs] of [["1", st.pass1], ["2", st.pass2]] as const)
      for (const [id, r] of Object.entries(recs)) for (const [c, l] of Object.entries(r.labels)) rows.push([st.rater, p, id, `"${c}"`, l, r.at].join(","));
    downloadText(`workbench_${st.rater}.csv`, rows.join("\n"), "text/csv");
  };
  return (
    <div>
      <PageHeader title="Annotation workbench" tier="COULD" subtitle="For Future Work #1 (retest with a proper washout) and #2 (second raters). Labels stay in this browser and export as CSV; nothing is written to the repository."
        actions={<Button variant="outline" size="sm" onClick={csv}><Download size={13} />{ARTIFACT ? "Copy CSV" : "Export CSV"}</Button>} />
      <Card className="mb-3"><CardBody className="flex flex-wrap items-center gap-3 text-[12.5px]">
        <label>Rater id <input value={st.rater} onChange={(e) => setSt({ ...st, rater: e.target.value.replace(/[^a-z0-9_]/gi, "") })} className="ml-1 w-24 rounded border border-line bg-panel px-1" /></label>
        <label>Washout (days) <input type="number" min={1} value={st.washoutDays} onChange={(e) => setSt({ ...st, washoutDays: Math.max(1, Number(e.target.value)) })} className="ml-1 w-14 rounded border border-line bg-panel px-1" /></label>
        <div className="inline-flex overflow-hidden rounded-md border border-line">{([1, 2] as const).map((p) => <button key={p} type="button" onClick={() => setPass(p)} className={`cursor-pointer px-3 py-1 ${pass === p ? "bg-accent text-white dark:text-black" : ""}`}>Pass {p}</button>)}</div>
        <span>Pass 1: {p1Done}/{sample.length}</span>
        {unlockAt && <span className="text-ink-3">Pass 2 unlocks {unlockAt.toLocaleString()}</span>}
      </CardBody></Card>
      {locked ? (
        <Card><CardBody className="flex items-center gap-2 text-[13px]"><Lock size={16} className="text-warn" />
          Pass 2 is locked: {p1Finished ? `the ${st.washoutDays}-day washout has not elapsed since the last pass-1 label.` : "finish pass 1 first."} Pass-1 labels are hidden in pass 2 (blind).</CardBody></Card>
      ) : item ? (
        <Card><CardBody className="space-y-3 text-[13px]">
          <div className="flex flex-wrap items-center gap-2"><Badge>{cur + 1}/{sample.length}</Badge><b>{item.sourceClass}</b><span className="text-ink-3">{item.subjectFamily}</span>{rec && <Badge tone="pos">labelled {new Date(rec.at).toLocaleString()}</Badge>}</div>
          <Pointer pid={item.sourcePid} label="source obligation" />
          <p className="text-[12px] text-ink-3">Read the full paragraph locally (python3 release/rehydrate.py). Judge each compared class: same / different / none / unsure (guidelines v3.4).</p>
          <div className="space-y-1.5">{item.comparedClasses.map((c) => (
            <div key={c} className="flex flex-wrap items-center gap-2"><span className="w-56">{c}</span>
              {(["same", "different", "none", "unsure"] as Label[]).map((l) => (
                <label key={l} className="flex items-center gap-1"><input type="radio" name={`${item.id}-${c}`} value={l} aria-label={`${c}: ${l}`}
                  checked={draft[c] === l} onChange={() => setDraft({ ...draft, [c]: l })} />{l}</label>))}
            </div>))}</div>
          {pass === 2 && p1 && <p className="text-[11.5px] text-ink-3">Pass-1 labels are hidden (blind retest).</p>}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={cur === 0} onClick={() => setCur(cur - 1)}>Previous</Button>
            <Button size="sm" disabled={item.comparedClasses.some((c) => !draft[c])} onClick={commit}>Save &amp; next</Button>
          </div>
        </CardBody></Card>
      ) : <p className="text-sm text-ink-3">No items.</p>}
    </div>
  );
}

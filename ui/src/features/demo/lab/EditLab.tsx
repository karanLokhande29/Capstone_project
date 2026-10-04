import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Play } from "lucide-react";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { liveAvailable, presenter, useFullText, type ApiState } from "../api";
import { StatusBadge } from "../badges";
import { caseHref, useCase, useJson } from "../data";
import { Loading } from "../DemoLayout";
import { FIELD_LABEL, VERDICT } from "../names";
import type { Field } from "../types";
import { diffWithSealed, useLiveRun } from "./live";
import { LivePanel, SealedPanel } from "./panels";

interface Bases { bases: { unitId: string; targetPid: string; verdict: "same" | "different"; kinds: string[] }[]; eligible: { same: number; different: number }; note: string }
export interface Edit { kind: string; pid: string; from: string; to: string; label: string }

/** Deterministic text transforms per field type (structured buttons; no free-text editor in v1). */
export function editsFor(text: string, pid: string): Edit[] {
  const out: Edit[] = [];
  const add = (kind: string, from: string, to: string, label: string) => { if (from && from !== to && text.includes(from)) out.push({ kind, pid, from, to, label }); };
  const freq = /\b(quarterly|monthly|annually|half-yearly|yearly|weekly)\b/i.exec(text);
  if (freq) for (const alt of ["monthly", "annually", "quarterly"]) if (alt !== freq[1].toLowerCase()) add("frequency", freq[0], freq[0][0] === freq[0][0].toUpperCase() ? alt[0].toUpperCase() + alt.slice(1) : alt, `${freq[0]} → ${alt}`);
  const dl = /\bwithin (\d+) days\b/i.exec(text);
  if (dl) { const n = Number(dl[1]); add("deadline", dl[0], dl[0].replace(dl[1], String(n * 2)), `within ${n} days → ${n * 2} days`); }
  const amt = /(₹|Rs\.?|INR)\s?([\d,]+(?:\.\d+)?)/i.exec(text);
  if (amt) { const v = Number(amt[2].replace(/,/g, "")); if (v) add("amount", amt[0], amt[0].replace(amt[2], (v * 2).toLocaleString("en-IN")), `${amt[0]} → doubled`); }
  const pc = /\b(\d+(?:\.\d+)?)\s?(per cent|percent|%)/i.exec(text);
  if (pc) { const v = Number(pc[1]); add("percentage", pc[0], pc[0].replace(pc[1], String(v + 5)), `${pc[0]} → ${v + 5} ${pc[2]}`); }
  const ex = /Provided (?:further )?that[^.]*\./i.exec(text);
  if (ex) add("exception", ex[0], "", "remove the proviso");
  const sh = /\bshall\b/.exec(text);
  if (sh && !ex) add("exception", sh[0], "shall, except where specifically exempted by the Reserve Bank,", "add “except where …”");
  const ap = /with the prior approval of [^,.;]+/i.exec(text);
  if (ap) add("condition", ap[0], "", "remove the prior-approval condition");
  const rep = /[^.]*\b(?:report|submit)[^.]*\./i.exec(text);
  if (rep) add("reporting", rep[0], "", "remove the reporting line");
  return out;
}

export function EditLab({ api }: { api: ApiState }) {
  const b = useJson<Bases>("edit_bases.json").data;
  const active = presenter(api) && liveAvailable(api);
  if (!b) return <Loading />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2"><StatusBadge status="postpaper" /><StatusBadge status="unvalidated" />{!api.health?.model.mock && <StatusBadge status="live" />}</div>
      <p className="max-w-3xl text-[14.5px] leading-relaxed text-ink-2">
        The edit lab changes one value in the target paragraph (a frequency, a deadline, an amount, a percentage, an exception, an approval condition or a reporting line), previews the change, and re-runs the frozen comparator.
        Did it detect the edited field? Did the verdict change? Did anything else move?
      </p>
      <Card><CardBody className="space-y-1.5 text-[13.5px] text-ink-2">
        <p className="font-semibold text-ink">The control-run gate</p>
        <p>Step 1 always re-runs the <i>unedited</i> pair live. If that control does not reproduce the sealed result (any field status or the verdict), the page says “Control did not reproduce the sealed result — this edit cannot be interpreted” and the conclusion panel stays disabled.</p>
        <p className="text-ink-3">Exploratory. A formal minimal-pair sensitivity study would freeze the edit set before any run.</p>
      </CardBody></Card>
      {!active ? (
        <div className="space-y-2 text-[13.5px]">
          <p className="rounded-lg border border-line bg-panel-2 p-3 text-ink-2">
            Read-only here. Editing needs the full paragraph text and a live model, so it runs only in local / presenter mode. Whether live control runs reproduce the sealed outputs has not yet been established, so the edit lab is shipped as an explainer (see AUDIT.md).
          </p>
          <p className="font-medium">Curated base pairs ({b.bases.length}; {b.eligible.same} same and {b.eligible.different} different pairs are eligible):</p>
          <ul className="space-y-1">
            {b.bases.map((x) => <li key={x.unitId}><Link className="text-accent hover:underline" to={caseHref(x.unitId)}>{x.unitId}</Link> <span className="text-ink-3">· {VERDICT[x.verdict]} · editable: {x.kinds.map((k) => FIELD_LABEL[k as Field] ?? k).join(", ")}</span></li>)}
          </ul>
        </div>
      ) : <EditRunner bases={b.bases} mock={!!api.health?.model.mock} />}
    </div>
  );
}

function EditRunner({ bases, mock }: { bases: Bases["bases"]; mock: boolean }) {
  const [unitId, setUnitId] = useState(bases[0]?.unitId ?? null);
  const c = useCase(unitId);
  const base = bases.find((x) => x.unitId === unitId);
  const text = useFullText(base?.targetPid, true);
  const edits = useMemo(() => (text && base ? editsFor(text, base.targetPid) : []), [text, base]);
  const [pick, setPick] = useState<number | null>(null);
  const control = useLiveRun();
  const edited = useLiveRun();
  if (!c.data || !base) return <Loading />;
  const unit = c.data.unit;
  const e = pick != null ? edits[pick] : null;
  const ctrlDiff = control.run.phase === "done" ? diffWithSealed(unit, control.run.verdict) : null;
  const interpretable = ctrlDiff?.same === true;
  const editedRows = edited.run.verdict?.rows ?? [];
  const changed = edited.run.verdict ? editedRows.filter((r) => unit.comparator.rows.find((s) => s.field === r.field)?.status !== r.status) : [];
  const editedField = e?.kind === "amount" ? ["amount", "threshold"] : e ? [e.kind] : [];
  return (
    <div className="space-y-4">
      <label className="flex flex-col gap-1 text-[12.5px] text-ink-3">Base pair
        <select value={unitId ?? ""} onChange={(ev) => { setUnitId(ev.target.value); setPick(null); control.stop(); edited.stop(); }} className="h-9 rounded-md border border-line bg-panel px-2 text-[13.5px] text-ink">
          {bases.map((x) => <option key={x.unitId} value={x.unitId}>{x.unitId} ({x.verdict})</option>)}
        </select>
      </label>
      <div><p className="text-[13.5px] font-medium">Edit</p>
        <div className="mt-1 flex flex-wrap gap-2">{edits.map((x, i) => <Button key={i} size="sm" variant={pick === i ? "default" : "outline"} onClick={() => setPick(i)}>{FIELD_LABEL[x.kind as Field] ?? x.kind}: {x.label}</Button>)}</div>
        {text && edits.length === 0 && <p className="text-[13px] text-ink-3">No structured edit applies to this paragraph.</p>}
      </div>
      {e && text && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-2 text-[12.5px]">
          <span className="bg-neg-soft line-through">{e.from}</span>{e.to ? <> → <span className="bg-pos-soft">{e.to}</span></> : " (removed)"}
        </pre>
      )}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void control.start({ mode: "benchmark", unitId: unit.id })}><Play size={15} />1. Control run (unedited)</Button>
        <Button disabled={!e || control.run.phase !== "done"} onClick={() => e && void edited.start({ mode: "edit", unitId: unit.id, edits: [{ kind: e.kind, from: e.from, to: e.to }] })}><Play size={15} />2. Run the edited pair</Button>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <SealedPanel unit={unit} />
        <LivePanel run={control.run} unit={unit} mock={mock} />
        <LivePanel run={edited.run} unvalidated mock={mock} />
      </div>
      {control.run.phase === "done" && !interpretable && <p className="rounded-md border border-neg/40 bg-neg-soft p-3 text-[14px] font-semibold text-neg">Control did not reproduce the sealed result — this edit cannot be interpreted.</p>}
      <Card><CardBody className={interpretable && edited.run.phase === "done" ? "" : "opacity-50"} aria-disabled={!interpretable}>
        <p className="font-semibold">Conclusion {!interpretable && "(disabled until the control reproduces the sealed result)"}</p>
        {interpretable && edited.run.phase === "done" && edited.run.verdict && (
          <ul className="mt-1 list-disc pl-5 text-[13.5px] text-ink-2">
            <li>Edited field detected: {changed.some((r) => editedField.includes(r.field) && r.status !== "equal") ? "yes" : "no"}.</li>
            <li>Verdict changed: {edited.run.verdict.judgement !== unit.predictions.comparator.judgement ? `yes (${unit.predictions.comparator.judgement} → ${edited.run.verdict.judgement})` : "no"}.</li>
            <li>Other fields that changed: {changed.filter((r) => !editedField.includes(r.field)).map((r) => FIELD_LABEL[r.field as Field]).join(", ") || "none"}.</li>
          </ul>
        )}
      </CardBody></Card>
    </div>
  );
}

import { Fragment, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowDown, Check, ChevronDown, ExternalLink, Info, ShieldCheck, X } from "lucide-react";
import { Badge, Button, Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { checkFreshness, type ApiState, type Freshness, useFullText, presenter } from "../api";
import { PostPaper, StatusBadge, type Status } from "../badges";
import { useJson } from "../data";
import { bandTone, FEATURE_LABEL, FIELD_LABEL, pct0, STATUS_LABEL, SYSTEM_NAME, SYSTEM_SHORT, VERDICT, VERDICT_SHORT } from "../names";
import type { Field, FieldRow, FieldValue, Judgement, Pointer, Prediction, ResultsShard, SystemId, Unit } from "../types";

export const isWithheld = (v: FieldValue): v is { withheld: true } => typeof v === "object" && v !== null && "withheld" in v;

/** Where to find a field value in the displayed text: exact or whitespace/case-normalised string match only. */
export function locate(value: FieldValue, text: string | null | undefined): [number, number] | null {
  if (!text || typeof value !== "string") return null;
  const v = value.replace(/…$/, "").trim();
  if (v.length < 3) return null;
  const words = v.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const m = new RegExp(words.join("\\s+"), "i").exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

export function targetPid(u: Unit) {
  return u.comparator.decisivePid ?? u.shownCandidates[0] ?? null;
}

// ---- paragraph cards ---------------------------------------------------------------------------------------------

export function ParagraphCards({ unit, pointers, api, highlight, hidden }: {
  unit: Unit; pointers: Record<string, Pointer>; api: ApiState; highlight?: { source: FieldValue; target: FieldValue } | null; hidden?: boolean;
}) {
  const full = presenter(api);
  const tpid = targetPid(unit);
  const srcFull = useFullText(unit.sourcePid, full);
  const tgtFull = useFullText(tpid, full);
  const cards = [
    { side: "source" as const, cls: unit.sourceClass, pid: unit.sourcePid, p: pointers[unit.sourcePid], text: srcFull, hl: highlight?.source },
    { side: "target" as const, cls: unit.targetClass, pid: tpid, p: tpid ? pointers[tpid] : undefined, text: tgtFull, hl: highlight?.target },
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {cards.map((c) => {
        const shown = c.text ?? c.p?.excerpt ?? null;
        const at = c.hl !== undefined && c.hl !== null ? locate(c.hl, shown) : null;
        return (
          <article key={c.side} className="min-w-0 rounded-lg border border-line bg-panel p-4" aria-label={`${c.side === "source" ? "Source" : "Target"} paragraph`}>
            <p className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-3">{c.side === "source" ? "Source rule" : "Closest rule for"} · {c.cls}</p>
            {c.p ? (
              <>
                <p className={cn("mt-2 whitespace-pre-line break-words leading-relaxed", c.text ? "text-[14px]" : "text-[15.5px]")}>
                  {shown ? (at ? <>“{shown.slice(0, at[0])}<mark className="rounded bg-warn-soft px-0.5 text-ink">{shown.slice(at[0], at[1])}</mark>{shown.slice(at[1])}”</> : <>“{shown}”</>) : "…"}
                </p>
                {c.hl !== undefined && c.hl !== null && (
                  <p className="mt-1.5 text-[11.5px] text-ink-3">{at ? "Highlighted value located by string match." : "Value not located in the displayed text."}</p>
                )}
                {!hidden && (
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink-3">
                    {c.p.url && <a href={c.p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">Read the official text <ExternalLink size={12} /></a>}
                    <span className="font-mono text-[11px]">{c.pid}</span>
                    {!c.text && <span>{c.p.focused ? "Excerpt (12 words, at the obligation)" : "Excerpt (first 12 words)"}</span>}
                    {c.text && <span>Full text (presenter mode)</span>}
                  </p>
                )}
              </>
            ) : <p className="mt-2 text-[14px] text-ink-3">No counterpart paragraph.</p>}
          </article>
        );
      })}
    </div>
  );
}

// ---- predictions strip -------------------------------------------------------------------------------------------

export function PredictionChip({ id, p, gold, selected, onClick }: { id: SystemId; p: Prediction; gold: Judgement; selected?: boolean; onClick?: () => void }) {
  const answered = p.status === "answered" && p.judgement;
  const ok = answered && p.judgement === gold;
  const label = answered ? VERDICT_SHORT[p.judgement!] : p.status === "abstained" ? "Abstained" : p.status === "not_answered" ? "Not answered" : "Not released";
  const body = (
    <button type="button" onClick={onClick} aria-pressed={selected}
      aria-label={`${SYSTEM_NAME[id]}: ${label}${answered ? (ok ? ", correct" : ", wrong") : ""}`}
      className={cn("flex min-w-0 flex-col items-start rounded-lg border px-2.5 py-1.5 text-left transition-colors",
        selected ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-ink-3", id === "comparator" && "bg-panel-2")}>
      <span className="text-[11px] text-ink-3">{SYSTEM_SHORT[id]}</span>
      <span className="flex items-center gap-1 text-[13px] font-medium">
        {answered ? (ok ? <Check size={13} className="text-pos" aria-hidden /> : <X size={13} className="text-neg" aria-hidden />) : null}{label}
      </span>
      {answered && !ok && p.inContext === true && <span className="text-[10.5px] text-neg">gold paragraph was in context</span>}
      {p.retryUsed && <span className="text-[10.5px] text-ink-3">fact-checker retried</span>}
    </button>
  );
  return <Tip content={<span>{SYSTEM_NAME[id]} <span className="font-mono text-ink-3">({id})</span></span>}>{body}</Tip>;
}

export function PredictionsStrip({ unit, selected, onSelect }: { unit: Unit; selected?: SystemId | null; onSelect?: (s: SystemId) => void }) {
  const order: SystemId[] = ["p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context", "comparator"];
  return (
    <div className="flex flex-wrap items-stretch gap-2" role="group" aria-label="Every system's answer">
      {order.map((s) => <PredictionChip key={s} id={s} p={unit.predictions[s]} gold={unit.goldJudgement} selected={selected === s} onClick={() => onSelect?.(s)} />)}
      <div className="flex flex-col justify-center rounded-lg border-2 border-ink px-2.5 py-1.5" aria-label={`Expert verdict: ${VERDICT[unit.goldJudgement]}`}>
        <span className="text-[11px] text-ink-3">Expert (gold)</span>
        <span className="text-[13px] font-semibold">{VERDICT_SHORT[unit.goldJudgement]}</span>
      </div>
    </div>
  );
}

// ---- 13-field microscope -------------------------------------------------------------------------------------------

function Value({ v }: { v: FieldValue }) {
  if (v === null) return <span className="text-ink-3 italic">not extracted</span>;
  if (isWithheld(v)) return <Tip content="The public site shows at most 25 words of any RBI paragraph. Open in presenter mode to see the full value."><span className="cursor-help text-ink-3 italic underline decoration-dotted">value withheld — excerpt limit; open in presenter mode</span></Tip>;
  return <span className="break-words">“{v}”</span>;
}

const STATUS_TONE: Record<FieldRow["status"], string> = {
  equal: "border-line text-ink-2", differs: "border-warn/60 bg-warn-soft text-warn", only_source: "border-warn/60 bg-warn-soft text-warn",
  only_target: "border-warn/60 bg-warn-soft text-warn", absent: "border-transparent text-ink-3",
};

export function Microscope({ unit, selected, onSelect, compact }: { unit: Unit; selected?: Field | null; onSelect?: (f: Field | null) => void; compact?: boolean }) {
  const [showAbsent, setShowAbsent] = useState(!compact);
  if (!unit.comparator.parseOk) return <p className="text-[14px] text-ink-3">The comparator's output for this pair could not be read, so the fixed rule made no call (counted as an abstention).</p>;
  const rows = unit.comparator.rows.filter((r) => showAbsent || r.status !== "absent");
  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[640px] text-left text-[13px]">
          <caption className="sr-only">The 13 fields the model extracted from both paragraphs, and how they compare</caption>
          <thead className="bg-panel-2 text-[11.5px] uppercase tracking-wide text-ink-3">
            <tr><th scope="col" className="px-3 py-2">Field</th><th scope="col" className="px-3 py-2">{unit.sourceClass}</th><th scope="col" className="px-3 py-2">{unit.targetClass}</th><th scope="col" className="px-3 py-2">Status</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const sel = selected === r.field;
              return (
                <tr key={r.field} className={cn("border-t border-line align-top", onSelect && "cursor-pointer hover:bg-panel-2", sel && "bg-accent-soft/50")}
                  onClick={() => onSelect?.(sel ? null : r.field)} tabIndex={onSelect ? 0 : undefined}
                  onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(sel ? null : r.field); } }}
                  aria-selected={onSelect ? sel : undefined}>
                  <th scope="row" className="whitespace-nowrap px-3 py-2 font-medium">
                    {FIELD_LABEL[r.field]}
                    {r.material && <Tip content="Material field: a one-sided statement counts as a difference under the frozen rule."><span className="ml-1 cursor-help text-[10.5px] font-semibold text-accent">M</span></Tip>}
                    <span className="block font-mono text-[10.5px] font-normal text-ink-3">{r.field}</span>
                  </th>
                  <td className="max-w-[260px] px-3 py-2">{r.status === "absent" && r.sourceValue === null ? <span className="text-ink-3">—</span> : <Value v={r.sourceValue} />}</td>
                  <td className="max-w-[260px] px-3 py-2">{r.status === "absent" && r.targetValue === null ? <span className="text-ink-3">—</span> : <Value v={r.targetValue} />}</td>
                  <td className="px-3 py-2">
                    <span className={cn("inline-block whitespace-nowrap rounded border px-1.5 py-0.5 text-[11.5px] font-medium", STATUS_TONE[r.status])}>{STATUS_LABEL[r.status]}</span>
                    {r.note === "entity_name_by_construction" && <span className="mt-1 block text-[11.5px] text-ink-3">Entity name differs by construction.</span>}
                    {r.note === "extraction_anomaly" && <span className="mt-1 block text-[11.5px] text-neg">Extraction anomaly: “differs” with no value on either side.</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
        <span><span className="font-semibold text-accent">M</span> = material field</span>
        {onSelect && <span>Click a row to highlight its values in the paragraphs.</span>}
        {compact && <button type="button" className="text-accent hover:underline" onClick={() => setShowAbsent(!showAbsent)}>{showAbsent ? "Hide" : "Show"} fields absent on both sides</button>}
      </div>
    </div>
  );
}

// ---- decision trace --------------------------------------------------------------------------------------------------

export function DecisionTrace({ unit, ruleSha }: { unit: Unit; ruleSha: string }) {
  const dec = unit.comparator.decisivePid;
  const t = unit.comparator.trace;
  const final = t[t.length - 1];
  const rowsOf = (fields: Field[]) => unit.comparator.rows.filter((r) => fields.includes(r.field));
  const decisiveSteps = t.filter((s) => s.pid === dec && s.step !== "precedence same > different > none");
  const firing = decisiveSteps.find((s) => s.result === "fired");
  const lines: { text: string; material?: boolean }[] = [];
  if (!unit.comparator.parseOk) lines.push({ text: "model output could not be read" });
  else if (firing && firing.fields.length) {
    for (const r of rowsOf(firing.fields)) lines.push({ text: `${r.field} = ${STATUS_LABEL[r.status]}`, material: r.material });
  } else if (firing?.step === "addresses the same duty") {
    lines.push({ text: "addresses the same duty = no (both candidates)" });
  } else {
    lines.push({ text: "no field differs; no material field on one side only" });
  }
  const others = unit.comparator.rows.filter((r) => r.status === "equal" && ["deadline", "frequency", "threshold", "scope", "amount"].includes(r.field) && !lines.some((l) => l.text.startsWith(r.field)));
  for (const r of others.slice(0, 2)) lines.push({ text: `${r.field} = equal` });
  return (
    <figure className="rounded-lg border border-line bg-panel-2 p-4" aria-label="Decision trace">
      <pre className="overflow-x-auto font-mono text-[12.5px] leading-6 text-ink">
        {lines.map((l) => `${l.text}${l.material ? "  [material]" : ""}`).join("\n")}
      </pre>
      <ArrowDown size={16} className="my-1 ml-6 text-ink-3" aria-hidden />
      <p className="font-mono text-[12.5px]">
        fixed rule (sha {ruleSha.slice(0, 8)}…) → <b className={cn(final?.verdict === "different" ? "text-warn" : "text-ink")}>{final?.verdict === "abstain" ? "NO CALL" : (final?.verdict ?? "").toUpperCase()}</b>
      </p>
      <details className="mt-2 text-[12px] text-ink-2">
        <summary className="cursor-pointer text-ink-3">Every rule step (both candidates)</summary>
        <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-mono text-[11.5px]">
          {t.map((s, i) => <li key={i}>{s.pid ? `[${s.pid}] ` : ""}{s.step}{s.fields.length ? ` (${s.fields.join(", ")})` : ""}: {s.result}{s.verdict ? ` → ${s.verdict}` : ""}</li>)}
        </ol>
      </details>
      <figcaption className="mt-2 text-[12.5px] text-ink-2">The model only extracts the fields. This fixed rule, frozen before any test run, decides the verdict.</figcaption>
    </figure>
  );
}

// ---- confidence (B1) -----------------------------------------------------------------------------------------------

export function ConfidenceBlock({ unit, showDetails = true }: { unit: Unit; showDetails?: boolean }) {
  const r = useJson<ResultsShard>("results.json").data;
  const c = unit.confidence;
  const verdict = unit.predictions.comparator.judgement;
  const band = r?.confidence.bands.find((b) => b.band === c.band);
  const f = r?.confidence.differentFlags;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {verdict === "different" ? <Badge tone="warn" className="text-[12px]">Flagged for review</Badge>
          : <Badge tone={bandTone(c.band)} className="text-[12px]">{c.band === "Abstain" ? "No confidence (abstained)" : `${c.band} confidence`}</Badge>}
        <PostPaper />
      </div>
      {verdict === "different" ? (
        <p className="text-[13.5px] leading-relaxed text-ink-2">
          {f ? <>When the comparator flags a difference, the expert agreed {pct0(f.precision.k / f.precision.n)} of the time ({f.precision.k} of {f.precision.n}) and the comparator caught {pct0(f.recall.k / f.recall.n)} of all real differences ({f.recall.k} of {f.recall.n}). </> : null}
          Treat a flag as a reason to look, not a conclusion.
        </p>
      ) : band && band.accuracy != null ? (
        <p className="text-[13.5px] text-ink-2">On the 412 test comparisons, answers in the {c.band} band matched the expert {pct0(band.accuracy)} of the time ({band.correct} of {band.n}).</p>
      ) : <p className="text-[13.5px] text-ink-2">No confidence: the comparator made no call.</p>}
      {showDetails && c.contributions.length > 0 && <ConfidenceDetails unit={unit} />}
    </div>
  );
}

export function ConfidenceDetails({ unit, open }: { unit: Unit; open?: boolean }) {
  const c = unit.confidence;
  const max = Math.max(...c.contributions.map((x) => Math.abs(x.term)), 0.01);
  return (
    <details className="rounded-lg border border-line px-3 py-2 text-[13px]" open={open}>
      <summary className="flex cursor-pointer list-none items-center gap-1 font-medium [&::-webkit-details-marker]:hidden"><ChevronDown size={14} />Confidence details</summary>
      <div className="mt-2 space-y-2">
        <p className="text-ink-2">Model M2 (comparator-only), fitted on the separate 30-item development set and frozen before gold evaluation.
          Probability correct {c.p != null ? <b className="num text-ink">{c.p.toFixed(3)}</b> : "—"} → band <b>{c.band}</b> (High ≥ 0.85, Medium 0.60–0.85, Low &lt; 0.60).</p>
        <ul className="space-y-1" aria-label="Feature contributions (weight × standardised value)">
          {c.contributions.map((x) => (
            <li key={x.feature} className="grid grid-cols-[minmax(0,1fr)_120px_56px] items-center gap-2 sm:grid-cols-[minmax(0,240px)_1fr_56px]">
              <span className="truncate text-ink-2" title={`${x.feature}: value ${x.value}, z ${x.z.toFixed(2)}, weight ${x.weight.toFixed(3)}`}>{FEATURE_LABEL[x.feature] ?? x.feature} <span className="num text-ink-3">({x.value})</span></span>
              <span className="relative h-3 rounded bg-panel-2" aria-hidden>
                <span className={cn("absolute top-0 h-3 rounded", x.term >= 0 ? "left-1/2 bg-pos" : "right-1/2 bg-neg")} style={{ width: `${(Math.abs(x.term) / max) * 50}%` }} />
                <span className="absolute left-1/2 top-[-2px] h-4 w-px bg-ink-3" />
              </span>
              <span className="num text-right text-[12px]">{x.term >= 0 ? "+" : "−"}{Math.abs(x.term).toFixed(2)}</span>
            </li>
          ))}
        </ul>
        <p className="text-[12px] text-ink-3">Each bar is weight × standardised feature value (green raises, red lowers the probability). Intercept {c.intercept?.toFixed(2)}. The score is never rescaled after the test.</p>
      </div>
    </details>
  );
}

// ---- provenance drawer ---------------------------------------------------------------------------------------------

export function ProvenanceDrawer({ unit, pointers, api, status = "sealed" }: { unit: Unit; pointers: Record<string, Pointer>; api: ApiState; status?: Status }) {
  const [fresh, setFresh] = useState<Record<string, Freshness | "checking">>({});
  const tpid = targetPid(unit);
  const pv = unit.provenance;
  const rows = useMemo(() => [
    ["Gold route", unit.route], ["Gold flag (item)", unit.goldFlag],
    ["Model", `${pv.model} · temperature ${pv.temperature}`], ["Prompt sha256", pv.prompt_sha256], ["Rule sha256", pv.rule_sha256],
    ["Sealed output written", pv.sealed_written_utc], ["Confidence model", `${pv.confidence_model} · sha256 ${String(pv.confidence_model_sha256).slice(0, 16)}…`],
    ["Gold file sha256", pv.gold_sha256], ["Results file sha256", pv.results_sha256], ["Snapshot generated", pv.snapshot_generated_utc],
  ] as [string, unknown][], [unit, pv]);
  const canCheck = api.status === "ready";
  const run = async (pid: string) => { setFresh((f) => ({ ...f, [pid]: "checking" })); const r = await checkFreshness(pid); setFresh((f) => ({ ...f, [pid]: r })); };
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild><Button variant="outline"><ShieldCheck size={15} />Why can I trust this?</Button></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/40" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-[75] w-full max-w-lg overflow-y-auto border-l border-line bg-bg p-5 shadow-xl focus:outline-none">
          <div className="flex items-start justify-between gap-2">
            <Dialog.Title className="text-[18px] font-semibold">Why can I trust this?</Dialog.Title>
            <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Close"><X size={16} /></Button></Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-ink-2">Everything this case view shows, and where it comes from.</Dialog.Description>
          <div className="mt-3"><StatusBadge status={status} /></div>
          {[unit.sourcePid, tpid].filter(Boolean).map((pid) => {
            const p = pointers[pid!];
            const fr = fresh[pid!];
            return p ? (
              <section key={pid} className="mt-4 rounded-lg border border-line p-3 text-[12.5px]">
                <p className="font-semibold">{pid === unit.sourcePid ? `Source · ${unit.sourceClass}` : `Target · ${unit.targetClass}`}</p>
                <dl className="mt-1 grid grid-cols-[110px_minmax(0,1fr)] gap-x-2 gap-y-0.5 text-ink-2">
                  <dt>Paragraph</dt><dd className="break-all font-mono">{p.id}</dd>
                  <dt>Direction</dt><dd>{p.directionTitle}</dd>
                  <dt>Entity class</dt><dd>{p.entityClass}</dd>
                  <dt>Clause</dt><dd>{p.clausePath ?? "—"}</dd>
                  <dt>Source URL</dt><dd className="break-all">{p.url ? <a className="text-accent hover:underline" href={p.url} target="_blank" rel="noreferrer">{p.url}</a> : "—"}</dd>
                  <dt>Harvested</dt><dd>{p.harvestDate}</dd>
                  <dt>Paragraph sha256</dt><dd className="break-all font-mono">{p.sha256}</dd>
                </dl>
                {canCheck && (
                  <div className="mt-2">
                    <Button size="sm" variant="outline" onClick={() => void run(pid!)} disabled={fr === "checking"}>{fr === "checking" ? "Checking…" : "Check against RBI's current source"}</Button>
                    {fr && fr !== "checking" && <FreshnessNote f={fr} />}
                  </div>
                )}
              </section>
            ) : null;
          })}
          <section className="mt-4 text-[12.5px]">
            <dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-x-2 gap-y-1 text-ink-2">
              {rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd className="break-all font-mono text-[11.5px]">{String(v ?? "—")}</dd></Fragment>)}
            </dl>
          </section>
          <p className="mt-4 flex gap-1.5 text-[12px] text-ink-3"><Info size={14} className="shrink-0" />The public site shows at most 12 words of each paragraph (25 across all uses) and links to RBI's official PDF.</p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FreshnessNote({ f }: { f: Freshness }) {
  const text = f.outcome === "match"
    ? `The text at RBI's URL still hashes to the value in the benchmark (harvested ${f.harvestDate}).`
    : f.outcome === "differs"
      ? "The text at RBI's URL no longer matches the harvested hash. This can mean an amendment, a re-issued PDF or a formatting change; it is not by itself evidence that the rule changed."
      : `Could not verify${f.detail ? `: ${f.detail}` : ""}.`;
  const label = f.outcome === "match" ? "Matches benchmark snapshot" : f.outcome === "differs" ? "Source differs from benchmark snapshot" : "Could not verify";
  return <p className="mt-1.5 text-ink-2"><b>{label}.</b> {text} <span className="text-ink-3">(checked {f.checkedUtc.slice(0, 16).replace("T", " ")} UTC)</span></p>;
}

export function VerdictPill({ j, className }: { j: Judgement | "abstain" | undefined; className?: string }) {
  if (!j || j === "abstain") return <span className={cn("rounded-md bg-panel-2 px-2 py-0.5 text-[13px] font-semibold text-ink-2", className)}>No call</span>;
  return <span className={cn("rounded-md px-2 py-0.5 text-[13px] font-semibold", j === "different" ? "bg-warn-soft text-warn" : j === "same" ? "bg-pos-soft text-pos" : "bg-panel-2 text-ink-2", className)}>{VERDICT[j]}</span>;
}

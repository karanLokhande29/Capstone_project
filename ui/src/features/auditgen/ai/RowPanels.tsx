import { useMemo, useState } from "react";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { useAudit } from "../state";
import { live } from "../api";
import { SourceLink } from "../parts";
import type { ChangeRow, DiffRow, RegisterRow, ReviewStatus, Section } from "../types";
import { ai } from "./aiApi";
import { useAi } from "./aiState";
import { AiBadge, Err, Meta, RowPicker, RunButton, Sentences } from "./AiParts";
import type { DraftResult, ExplainResult, SuggestResult } from "./aiTypes";

const PART_LABEL: Record<string, string> = { summary: "In plain language", action: "What to do", who: "Who must act", deadline: "Deadline / frequency" };

function ExplainView({ r }: { r: ExplainResult }) {
  const parts = ["summary", "action", "who", "deadline"];
  return (
    <div className="space-y-2">
      {parts.map((p) => {
        const items = r.sentences.filter((s) => s.part === p);
        if (!items.length) return null;
        return <div key={p}><p className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-3">{PART_LABEL[p]}</p><Sentences items={items} /></div>;
      })}
      {r.sentences.length === 0 && <p className="text-[12.5px] text-ink-3">The model returned nothing usable.</p>}
      <p className="text-[12px] text-ink-3">Key quote {r.evidence_quote_found ? <Badge tone="pos">found in the paragraph</Badge> : <Badge tone="neg">not found in the paragraph</Badge>}
        {r.evidence_quote && <span className="ml-1 italic">“{r.evidence_quote}”</span>}</p>
      {r.rule_deadline && <p className="text-[12px] text-ink-3">Rule-based calendar extraction for this row: <b>{r.rule_deadline}</b></p>}
      <Meta r={r} />
    </div>
  );
}

const COVER_TONE = { covered: "pos", partial: "warn", missing: "neg" } as const;

function DraftView({ r }: { r: DraftResult }) {
  return (
    <div className="space-y-2">
      <p className="text-[13px] font-semibold">{r.title || "Draft clause"} {r.owner && <span className="font-normal text-ink-3">· owner: {r.owner}</span>}</p>
      <blockquote className="whitespace-pre-wrap rounded-md border-l-2 border-product bg-panel-2 p-2 text-[13px]">{r.clause || "(empty)"}</blockquote>
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span>Gap-analyser check of this draft:</span>
        <Badge tone={COVER_TONE[r.check.coverage]}>{r.check.coverage}</Badge>
        <span className="num text-ink-3">entailment {r.check.entailment.toFixed(2)} · cosine {r.check.cosine.toFixed(2)}</span>
        {r.stray_numbers.length > 0 && <Badge tone="neg">numbers not in the obligation: {r.stray_numbers.join(", ")}</Badge>}
      </div>
      {r.check.rule && <p className="text-[11px] text-ink-3">{r.check.rule}</p>}
      {r.notes && <p className="text-[12px] text-ink-2"><b>Reviewer notes:</b> {r.notes}</p>}
      <p className="text-[11.5px] text-warn">Draft wording for {r.company}. Legal and compliance review required before it enters any policy.</p>
      <Button size="sm" variant="outline" onClick={() => void navigator.clipboard?.writeText(r.clause)}>Copy clause</Button>
      <Meta r={r} />
    </div>
  );
}

const TO_STATUS: Record<string, ReviewStatus> = { confirm: "confirmed", dispute: "disputed", "not applicable": "not applicable" };

function SuggestView({ r, onApplied }: { r: SuggestResult; onApplied: () => void }) {
  const { mode, pack } = useAudit();
  const [who, setWho] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const status = TO_STATUS[r.suggestion];
  return (
    <div className="space-y-2">
      <p className="text-[13px]">Suggestion: <Badge tone={r.suggestion === "confirm" ? "pos" : r.suggestion === "dispute" ? "neg" : "outline"}>{r.suggestion}</Badge>
        {r.raw_suggestion !== r.suggestion && <span className="ml-1 text-[12px] text-ink-3">(the model said “{r.raw_suggestion}”, but no reason sentence was verified)</span>}</p>
      <Sentences items={r.sentences} empty="No verified reason." />
      {r.check && <p className="text-[12px] text-ink-2"><b>Check before deciding:</b> {r.check}</p>}
      <p className="text-[11.5px] text-ink-3">{r.note} Current status: {r.current_review_status}.</p>
      {status && mode === "live" && pack && !pack.signoff && (
        <form className="flex flex-wrap items-center gap-2 text-[12px]" onSubmit={async (e) => {
          e.preventDefault();
          if (!who.trim() || !r.row) return;
          try {
            await live.review(pack.pack_id, [{ section: r.section as Section, row_id: r.row.row_id, review_status: status, reviewer: who.trim(), note: "AI suggestion reviewed and accepted" }]);
            setMsg(`Marked ${status} by ${who.trim()}.`); onApplied();
          } catch (x) { setMsg((x as Error).message); }
        }}>
          <input aria-label="Reviewer name" placeholder="Your name" value={who} onChange={(e) => setWho(e.target.value)} className="h-7 rounded-md border border-line bg-panel px-2" />
          <Button size="sm" variant="outline" type="submit" disabled={!who.trim()}>I agree: mark {status}</Button>
          {msg && <span>{msg}</span>}
        </form>
      )}
      <Meta r={r} />
    </div>
  );
}

export function ObligationPanel() {
  const { pack, reload } = useAudit();
  const { store, run, model } = useAi();
  const [rid, setRid] = useState<string | null>(null);
  const [company, setCompany] = useState("the Company");
  const rows = useMemo(() => (pack?.register ?? []).filter((r) => !r.hidden), [pack]);
  const marks = useMemo(() => ({ ...(store.explain ?? {}), ...(store.draft ?? {}) }), [store]);
  const row = rows.find((r) => r.row_id === rid) ?? null;
  const ex = rid ? store.explain?.[rid] : undefined;
  const dr = rid ? store.draft?.[rid] : undefined;
  const sg = rid ? store.suggest?.[`register:${rid}`] : undefined;
  const text = (r: RegisterRow) => `${r.paragraph_id} · ${r.excerpt} · ${r.direction_title}`;
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <RowPicker rows={rows} text={text} label="obligations" value={rid} onPick={(r) => setRid(r.row_id)} marks={marks} />
      {!row ? <p className="text-[12.5px] text-ink-3">Pick an obligation to explain it in plain language, draft a policy clause for it, or get a review suggestion.</p> : (
        <div className="space-y-3">
          <Card><CardBody className="space-y-1 text-[12.5px]">
            <p className="font-semibold">{row.direction_title}</p>
            <p>{row.excerpt}</p>
            <p className="text-ink-3"><SourceLink row={row} /> · {row.status} · {row.applies_to}{row.deadline_frequency ? ` · ${row.deadline_frequency}` : ""}</p>
          </CardBody></Card>
          <Card><CardBody className="space-y-2">
            <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">Explain in plain language</p><AiBadge />
              <span className="ml-auto"><RunButton k={`explain:${row.row_id}`} onClick={() => void run(`explain:${row.row_id}`, () => ai.explain(pack!.pack_id, row.row_id, model),
                (s, r) => ({ ...s, explain: { ...(s.explain ?? {}), [row.row_id]: r } }))}>{ex ? "Explain again" : "Explain"}</RunButton></span></div>
            <Err k={`explain:${row.row_id}`} />
            {ex && <ExplainView r={ex} />}
          </CardBody></Card>
          <Card><CardBody className="space-y-2">
            <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">Draft a policy clause</p><AiBadge />
              <input aria-label="Company name" value={company} onChange={(e) => setCompany(e.target.value)} className="h-7 w-44 rounded-md border border-line bg-panel px-2 text-[12px]" />
              <span className="ml-auto"><RunButton k={`draft:${row.row_id}`} onClick={() => void run(`draft:${row.row_id}`, () => ai.draft(pack!.pack_id, row.row_id, "register", company, model),
                (s, r) => ({ ...s, draft: { ...(s.draft ?? {}), [row.row_id]: r } }))}>{dr ? "Draft again" : "Draft clause"}</RunButton></span></div>
            <p className="text-[11.5px] text-ink-3">Uses only the RBI text. The draft is then scored by the gap analyser's own covered / partial / missing rule.</p>
            <Err k={`draft:${row.row_id}`} />
            {dr && <DraftView r={dr} />}
          </CardBody></Card>
          <Card><CardBody className="space-y-2">
            <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">Review suggestion</p><AiBadge />
              <span className="ml-auto"><RunButton k={`suggest:${row.row_id}`} onClick={() => void run(`suggest:${row.row_id}`, () => ai.suggest(pack!.pack_id, "register", row.row_id, model),
                (s, r) => ({ ...s, suggest: { ...(s.suggest ?? {}), [`register:${row.row_id}`]: r } }))}>{sg ? "Suggest again" : "Suggest"}</RunButton></span></div>
            <Err k={`suggest:${row.row_id}`} />
            {sg && <SuggestView r={sg} onApplied={() => void reload()} />}
          </CardBody></Card>
        </div>
      )}
    </div>
  );
}

export function ChangesPanel() {
  const { pack } = useAudit();
  const { store, run, model } = useAi();
  const [rid, setRid] = useState<string | null>(null);
  const rows = useMemo(() => pack?.changes ?? [], [pack]);
  const row = rows.find((r) => r.row_id === rid) ?? null;
  const res = rid ? store.change?.[rid] : undefined;
  const text = (r: ChangeRow) => `${r.change} · ${r.paragraph_id ?? r.md_id} · ${r.effective ?? ""} · ${r.direction_title}`;
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <RowPicker rows={rows} text={text} label="changes" value={rid} onPick={(r) => setRid(r.row_id)} marks={store.change} />
      {!row ? <p className="text-[12.5px] text-ink-3">Pick a change to see what the amendment did to the paragraph and what it means for the entity.</p> : (
        <Card><CardBody className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="warn">{row.change}</Badge><p className="text-[13px] font-semibold">{row.direction_title}</p><AiBadge />
            <span className="ml-auto"><RunButton k={`change:${row.row_id}`} onClick={() => void run(`change:${row.row_id}`, () => ai.change(pack!.pack_id, row.row_id, model),
              (s, r) => ({ ...s, change: { ...(s.change ?? {}), [row.row_id]: r } }))}>{res ? "Explain again" : "Explain change"}</RunButton></span>
          </div>
          <p className="text-[12px] text-ink-3"><SourceLink row={row} /> · governing instrument <a className="text-accent" href={row.governing_url} target="_blank" rel="noreferrer">{row.governing_instrument}</a> · effective {row.effective ?? "unknown"}</p>
          <Err k={`change:${row.row_id}`} />
          {res && (
            <div className="space-y-2">
              {res.note && <p className="rounded-md bg-warn-soft p-2 text-[12.5px] text-warn">{res.note}</p>}
              {(res.before_excerpt || res.after_excerpt) && (
                <div className="grid gap-2 md:grid-cols-2 text-[12px]">
                  <div className="rounded-md border border-line p-2"><p className="mb-1 text-[11px] font-semibold uppercase text-ink-3">Before</p>{res.before_excerpt}</div>
                  <div className="rounded-md border border-line p-2"><p className="mb-1 text-[11px] font-semibold uppercase text-ink-3">Amendment text</p>{res.after_excerpt ?? "(deleted, or not available)"}</div>
                </div>
              )}
              {["what_changed", "impact"].map((p) => {
                const items = res.sentences.filter((s) => s.part === p);
                return items.length ? <div key={p}><p className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-3">{p === "impact" ? "Impact" : "What changed"}</p><Sentences items={items} /></div> : null;
              })}
              <Meta r={res} />
            </div>
          )}
        </CardBody></Card>
      )}
    </div>
  );
}

export function DiffPanel() {
  const { pack } = useAudit();
  const { store, run, model } = useAi();
  const [rid, setRid] = useState<string | null>(null);
  const rows = useMemo(() => (pack?.differential ?? []).filter((r) => r.counterpart_paragraph_id), [pack]);
  const row = rows.find((r) => r.row_id === rid) ?? null;
  const res = rid ? store.diff?.[rid] : undefined;
  const text = (r: DiffRow) => `${r.differential} · ${r.paragraph_id} → ${r.target_class} · ${r.excerpt ?? ""}`;
  if (!pack?.differential?.length) return <p className="text-[12.5px] text-ink-3">This pack has no cross-class differential (the profile has no group classes).</p>;
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <RowPicker rows={rows} text={text} label="matched pairs" value={rid} onPick={(r) => setRid(r.row_id)} marks={store.diff} />
      {!row ? <p className="text-[12.5px] text-ink-3">Pick a matched pair for a field-by-field second opinion (actor, deadline, threshold, …), decided by the frozen comparator rule.</p> : (
        <Card><CardBody className="space-y-2">
          <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">{row.source_class} → {row.target_class}</p><Badge tone="outline">pack: {row.differential}</Badge><AiBadge />
            <span className="ml-auto"><RunButton k={`diff:${row.row_id}`} onClick={() => void run(`diff:${row.row_id}`, () => ai.diff(pack.pack_id, row.row_id, model),
              (s, r) => ({ ...s, diff: { ...(s.diff ?? {}), [row.row_id]: r } }))}>{res ? "Compare again" : "Second opinion"}</RunButton></span></div>
          <div className="grid gap-2 text-[12px] md:grid-cols-2">
            <div className="rounded-md border border-line p-2"><SourceLink row={row} /><p className="mt-1">{row.excerpt}</p></div>
            <div className="rounded-md border border-line p-2">{row.counterpart_url && <a className="text-accent" href={row.counterpart_url} target="_blank" rel="noreferrer">{row.counterpart_paragraph_id}</a>}<p className="mt-1">{row.counterpart_excerpt}</p></div>
          </div>
          <Err k={`diff:${row.row_id}`} />
          {res && (
            <div className="space-y-2">
              <p className="text-[13px]">AI field comparison → rule verdict: <Badge tone={res.judgement === "same" ? "pos" : res.judgement === "different" ? "neg" : "outline"}>{res.judgement}</Badge> <span className="text-[11px] text-ink-3">({res.rule})</span></p>
              <p className="rounded-md bg-warn-soft p-2 text-[12px] text-warn">{res.caution}</p>
              {Object.keys(res.field_comparison).length > 0 && (
                <div className="flex flex-wrap gap-1 text-[11px]">{Object.entries(res.field_comparison).map(([f, v]) => (
                  <Badge key={f} tone={v === "equal" ? "pos" : v === "differs" ? "neg" : v === "absent" || !v ? "neutral" : "warn"}>{f}: {v ?? "?"}</Badge>))}</div>
              )}
              {res.differences.length > 0 && (
                <table className="w-full text-[12px]"><thead className="text-ink-3"><tr><th className="text-left">Field</th><th className="text-left">Source</th><th className="text-left">Target</th></tr></thead>
                  <tbody>{res.differences.map((d, i) => (
                    <tr key={i} className="border-t border-line align-top"><td className="pr-2">{d.field}</td>
                      <td className="pr-2">{d.source} {!d.source_found && d.source && <Badge tone="neg">not quoted</Badge>}</td>
                      <td>{d.target} {!d.target_found && d.target && <Badge tone="neg">not quoted</Badge>}</td></tr>))}</tbody></table>
              )}
              {res.note && <p className="text-[12px] text-ink-3">{res.note}</p>}
              <Meta r={res} />
            </div>
          )}
        </CardBody></Card>
      )}
    </div>
  );
}

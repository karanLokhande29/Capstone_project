import { useEffect, useState } from "react";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { useAudit } from "../state";
import { Stat } from "../parts";
import { ai } from "./aiApi";
import { useAi } from "./aiState";
import { AiBadge, Err, Meta, RunButton, Sentences, SourceChip } from "./AiParts";
import type { ActivityRow } from "./aiTypes";

const PRI_TONE = { high: "neg", medium: "warn", low: "outline" } as const;

export function BriefingPanel() {
  const { mode, pack } = useAudit();
  const { store, run, model } = useAi();
  const [facts, setFacts] = useState(false);
  const memo = store.memo;
  const plan = store.plan;
  if (!pack) return null;
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      <Card><CardBody className="space-y-2">
        <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">Executive memo</p><AiBadge />
          <span className="ml-auto flex gap-2">
            {memo && mode === "live" && <a className="inline-flex h-7 items-center rounded-md border border-line px-2 text-xs text-accent" href={ai.memoDocxUrl(pack.pack_id)} download>Download DOCX</a>}
            <RunButton k="memo" onClick={() => void run("memo", () => ai.memo(pack.pack_id, model), (s, r) => ({ ...s, memo: r }))}>{memo ? "Redraft" : "Draft memo"}</RunButton>
          </span></div>
        <p className="text-[11.5px] text-ink-3">Drafted from numbered facts taken from this pack. Every number in a sentence must appear in the facts it cites; anything else is held back as unverified.</p>
        <Err k="memo" />
        {memo && (
          <div className="space-y-2">
            <p className="text-[13.5px] font-semibold">{memo.subject}</p>
            {memo.sections.map((s, i) => s.sentences.length ? (
              <div key={i}><p className="text-[11.5px] font-semibold uppercase tracking-wide text-ink-3">{s.heading}</p><Sentences items={s.sentences} /></div>
            ) : null)}
            <button className="text-[12px] text-accent hover:underline" onClick={() => setFacts(!facts)}>{facts ? "Hide" : "Show"} the {memo.facts.length} facts given to the model</button>
            {facts && <ol className="space-y-0.5 rounded-md border border-line bg-panel-2 p-2 text-[11.5px]">{memo.facts.map((f) => <li key={f.id}><b>{f.id}</b> {f.text}</li>)}</ol>}
            <Meta r={memo} />
          </div>
        )}
      </CardBody></Card>
      <Card><CardBody className="space-y-2">
        <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">Action plan</p><AiBadge />
          <span className="ml-auto"><RunButton k="plan" onClick={() => void run("plan", () => ai.plan(pack.pack_id, model), (s, r) => ({ ...s, plan: r }))}>{plan ? "Re-plan" : "Build action plan"}</RunButton></span></div>
        <p className="text-[11.5px] text-ink-3">Each action must point at one deadline, change or gap row of this pack, and may not add dates or figures. Actions that break a rule are held back.</p>
        <Err k="plan" />
        {plan?.note && <p className="text-[12.5px] text-ink-3">{plan.note}</p>}
        {plan && plan.items.length > 0 && (
          <ol className="space-y-1.5">
            {plan.items.filter((x) => x.verified).map((x, i) => (
              <li key={i} className="rounded-md border border-line p-2 text-[12.5px]">
                <div className="flex flex-wrap items-center gap-2"><Badge tone={PRI_TONE[x.priority]}>{x.priority}</Badge><b>{x.text}</b></div>
                {x.why && <p className="text-ink-2">{x.why}</p>}
                <p className="text-[11.5px] text-ink-3">{x.item}: {x.fact} {x.url && <a className="text-accent" href={x.url} target="_blank" rel="noreferrer">source</a>}</p>
              </li>
            ))}
            {plan.items.some((x) => !x.verified) && <li className="text-[12px] text-ink-3">{plan.items.filter((x) => !x.verified).length} action(s) held back: {plan.items.filter((x) => !x.verified).map((x) => x.reason).join("; ")}</li>}
          </ol>
        )}
        {plan && <Meta r={plan} />}
      </CardBody></Card>
    </div>
  );
}

export function CalendarPanel() {
  const { pack } = useAudit();
  const { store, run, model } = useAi();
  const res = store.calendar;
  if (!pack) return null;
  const verify = (pack.calendar ?? []).filter((e) => e.verify).length;
  return (
    <div className="space-y-3">
      <Card><CardBody className="space-y-2">
        <div className="flex flex-wrap items-center gap-2"><p className="text-[13px] font-semibold">AI check of the compliance calendar</p><AiBadge />
          <span className="ml-auto"><RunButton k="calendar" disabled={!verify} onClick={() => void run("calendar", () => ai.calendar(pack.pack_id, null, model), (s, r) => ({ ...s, calendar: r }))}>
            {res ? "Check again" : `Check the ${Math.min(verify, 25)} “verify” entries`}</RunButton></span></div>
        <p className="text-[12px] text-ink-3">The rule-based extractor marks {verify} of {pack.calendar.length} entries “verify”. The local model reads each source paragraph, extracts the deadline or frequency as structured data, and must quote the words it used; the quote is checked against the paragraph.</p>
        <Err k="calendar" />
      </CardBody></Card>
      {res && (
        <>
          <div className="grid gap-2 md:grid-cols-4">
            <Stat label="Entries checked" value={res.results.length} />
            <Stat label="AI agrees with rule" value={res.agreement.rate == null ? "–" : `${res.agreement.agree} / ${res.agreement.n}`} tone="pos" />
            <Stat label="Quote found in source" value={res.results.filter((r) => r.ai.quote_found).length} />
            <Stat label="AI says no deadline" value={res.results.filter((r) => r.ai.kind === "none").length} tone="warn" />
          </div>
          <p className="text-[11.5px] text-ink-3">{res.note}</p>
          <div className="overflow-x-auto rounded-lg border border-line bg-panel">
            <table className="w-full text-left text-[12px]" aria-label="AI calendar check">
              <thead className="bg-panel-2 text-ink-3"><tr><th className="px-2 py-1">Source</th><th className="px-2 py-1">Rule</th><th className="px-2 py-1">AI</th><th className="px-2 py-1">Quote</th><th className="px-2 py-1">Agree</th></tr></thead>
              <tbody>{res.results.map((r) => (
                <tr key={r.entry_id} className="border-t border-line align-top">
                  <td className="px-2 py-1"><SourceChip s={r} /><p className="text-ink-3">{r.summary}</p></td>
                  <td className="px-2 py-1">{r.rule?.kind}{r.rule?.frequency ? ` · ${r.rule.frequency}` : ""}{r.rule?.offset_days ? ` · ${r.rule.offset_days}d` : ""}</td>
                  <td className="px-2 py-1">{r.ai.kind}{r.ai.frequency ? ` · ${r.ai.frequency}` : ""}{r.ai.offset_days ? ` · ${r.ai.offset_days}d` : ""}{r.ai.trigger ? ` · after ${r.ai.trigger}` : ""}
                    {r.ai.what && <p className="text-ink-3">{r.ai.what}</p>}</td>
                  <td className="px-2 py-1"><span className="italic">{r.ai.quote}</span> {r.ai.quote_found ? <Badge tone="pos">found</Badge> : <Badge tone="neg">not found</Badge>}</td>
                  <td className="px-2 py-1">{r.agrees_with_rule == null ? "–" : r.agrees_with_rule ? <Badge tone="pos">yes</Badge> : <Badge tone="warn">no</Badge>}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <Meta r={res} />
        </>
      )}
    </div>
  );
}

export function ActivityPanel() {
  const { mode } = useAudit();
  const { status, store } = useAi();
  const [rows, setRows] = useState<ActivityRow[]>([]);
  useEffect(() => { if (mode === "live") void ai.activity().then(setRows).catch(() => setRows([])); }, [mode, store]);
  return (
    <div className="space-y-3">
      <Card><CardBody className="space-y-1 text-[12.5px]">
        <p className="font-semibold">How the AI features work</p>
        <ul className="list-disc space-y-0.5 pl-5 text-ink-2">
          <li><b>Local model only:</b> {status?.model ?? "a local Ollama model"} on {status?.host ?? "127.0.0.1"}. The backend refuses any non-loopback model host. No Gemini, Groq or other remote API.</li>
          <li><b>Inputs:</b> RBI paragraphs from the local corpus and this pack's own rows. These features never send an uploaded company policy to the model.</li>
          <li><b>Verifier:</b> every answer sentence is checked by the NLI cross-encoder ({status?.verifier ?? "nli-deberta-v3-xsmall"}) against the RBI text it cites; numbers must appear in the source. Unverified sentences are hidden by default.</li>
          <li><b>Never settled:</b> outputs are drafts. A review suggestion changes nothing until a named person applies it.</li>
          <li><b>Log:</b> each call is logged with feature, model, timing, counts and sha256 hashes. Questions, prompts and answers are not logged.</li>
        </ul>
      </CardBody></Card>
      {mode !== "live" ? <p className="text-[12.5px] text-ink-3">The activity log needs the local backend.</p> : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-left text-[12px]" aria-label="AI activity log">
            <thead className="bg-panel-2 text-ink-3"><tr>{["Time (UTC)", "Pack", "Feature", "Row", "Model", "Seconds", "Verified", "Unverified", "Input sha256"].map((h) => <th key={h} className="px-2 py-1">{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-2 py-1">{r.utc.replace("T", " ").slice(0, 19)}</td><td className="px-2 py-1">{r.pack_id}</td><td className="px-2 py-1">{r.feature}{r.abstained ? " (abstained)" : ""}</td>
                  <td className="px-2 py-1">{r.key ?? "–"}</td><td className="px-2 py-1">{r.model ?? "–"}</td><td className="num px-2 py-1">{r.seconds ?? "–"}</td>
                  <td className="num px-2 py-1">{r.verified}</td><td className="num px-2 py-1">{r.unverified}</td><td className="px-2 py-1 font-mono text-[10.5px]">{r.input_sha256?.slice(0, 16)}…</td>
                </tr>))}
              {rows.length === 0 && <tr><td colSpan={9} className="px-2 py-3 text-center text-ink-3">No AI calls yet.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

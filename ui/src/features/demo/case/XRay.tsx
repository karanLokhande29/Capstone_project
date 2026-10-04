import { SYSTEM_NAME } from "../names";
import type { Pointer, SystemId, Unit } from "../types";

/** "How this system saw it": only what the run logs record for this one system. Never a combined pipeline. */
export function XRay({ unit, system, pointers }: { unit: Unit; system: SystemId; pointers: Record<string, Pointer> }) {
  const p = unit.predictions[system];
  const log = unit.xray?.[system];
  const gold = unit.goldMatchedPid;
  if (system === "p2002_candidates") {
    return (
      <Panel title={SYSTEM_NAME[system]}>
        <p>An embedding baseline: it proposes the two most similar paragraphs in the target class (shown to the expert) and calls them <i>same</i> when they are close enough, otherwise <i>no match</i>. It cannot output <i>different</i>.</p>
        <Ids ids={unit.shownCandidates} gold={gold} matched={null} pointers={pointers} />
      </Panel>
    );
  }
  if (system === "long_context") {
    return (
      <Panel title={SYSTEM_NAME[system]}>
        <p>Context: every relevant Direction for the item, capped at 100K tokens; no search step. {p.inContext === true ? "The gold paragraph was inside that context." : p.inContext === false ? "The gold paragraph did not fit in the context." : "The item was never answered (input too long)."}</p>
        <Answer unit={unit} system={system} />
      </Panel>
    );
  }
  if (!log || !log.attempts.length) return <Panel title={SYSTEM_NAME[system]}><p>No run log is available for this system on this case; the X-Ray is hidden.</p></Panel>;
  return (
    <Panel title={SYSTEM_NAME[system]}>
      <p className="text-ink-3">Recorded settings: institution filter {log.classFilter ? "on" : "off"} · fact-checker {log.verifier ? "on" : "off"} · date check {typeof log.temporalFilter === "string" ? log.temporalFilter : log.temporalFilter ? "on" : "off"}.
        The keyword, meaning-based and merge stages were not logged per case, so only the final context is shown.</p>
      {log.attempts.map((a) => (
        <div key={a.attempt} className="mt-2">
          <p className="font-medium">Attempt {a.attempt}: context given to the model{a.pooled ? " (one pooled list for all classes)" : ""}</p>
          <Ids ids={a.shown} gold={gold} matched={p.matchedPid ?? null} pointers={pointers} />
          {a.retryRequested && <p className="mt-1 text-warn">The fact-checker could not back the answer for this class and asked for a retry.</p>}
          {a.parseProblems && <p className="mt-1 text-neg">The model's answer could not be read on this attempt.</p>}
        </div>
      ))}
      <Answer unit={unit} system={system} />
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-3 rounded-lg border border-line bg-panel p-4 text-[13px] leading-relaxed text-ink-2" aria-label={`How ${title} saw this case`}>
      <h3 className="mb-1 text-[14px] font-semibold text-ink">How this system saw it · {title}</h3>{children}
    </section>
  );
}

function Ids({ ids, gold, matched, pointers }: { ids: string[]; gold: string | null; matched: string | null; pointers: Record<string, Pointer> }) {
  return (
    <ol className="mt-1 flex flex-wrap gap-1.5">
      {ids.map((id, i) => (
        <li key={id} className={`rounded border px-1.5 py-0.5 font-mono text-[11.5px] ${id === gold ? "border-pos bg-pos-soft text-pos" : "border-line"}`}>
          {i + 1}. {pointers[id]?.url ? <a href={pointers[id].url!} target="_blank" rel="noreferrer" className="hover:underline">{id}</a> : id}
          {id === gold && " · gold counterpart"}{id === matched && " · model's match"}
        </li>
      ))}
    </ol>
  );
}

function Answer({ unit, system }: { unit: Unit; system: SystemId }) {
  const p = unit.predictions[system];
  const txt = p.status === "answered" ? `answered “${p.judgement}”` : p.status === "abstained" ? "declined to answer (abstained)" : "never answered";
  return <p className="mt-2"><b className="text-ink">Final:</b> {txt}{p.matchedPid ? `, matched ${p.matchedPid}` : ""}. Expert: “{unit.goldJudgement}”. The model's free-text rationale is not shown.</p>;
}

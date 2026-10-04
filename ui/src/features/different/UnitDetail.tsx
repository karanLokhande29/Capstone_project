import { useData } from "@/data/store";
import { unitConfidence } from "@/data/confidence";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { CaveatChips } from "@/components/CaveatChip";
import { Pointer } from "@/components/Pointer";
import { Badge } from "@/components/ui/primitives";
import { SYSTEM_ORDER, cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  equal: "text-ink-3", differs: "bg-warn-soft text-warn font-medium", only_source: "bg-neg-soft text-neg", only_target: "bg-neg-soft text-neg", absent: "text-ink-3",
};

export function JudgementPill({ j, gold }: { j: string; gold?: string }) {
  const tone = j === gold ? "pos" : j === "abstain" || j === "unanswered" ? "neutral" : "neg";
  return <Badge tone={gold ? tone : "outline"}>{j}</Badge>;
}

/** The unit drawer body: source vs compared class, gold pointer, every system's answer, the comparator's 13 fields, its decision path, confidence. */
export function UnitDetail({ unitId }: { unitId: string }) {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const u = d.unitById.get(unitId);
  if (!u) return <p className="text-sm text-ink-3">Unit not in the snapshot.</p>;
  const it = d.itemById.get(u.itemId)!;
  const cf = s.comparatorFields[u.id];
  const cmp = u.predictions.comparator;
  const m2 = unitConfidence(model, u.id, "M2");
  const m1 = unitConfidence(model, u.id, "M1");
  return (
    <div className="space-y-4 text-sm">
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-md border border-line p-2">
          <p className="text-[11px] uppercase tracking-wide text-ink-3">Source class</p>
          <p className="font-medium">{it.sourceClass}</p>
          <Pointer pid={it.sourcePid} />
        </div>
        <div className="rounded-md border border-line p-2">
          <p className="text-[11px] uppercase tracking-wide text-ink-3">Compared class</p>
          <p className="font-medium">{u.classId}</p>
          <p className="mt-1">Gold: <Badge tone="accent">{u.goldJudgement}</Badge></p>
          {u.goldMatchedPid ? <Pointer pid={u.goldMatchedPid} label="gold counterpart" /> : <p className="text-xs text-ink-3">no gold counterpart (none)</p>}
        </div>
      </div>

      <section>
        <h4 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Every system's answer</h4>
        <table className="w-full text-[12.5px]">
          <thead><tr className="text-left text-ink-3"><th className="py-1 font-normal">System</th><th className="font-normal">Judgement</th><th className="font-normal">Gold paragraph in context?</th></tr></thead>
          <tbody>
            {SYSTEM_ORDER.filter((x) => u.predictions[x]).map((x) => {
              const p = u.predictions[x];
              return (
                <tr key={x} className="border-t border-line">
                  <td className="py-1">{d.systemName(x)}</td>
                  <td><JudgementPill j={p.judgement} gold={u.goldJudgement} /></td>
                  <td className="text-ink-3">{p.inContext === undefined || p.inContext === null ? "—" : p.inContext ? `yes${p.failure ? ` (${p.failure} failure)` : ""}` : `no${p.failure ? ` (${p.failure} failure)` : ""}`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {u.goldJudgement === "different" && <p className="mt-1 text-xs text-ink-3">Missed by every LLM system: definition A {u.missedA ? "yes" : "no"} · definition B {u.missedB ? "yes" : "no"}.</p>}
      </section>

      <section>
        <h4 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Comparator confidence</h4>
        <div className="flex flex-wrap gap-2">
          <ConfidenceBadge c={m2} />
          <span className="text-[11px] text-ink-3">Research view (cross-validated on gold):</span>
          <ConfidenceBadge c={m1} compact />
        </div>
      </section>

      <section>
        <h4 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Comparator: 13-field side-by-side</h4>
        {!cf || !cf.parseOk ? (
          <p className="text-xs text-ink-3">The comparator output for this unit could not be parsed, so the rule returned <b>unsure</b> (Abstain).</p>
        ) : (
          <>
            <p className="mb-1 text-xs text-ink-3">Decisive candidate {cf.decisivePid}; addresses the same duty: {cf.addressesSameDuty ? "yes" : "no"}.
              Values are trimmed to the 25-words-per-paragraph budget; differing fields are shown first. Material fields are marked •.</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-[12px]">
                <thead><tr className="text-left text-ink-3"><th className="py-1 font-normal">Field</th><th className="font-normal">Source</th><th className="font-normal">Candidate</th><th className="font-normal">Status</th></tr></thead>
                <tbody>
                  {cf.rows.map((r) => (
                    <tr key={r.field} className={cn("border-t border-line", r.status !== "equal" && r.status !== "absent" && "bg-warn-soft/40")}>
                      <td className="py-1 pr-2">{r.material && "• "}{r.field}</td>
                      <td className="pr-2">{r.sourceValue ?? (r.sourcePresent ? <span className="text-ink-3">(present, over budget)</span> : <span className="text-ink-3">—</span>)}</td>
                      <td className="pr-2">{r.targetValue ?? (r.targetPresent ? <span className="text-ink-3">(present, over budget)</span> : <span className="text-ink-3">—</span>)}</td>
                      <td><span className={cn("rounded px-1", STATUS_TONE[r.status])}>{r.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section>
        <h4 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Rule decision path (comparator-rule-v1, frozen)</h4>
        <ol className="space-y-1 text-[12.5px]">
          {(cf?.perCandidate ?? []).map((c) => (
            <li key={c.pid}>Candidate <code>{c.pid}</code>: {c.addressesSameDuty === false ? "does not address the same duty → none" : `verdict ${c.verdict}`}</li>
          ))}
          <li>Precedence <b>same &gt; different &gt; none</b> → class verdict <JudgementPill j={cmp.judgement} gold={u.goldJudgement} />
            {cf?.hinge && <span className="ml-1 text-warn">(decided by a single differing field)</span>}</li>
        </ol>
      </section>
      <CaveatChips ids={["single_expert", "candidates_shown", "scoring_asymmetry"]} />
    </div>
  );
}

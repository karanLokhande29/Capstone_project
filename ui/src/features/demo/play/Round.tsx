import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, X } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import type { ApiState } from "../api";
import { caseHref } from "../data";
import { FIELD_LABEL, LLM_SYSTEMS, SYSTEM_SHORT, VERDICT } from "../names";
import type { Judgement, Pointer, Unit } from "../types";
import { isWithheld, ParagraphCards } from "../case/parts";

export const CHOICES: { j: Judgement; label: string }[] = [
  { j: "same", label: "Same requirement" },
  { j: "different", label: "Different requirement" },
  { j: "none", label: "No matching rule" },
];

/** Mount with key={unit.id}: a new unit starts a new round. Reveal order (presentation pacing only, not a liveness claim): you → expert → each system → comparator → decisive fields. */
const STEP_MS = 450;

export function Round({ unit, pointers, api, onGuess, guess: initial, compact }: {
  unit: Unit; pointers: Record<string, Pointer>; api: ApiState; onGuess?: (j: Judgement) => void; guess?: Judgement | null; compact?: boolean;
}) {
  const [guess, setGuess] = useState<Judgement | null>(initial ?? null);
  const [shown, setShown] = useState(initial ? 99 : 0);
  useEffect(() => {
    if (!guess || shown >= 9) return;
    const t = setTimeout(() => setShown((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [guess, shown]);
  const pick = (j: Judgement) => { if (guess) return; setGuess(j); setShown(1); onGuess?.(j); };

  return (
    <div className="space-y-4">
      <ParagraphCards unit={unit} pointers={pointers} api={api} hidden={!guess} />
      {!guess ? (
        <div>
          <p className="mb-2 text-[14px] font-medium">Your call: for {unit.targetClass}, is this…</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Your answer">
            {CHOICES.map((c) => <Button key={c.j} variant="outline" className="h-10 px-4 text-[14px]" onClick={() => pick(c.j)}>{c.label}</Button>)}
          </div>
          {!compact && <p className="mt-2 text-[12px] text-ink-3">The public site shows short excerpts. Use “Read the official text” after you answer to see the whole paragraph.</p>}
        </div>
      ) : <Reveal unit={unit} guess={guess} shown={shown} />}
    </div>
  );
}

function Reveal({ unit, guess, shown }: { unit: Unit; guess: Judgement; shown: number }) {
  const gold = unit.goldJudgement;
  const cmp = unit.predictions.comparator;
  const decisive = unit.comparator.rows.filter((r) => r.status !== "equal" && r.status !== "absent" && (r.material || r.status === "differs"))
    .sort((a, b) => Number(b.material) - Number(a.material));
  const steps = [
    <Line key="you" ok={guess === gold} who="You" what={VERDICT[guess]} />,
    <Line key="gold" who="Expert" what={VERDICT[gold]} strong />,
    <div key="sys" className="flex flex-wrap gap-1.5">
      {LLM_SYSTEMS.map((s) => {
        const p = unit.predictions[s];
        const ok = p.status === "answered" && p.judgement === gold;
        const label = p.status === "answered" ? VERDICT[p.judgement!] : p.status === "abstained" ? "Abstained" : "Not answered";
        return <span key={s} className={cn("rounded-md border px-2 py-1 text-[12.5px]", ok ? "border-pos/50 bg-pos-soft" : "border-line")}>{SYSTEM_SHORT[s]}: <b>{label}</b> {ok ? <Check size={12} className="inline text-pos" aria-label="correct" /> : <X size={12} className="inline text-neg" aria-label="wrong" />}</span>;
      })}
    </div>,
    <Line key="cmp" ok={cmp.judgement === gold} who="Structured comparator" what={cmp.judgement ? VERDICT[cmp.judgement] : "No call"} />,
    decisive.length ? (
      <div key="fields" className="rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-[13.5px]">
        <b>What the comparator saw differ:</b>{" "}
        {decisive.slice(0, 3).map((r, i) => (
          <span key={r.field}>{i > 0 && "; "}<b>{FIELD_LABEL[r.field]}</b>
            {typeof r.sourceValue === "string" || typeof r.targetValue === "string" ? <> (“{typeof r.sourceValue === "string" ? r.sourceValue : isWithheld(r.sourceValue) ? "withheld" : "not stated"}” vs “{typeof r.targetValue === "string" ? r.targetValue : isWithheld(r.targetValue) ? "withheld" : "not stated"}”)</> : null}
            {r.note === "entity_name_by_construction" && <i> (entity name, by construction)</i>}</span>
        ))}
      </div>
    ) : <p key="fields" className="text-[13px] text-ink-2">The comparator found no differing field here.</p>,
    <Link key="open" to={caseHref(unit.id)} className="inline-flex items-center gap-1 text-[14px] font-medium text-accent hover:underline">Open in Microscope <ArrowRight size={14} /></Link>,
  ];
  return <div className="space-y-2" aria-live="polite">{steps.slice(0, Math.min(shown, steps.length))}</div>;
}

function Line({ who, what, ok, strong }: { who: string; what: string; ok?: boolean; strong?: boolean }) {
  return (
    <p className={cn("flex items-center gap-2 text-[14.5px]", strong && "font-semibold")}>
      <span className="w-44 shrink-0 text-ink-2">{who}</span>
      <span>{what}</span>
      {ok !== undefined && (ok ? <Check size={15} className="text-pos" aria-label="matches the expert" /> : <X size={15} className="text-neg" aria-label="differs from the expert" />)}
    </p>
  );
}

/** Score over rounds played only. "Best single AI system" = best of the five LLM systems over the same rounds. */
export function score(rounds: { unit: Unit; guess: Judgement }[]) {
  const you = rounds.filter((r) => r.guess === r.unit.goldJudgement).length;
  const per = LLM_SYSTEMS.map((s) => ({ s, k: rounds.filter((r) => r.unit.predictions[s].judgement === r.unit.goldJudgement).length }));
  const best = per.reduce((a, b) => (b.k > a.k ? b : a), per[0]);
  const cmp = rounds.filter((r) => r.unit.predictions.comparator.judgement === r.unit.goldJudgement).length;
  return { n: rounds.length, you, best: best.k, bestSystem: best.s, cmp };
}

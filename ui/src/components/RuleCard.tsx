import type { RuleOutput } from "@/intelligence/rules";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  supported: "border-pos/40 bg-pos-soft", ok: "border-pos/40 bg-pos-soft", warn: "border-warn/40 bg-warn-soft", fail: "border-neg/40 bg-neg-soft",
  block: "border-neg/40 bg-neg-soft", unclear: "border-warn/40 bg-warn-soft", missing: "border-neg/40 bg-neg-soft", info: "border-line bg-panel-2",
};
const MARK: Record<string, string> = { supported: "supported ✓", ok: "ok ✓", warn: "⚠ check wording", fail: "✗", block: "blocked", unclear: "? unclear", missing: "missing", info: "info" };

/** Renders a rule output: rule id, reason, evidence refs and verdict. */
export function RuleCard({ r, className }: { r: RuleOutput; className?: string }) {
  return (
    <div className={cn("min-w-0 break-words rounded-md border px-3 py-2 text-[12.5px]", TONE[r.verdict], className)}>
      <p className="font-semibold">{r.title} ({r.rule}) <span className="ml-1 font-normal text-ink-2">· {MARK[r.verdict]}</span></p>
      {"sentence" in r.inputs && <p className="mt-0.5 italic text-ink-2">“{String(r.inputs.sentence).slice(0, 260)}”</p>}
      <p className="mt-1">{r.reason}</p>
      {r.suggestion && <p className="mt-1 text-ink-2">Suggested: {r.suggestion}</p>}
      {r.sourceRefs.filter(Boolean).length > 0 && <p className="mt-1 text-[11px] text-ink-3">Source: {r.sourceRefs.filter(Boolean).map((s) => <code key={s} className="mr-1 break-all">{s}</code>)}</p>}
    </div>
  );
}

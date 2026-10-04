import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Circle, Minus, Star, X } from "lucide-react";
import { Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { caseHref, useIndex } from "../data";
import { Loading, LoadError, PageHead } from "../DemoLayout";
import { useCaseNav } from "../case/CaseView";
import { LLM_SYSTEMS, SYSTEM_NAME, SYSTEM_SHORT } from "../names";
import type { IndexUnit, SystemId } from "../types";
import { CasesNav } from "./CasesNav";

const COLS: SystemId[] = ["p2002_candidates", ...LLM_SYSTEMS, "comparator"];
type Cell = "caught" | "reasoning" | "retrieval" | "abstained" | "not_answered" | "na";
type Sort = "groups" | "src" | "topic";

export function cellOf(u: IndexUnit, s: SystemId): Cell {
  if (s === "p2002_candidates") return "na";
  const j = u.sys[s];
  if (j === "different") return "caught";
  if (j === "abstained") return "abstained";
  if (j === "not_answered") return "not_answered";
  return u.inCtx[s] === false ? "retrieval" : "reasoning";
}

const CELL: Record<Cell, { label: string; cls: string; icon: React.ReactNode }> = {
  caught: { label: "caught the difference", cls: "bg-pos text-white dark:text-black", icon: <Check size={13} strokeWidth={3} /> },
  reasoning: { label: "wrong, gold paragraph was in context (reasoning failure)", cls: "bg-neg text-white dark:text-black", icon: <X size={13} strokeWidth={3} /> },
  retrieval: { label: "wrong, gold paragraph not in context (retrieval implicated)", cls: "hatch text-neg border border-neg", icon: <X size={13} strokeWidth={3} /> },
  abstained: { label: "abstained", cls: "bg-ink-3/35 text-ink", icon: <Minus size={13} strokeWidth={3} /> },
  not_answered: { label: "never answered (input too long)", cls: "border border-dashed border-ink-3 text-ink-3", icon: <Circle size={9} /> },
  na: { label: "cannot output “different” (embedding baseline)", cls: "bg-panel-2 text-ink-3 opacity-60", icon: <span className="text-[10px]">n/a</span> },
};

export default function FailureMap() {
  const idx = useIndex();
  const setNav = useCaseNav((s) => s.set);
  const [sort, setSort] = useState<Sort>("groups");
  const [why, setWhy] = useState(false);
  const units = useMemo(() => (idx.data?.units ?? []).filter((u) => u.gold === "different"), [idx.data]);
  const recovered = (u: IndexUnit) => u.missedA && u.sys.comparator === "different";
  const missedAll = (u: IndexUnit) => [...LLM_SYSTEMS, "comparator" as SystemId].every((s) => u.sys[s] !== "different");
  const group = (u: IndexUnit) => (recovered(u) ? 0 : missedAll(u) ? 1 : 2);
  const rows = useMemo(() => {
    let r = [...units];
    if (why) r = r.filter((u) => u.sys.comparator === "none");
    return r.sort((a, b) => sort === "groups" ? group(a) - group(b) || a.id.localeCompare(b.id)
      : sort === "src" ? a.src.localeCompare(b.src) || a.id.localeCompare(b.id) : (a.topic ?? "").localeCompare(b.topic ?? "") || a.id.localeCompare(b.id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [units, sort, why]);
  if (idx.error) return <LoadError error={idx.error} />;
  if (!idx.data) return <Loading what="the failure map" />;

  const nMissedA = units.filter((u) => u.missedA).length;
  const nRecovered = units.filter(recovered).length;
  const err = Object.fromEntries(COLS.map((s) => [s, units.filter((u) => ["reasoning", "retrieval", "abstained"].includes(cellOf(u, s))).length])) as Record<SystemId, number>;
  const llmErr = LLM_SYSTEMS.reduce((a, s) => a + err[s], 0);
  const llmInCtx = LLM_SYSTEMS.reduce((a, s) => a + units.filter((u) => cellOf(u, s) === "reasoning" || (cellOf(u, s) === "abstained" && u.inCtx[s] === true)).length, 0);
  const cmpNone = units.filter((u) => u.sys.comparator === "none");
  const bothNotSame = cmpNone.filter((u) => u.sameDuty.length > 0 && u.sameDuty.every((x) => x === false)).length;

  return (
    <div>
      <PageHead eyebrow="Cases · Failure Map" title="Where do the models fail on the 78 real differences?">
        {nMissedA} differences no LLM system caught · the comparator recovered {nRecovered} · in {llmInCtx} of {llmErr} LLM errors ({Math.round((llmInCtx / llmErr) * 100)}%) the right paragraph was already in context.
      </PageHead>
      <CasesNav />
      <div className="mt-4 flex flex-wrap items-center gap-3 text-[13px]">
        <label className="flex items-center gap-2">Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="h-8 rounded-md border border-line bg-panel px-2">
            <option value="groups">Recovered → missed by all → others</option><option value="src">Source class</option><option value="topic">Topic</option>
          </select>
        </label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={why} onChange={(e) => setWhy(e.target.checked)} />Why the comparator misses</label>
      </div>
      {why && (
        <div className="mt-3 rounded-lg border border-line bg-panel p-3 text-[13.5px] text-ink-2">
          The comparator answered <i>no matching rule</i> on {cmpNone.length} real differences. In {bothNotSame} of them it judged that <b>neither</b> shown paragraph addresses the same duty
          ({cmpNone.length - bothNotSame} other).
          {bothNotSame / Math.max(1, cmpNone.length) > 0.5 && <> In most remaining misses the model decided the two paragraphs were not about the same duty — topic matching, not field extraction, is the next bottleneck.</>}
        </div>
      )}
      <Legend />
      <div className="mt-3 overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[620px] border-collapse text-[12.5px]" aria-label="Failure map: rows are real differences, columns are systems">
          <thead className="sticky top-0 bg-panel-2">
            <tr>
              <th scope="col" className="px-2 py-2 text-left font-medium">Case ({rows.length})</th>
              {COLS.map((s) => (
                <th key={s} scope="col" className={cn("px-1 py-2 text-center font-medium", s === "p2002_candidates" && "text-ink-3")}>
                  <Tip content={<span>{SYSTEM_NAME[s]} <span className="font-mono">({s})</span></span>}><span className="cursor-help">{SYSTEM_SHORT[s]}</span></Tip>
                  {s !== "p2002_candidates" && <span className="block text-[10.5px] font-normal text-ink-3">{err[s]} errors</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={cn("border-t border-line", u.missedA && "border-l-4 border-l-warn")}>
                <th scope="row" className="max-w-[220px] px-2 py-1 text-left font-normal">
                  <Link to={caseHref(u.id)} onClick={() => setNav(rows.map((r) => r.id), "the Failure Map")} className="block truncate hover:underline" title={`${u.src} → ${u.tgt} · ${u.topic}`}>
                    {recovered(u) && <Star size={11} className="mr-1 inline fill-accent text-accent" aria-label="recovered by the comparator" />}
                    {u.src} → {u.tgt}
                  </Link>
                  <span className="block truncate text-[10.5px] text-ink-3">{u.topic}</span>
                </th>
                {COLS.map((s) => {
                  const c = cellOf(u, s);
                  const m = CELL[c];
                  const cell = <span className={cn("mx-auto grid h-6 w-6 place-items-center rounded", m.cls)} aria-hidden>{m.icon}</span>;
                  return (
                    <td key={s} className="px-1 py-1 text-center">
                      {c === "na" ? <span title={m.label}>{cell}<span className="sr-only">{m.label}</span></span> : (
                        <Link to={caseHref(u.id, s)} onClick={() => setNav(rows.map((r) => r.id), "the Failure Map")} aria-label={`${SYSTEM_NAME[s]} on ${u.src} → ${u.tgt}: ${m.label}`} title={m.label}
                          className="inline-block rounded focus-visible:outline-2 focus-visible:outline-accent">{cell}</Link>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-ink-3">Left border = one of the {nMissedA} differences every LLM system missed (all five answered, none said “different”). Star = the comparator recovers it. “In context” = the expert's matching paragraph was among the paragraphs the system was given.</p>
    </div>
  );
}

function Legend() {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-ink-2" aria-label="Legend">
      {(Object.keys(CELL) as Cell[]).map((c) => (
        <li key={c} className="flex items-center gap-1.5"><span className={cn("grid h-5 w-5 place-items-center rounded", CELL[c].cls)} aria-hidden>{CELL[c].icon}</span>{CELL[c].label}</li>
      ))}
    </ul>
  );
}

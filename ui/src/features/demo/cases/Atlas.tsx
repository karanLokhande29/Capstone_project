import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { Card, CardBody } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { useJson } from "../data";
import { Loading, LoadError, PageHead } from "../DemoLayout";
import type { MatrixShard } from "../types";
import { CasesNav } from "./CasesNav";

const ABBR: Record<string, string> = {
  "All India Financial Institutions": "AIFI", "Asset Reconstruction Companies": "ARC", "Commercial Banks": "CB", "Credit Information Companies": "CIC",
  "Local Area Banks": "LAB", "Non-Banking Financial Companies": "NBFC", "Payments Banks": "PB", "Regional Rural Banks": "RRB",
  "Rural Co-operative Banks": "RCB", "Small Finance Banks": "SFB", "Urban Co-operative Banks": "UCB",
};

export default function Atlas() {
  const m = useJson<MatrixShard>("matrix.json");
  const [sel, setSel] = useState<{ c: string; f: string } | null>(null);
  const [second, setSecond] = useState("");
  const [first, setFirst] = useState("");
  const cell = useMemo(() => new Map((m.data?.cells ?? []).map((c) => [`${c.classId}|${c.familyId}`, c])), [m.data]);
  if (m.error) return <LoadError error={m.error} />;
  if (!m.data) return <Loading what="the atlas" />;
  const { classes, families } = m.data;
  const populated = m.data.cells.filter((c) => c.populated).length;
  const ambiguous = m.data.cells.filter((c) => c.ambiguous).length;
  const maxT1 = Math.max(...m.data.cells.map((c) => c.t1Items.length), 1);
  const shared = (f: string) => !!first && !!second && cell.get(`${first}|${f}`)?.populated && cell.get(`${second}|${f}`)?.populated;
  const s = sel ? cell.get(`${sel.c}|${sel.f}`) : null;
  return (
    <div>
      <PageHead eyebrow="Cases · Atlas" title="Which institution types have a Direction on which topic?">
        {classes.length} regulated institution types × {families.length} topics. Filled = at least one Direction ({populated} cells; the full matrix also has 2 populated cells under an RBI function heading, 296 in all).
        Darker = more benchmark obligations drawn from that cell. ⚠ marks the {ambiguous} cells whose class or topic mapping is ambiguous.
      </PageHead>
      <CasesNav />
      <div className="mt-4 flex flex-wrap gap-3 text-[13px]">
        <label className="flex items-center gap-2">Compare <select value={first} onChange={(e) => setFirst(e.target.value)} className="h-8 rounded-md border border-line bg-panel px-2"><option value="">—</option>{classes.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label className="flex items-center gap-2">with <select value={second} onChange={(e) => setSecond(e.target.value)} className="h-8 rounded-md border border-line bg-panel px-2"><option value="">—</option>{classes.map((c) => <option key={c}>{c}</option>)}</select></label>
        {first && second && <span className="text-ink-2">{families.filter(shared).length} topics with parallel Directions (outlined)</span>}
      </div>
      <div className="mt-3 overflow-x-auto rounded-lg border border-line">
        <table className="border-collapse text-[11px]" aria-label="Institution type by topic matrix">
          <thead><tr><th className="sticky left-0 bg-panel-2 px-2 text-left">Topic</th>{classes.map((c) => <th key={c} scope="col" className="bg-panel-2 px-1 py-1 font-medium" title={c}>{ABBR[c] ?? c}</th>)}</tr></thead>
          <tbody>
            {families.map((f) => (
              <tr key={f} className={cn(shared(f) && "outline outline-2 -outline-offset-2 outline-accent")}>
                <th scope="row" className="sticky left-0 max-w-[220px] truncate bg-bg px-2 py-0.5 text-left font-normal" title={f}>{f}</th>
                {classes.map((c) => {
                  const x = cell.get(`${c}|${f}`);
                  const on = !!x?.populated;
                  const shade = x ? x.t1Items.length / maxT1 : 0;
                  return (
                    <td key={c} className="p-0.5">
                      <button type="button" disabled={!on} onClick={() => setSel({ c, f })} aria-label={`${c}, ${f}: ${on ? `${x!.directionIds.length} Directions, ${x!.t1Items.length} benchmark obligations` : "no Direction"}${x?.ambiguous ? ", ambiguous" : ""}`}
                        className={cn("grid h-5 w-8 place-items-center rounded-sm text-[9px]", on ? "cursor-pointer" : "bg-panel-2/60", sel?.c === c && sel?.f === f && "ring-2 ring-ink")}
                        style={on ? { background: `color-mix(in oklab, var(--accent) ${18 + shade * 72}%, var(--panel))` } : undefined}>
                        {x?.ambiguous ? "⚠" : x?.t1Items.length ? x.t1Items.length : ""}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {s && sel && (
        <Card className="mt-4"><CardBody className="space-y-2 text-[13.5px]">
          <p className="font-semibold">{sel.c} · {sel.f}{s.ambiguous && <span className="ml-2 text-warn">⚠ ambiguous{s.ambiguityReason ? `: ${s.ambiguityReason}` : ""}</span>}</p>
          <ul className="space-y-1">{s.directionIds.map((d) => <li key={d}>{m.data!.directions[d]?.url ? <a className="text-accent hover:underline" href={m.data!.directions[d].url!} target="_blank" rel="noreferrer">{m.data!.directions[d]?.title || d} <ExternalLink size={11} className="inline" /></a> : (m.data!.directions[d]?.title || d)}</li>)}</ul>
          {s.t1Items.length > 0 && <p>Benchmark obligations from this cell: {s.t1Items.map((i) => <Link key={i} className="mr-2 font-mono text-[12px] text-accent hover:underline" to={`/cases?q=${encodeURIComponent(i.replace("t1_", ""))}`}>{i}</Link>)}</p>}
        </CardBody></Card>
      )}
    </div>
  );
}

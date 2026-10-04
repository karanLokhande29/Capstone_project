import { useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download } from "lucide-react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Button, Card, CardBody, Tip } from "@/components/ui/primitives";
import { Num } from "@/components/Provenance";
import { CaveatChips } from "@/components/CaveatChip";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { unitConfidence } from "@/data/confidence";
import { exportPng, exportSvg } from "@/lib/export";
import { ARTIFACT } from "@/lib/env";
import { resolveKey } from "@/lib/keys";
import { cn, LLM5 } from "@/lib/utils";

const SYSTEMS = [...LLM5, "comparator"];
const CELL: Record<string, { cls: string; mark: string; label: string }> = {
  different: { cls: "bg-pos text-white dark:text-black", mark: "✓", label: "✓ different (correct)" },
  same: { cls: "bg-neg-soft text-neg", mark: "S", label: "→ same" },
  none: { cls: "bg-warn-soft text-warn", mark: "N", label: "→ none" },
  abstain: { cls: "bg-panel-2 text-ink-3", mark: "A", label: "abstain" },
  unanswered: { cls: "border border-dashed border-line text-ink-3", mark: "·", label: "unanswered (over cap)" },
};
const DEF = {
  A: "Definition A: every LLM system answered the item, and none said `different`.",
  B: "Definition B: only the systems that answered are counted (including items long-context never answered).",
};

function FieldHeatmap() {
  const s = useData((st) => st.snapshot)!;
  const ref = useRef<SVGSVGElement>(null);
  const fields = s.comparatorFields[Object.keys(s.comparatorFields)[0]]?.rows.map((r) => r.field) ?? [];
  const groups = [
    { id: "tp", label: "said different, gold different", filter: (g: string, p: string) => p === "different" && g === "different" },
    { id: "fp", label: "said different, gold same/none", filter: (g: string, p: string) => p === "different" && g !== "different" },
    { id: "fn", label: "gold different, said same", filter: (g: string, p: string) => g === "different" && p === "same" },
  ];
  const counts = groups.map((gr) => {
    const units = s.classUnits.filter((u) => gr.filter(u.goldJudgement, u.predictions.comparator.judgement) && s.comparatorFields[u.id]?.parseOk);
    return { ...gr, n: units.length, by: fields.map((f) => units.filter((u) => ["differs", "only_source", "only_target"].includes(s.comparatorFields[u.id].rows.find((r) => r.field === f)?.status ?? "")).length) };
  });
  const W = 760, lw = 230, cw = (W - lw - 10) / Math.max(1, fields.length), rh = 26, H = 40 + counts.length * rh;
  return (
    <div>
      <div className="mb-1 flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => exportSvg(ref.current, "comparator_field_heatmap")}><Download size={13} />{ARTIFACT ? "Copy SVG" : "SVG"}</Button>
        {!ARTIFACT && <Button variant="ghost" size="sm" onClick={() => exportPng(ref.current, "comparator_field_heatmap")}><Download size={13} />PNG</Button>}</div>
      <div className="overflow-x-auto">
        <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[640px]" role="img" aria-label="Comparator field heatmap">
          {fields.map((f, j) => <text key={f} x={lw + j * cw + cw / 2} y={28} fontSize={10} textAnchor="middle" fill="var(--ink-3)" transform={`rotate(-20 ${lw + j * cw + cw / 2} 28)`}>{f}</text>)}
          {counts.map((g, i) => (
            <g key={g.id}>
              <text x={4} y={40 + i * rh + 17} fontSize={11} fill="var(--ink)">{g.label} (n={g.n})</text>
              {g.by.map((c, j) => {
                const share = g.n ? c / g.n : 0;
                return (
                  <g key={j}>
                    <title>{`${fields[j]}: ${c}/${g.n} units have this field differing or one-sided`}</title>
                    <rect x={lw + j * cw + 1} y={40 + i * rh + 2} width={cw - 2} height={rh - 4} rx={3} fill="var(--accent)" opacity={0.08 + share * 0.9} />
                    <text x={lw + j * cw + cw / 2} y={40 + i * rh + 17} fontSize={10} textAnchor="middle" fill="var(--ink)">{c}</text>
                  </g>
                );
              })}
            </g>
          ))}
        </svg>
      </div>
      <p className="text-[12px] text-ink-3">Counts of units whose decisive candidate has the field differing or stated on one side only (gold v1, comparator units with a parsed output). Darker = larger share of the row.</p>
    </div>
  );
}

export default function DifferentExplorer() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const open = useDrawer((st) => st.open);
  const [sp, setSp] = useSearchParams();
  const def = (sp.get("def") === "B" ? "B" : "A") as "A" | "B";
  const missedOnly = sp.get("missed") === "1";
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }); };
  const units = useMemo(() => s.classUnits.filter((u) => u.goldJudgement === "different"), [s.classUnits]);
  const shown = units.filter((u) => !missedOnly || (def === "A" ? u.missedA : u.missedB));
  const missedCount = units.filter((u) => (def === "A" ? u.missedA : u.missedB)).length;
  const recovered = units.filter((u) => (def === "A" ? u.missedA : u.missedB) && u.predictions.comparator.judgement === "different").length;
  const rr = resolveKey(s.results, "phase4.retrieval_vs_reasoning.per_system") as Record<string, { errors: number; failure_types: Record<string, number> }>;
  const chart = SYSTEMS.map((x) => ({ system: d.systemName(x).replace(" (class filter + verifier)", "").replace(" LLM", "").replace(" (100K cap)", ""),
    retrieval: rr[x]?.failure_types.retrieval ?? 0, reasoning: rr[x]?.failure_types.reasoning ?? 0 }));

  return (
    <div>
      <PageHeader title="`different` Failure Explorer" tier="MUST"
        subtitle={<>The core failure: gold <code>different</code> class units ({units.length}), every system's answer, and why it failed. Click a row for the 13-field comparator diff and its rule path.</>} />
      <div className="mb-3 flex flex-wrap items-center gap-3 text-[12.5px]">
        <div className="inline-flex overflow-hidden rounded-md border border-line">
          {(["A", "B"] as const).map((k) => <button key={k} type="button" onClick={() => set("def", k)} className={cn("cursor-pointer px-3 py-1", def === k ? "bg-accent text-white dark:text-black" : "bg-panel")}>Definition {k}</button>)}
        </div>
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={missedOnly} onChange={(e) => set("missed", e.target.checked ? "1" : "0")} />Only units missed by every LLM system</label>
        <CaveatChips ids={["single_expert", "candidates_shown"]} />
      </div>
      <Card className="mb-3"><CardBody className="text-[13px]">
        <p className="italic text-ink-2">{DEF[def]}</p>
        <p className="mt-1">Missed by every LLM system: <b><Num value={missedCount} sourceKey={`phase4.missed_by_every_llm_system.${def === "A" ? "A_all_five_answered" : "B_answered_only"}.missed`} /></b> of{" "}
          <Num value={units.length} sourceKey="phase4.missed_by_every_llm_system.gold_different_units" />. The comparator gets{" "}
          <b><Num value={recovered} sourceKey={`phase4.missed_by_every_llm_system.${def === "A" ? "A_all_five_answered" : "B_answered_only"}.comparator_correct`} /></b> of them right.</p>
      </CardBody></Card>

      <Card><CardBody className="overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-[12px]">
          <thead><tr className="border-b border-line text-left text-ink-3">
            <th className="px-3 py-2 font-normal">Source class → compared class</th>
            {SYSTEMS.map((x) => <th key={x} className="px-1 text-center font-normal">{d.systemName(x).split(" ")[0]}{x === "ablation_a" ? "+ver." : x === "final_agentic" ? " ag." : ""}</th>)}
            <th className="font-normal">Confidence (M2)</th></tr></thead>
          <tbody>
            {shown.map((u) => {
              const it = d.itemById.get(u.itemId)!;
              return (
                <tr key={u.id} className="cursor-pointer border-b border-line hover:bg-panel-2" onClick={() => open(`unit:${u.id}`)}>
                  <td className="px-3 py-1.5"><span className="text-ink-2">{it.sourceClass}</span> → <b>{u.classId}</b>
                    {(def === "A" ? u.missedA : u.missedB) && <Badge tone="neg" className="ml-1">missed by all</Badge>}</td>
                  {SYSTEMS.map((x) => {
                    const p = u.predictions[x];
                    const c = CELL[p.judgement] ?? CELL.abstain;
                    return (
                      <td key={x} className="px-1 text-center">
                        <Tip content={<span>{d.systemName(x)}: {c.label}{p.failure ? ` · ${p.failure} failure` : ""}</span>}>
                          <span className={cn("inline-grid h-5 w-6 place-items-center rounded text-[10.5px] font-semibold", c.cls)}>{c.mark}</span>
                        </Tip>
                      </td>
                    );
                  })}
                  <td className="pr-2" onClick={(e) => e.stopPropagation()}><ConfidenceBadge c={unitConfidence(model, u.id, "M2")} compact /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody></Card>
      <div className="mt-2 flex flex-wrap gap-3 text-[11.5px] text-ink-3">{Object.values(CELL).map((c) => <span key={c.label} className="inline-flex items-center gap-1"><span className={cn("inline-grid h-4 w-5 place-items-center rounded text-[10px] font-semibold", c.cls)}>{c.mark}</span>{c.label}</span>)}</div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Retrieval vs reasoning (errors on the 78 units)">
          <Card><CardBody>
            <div className="h-64"><ResponsiveContainer>
              <BarChart data={chart} margin={{ left: -16, right: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="system" tick={{ fontSize: 10, fill: "var(--ink-3)" }} interval={0} />
                <YAxis tick={{ fontSize: 10, fill: "var(--ink-3)" }} />
                <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="reasoning" stackId="a" fill="var(--warn)" name="reasoning (gold paragraph in context)" />
                <Bar dataKey="retrieval" stackId="a" fill="var(--neutral)" name="retrieval (gold paragraph not in context)" />
              </BarChart>
            </ResponsiveContainer></div>
            <p className="text-[12px] text-ink-3">Source <code>phase4.retrieval_vs_reasoning.per_system</code>. The comparator has 0 retrieval failures by design: its context is the two shown candidates, which contain the gold paragraph. The human error-category pass was not done (G-04).</p>
          </CardBody></Card>
        </Section>
        <Section title="Comparator field heatmap: which fields decide `different`">
          <Card><CardBody><FieldHeatmap /></CardBody></Card>
        </Section>
      </div>
    </div>
  );
}

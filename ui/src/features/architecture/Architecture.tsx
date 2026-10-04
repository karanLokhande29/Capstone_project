import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { CICell } from "@/components/CICell";
import { CaveatChips } from "@/components/CaveatChip";

interface Comp { id: string; label: string; x: number; y: number; kind?: "input" | "product" | "verdict"; systems: string[]; ablation?: string; effect?: string[]; detail: string }

const COMPS: Comp[] = [
  { id: "query", label: "Query + target class + as-of date", x: 0, y: 140, kind: "input", systems: [], detail: "A source obligation (T1/T2) or question (T4), a declared entity class, and optionally an as-of date (T3)." },
  { id: "class_filter", label: "Class filter", x: 250, y: 60, systems: ["class_aware", "final_agentic", "class_aware_hybrid"], ablation: "A",
    effect: ["t2:t2_xclass_t1", "t1:Class filter, no verifier: class-aware − class-blind:flag_macro_f1", "t1:Ablation A (verifier on): final agentic − class-blind + verifier:flag_macro_f1"],
    detail: "Restricts candidates to the target class's Directions (entity-class metadata). Its gain on T2 is partly by construction." },
  { id: "temporal_filter", label: "Temporal filter", x: 250, y: 230, systems: ["T3 pipeline"], ablation: "B", effect: ["t3:status"],
    detail: "Keeps paragraphs in force on the as-of date, using the same amendment index that builds T3 (circular by construction)." },
  { id: "bm25", label: "BM25 (bm25s)", x: 500, y: 0, systems: ["bm25", "hybrid_rrf", "class_aware_hybrid"], detail: "lucene variant, k1 1.5, b 0.75." },
  { id: "dense", label: "Dense bge-base-en-v1.5", x: 500, y: 100, systems: ["dense", "hybrid_rrf", "class_aware_hybrid"], detail: "Pinned revision a5beb1e3…; normalised embeddings, exact inner product." },
  { id: "rrf", label: "Hybrid RRF (k = 60)", x: 500, y: 200, systems: ["hybrid_rrf", "class_aware_hybrid", "class_blind", "class_aware"], detail: "Reciprocal rank fusion of BM25 and dense ranks." },
  { id: "llm", label: "LLM judgement", x: 760, y: 100, systems: ["class_blind", "class_aware", "final_agentic", "ablation_a"],
    detail: "gemini-3.5-flash-lite, temperature 0, minimal thinking, JSON mode, frozen prompts (configs/p4_prompts_v1)." },
  { id: "verifier", label: "NLI verifier (retry / abstain)", x: 1010, y: 100, systems: ["final_agentic", "ablation_a"], ablation: "C",
    effect: ["t1:Ablation C on T1: final agentic − class-aware:flag_macro_f1", "t1:Ablation C on T1: final agentic − class-aware:coverage"],
    detail: "cross-encoder/nli-deberta-v3-xsmall at a pinned revision. Whole-paragraph premise vs one-sentence rationale; abstentions are scored as errors (A11)." },
  { id: "long_context", label: "Long-context path (100K cap)", x: 760, y: 300, systems: ["long_context"], effect: ["t1:Long-context − final agentic (same items):collapsed_macro_f1"],
    detail: "Every Direction of the compared classes in one prompt; 102 of 106 items answered; comparisons on the same 102 items." },
  { id: "comparator", label: "Structured comparator (13 fields + fixed rule)", x: 760, y: -60, systems: ["comparator"], effect: ["prereg:comparator − class_aware:different_f1"],
    detail: "Extracts 13 fields from both sides; comparator-rule-v1 decides same > different > none. Prompt + rule frozen by sha256 before any T1 run." },
  { id: "verdict", label: "Verdict + pointer", x: 1260, y: 100, kind: "verdict", systems: [], detail: "Per-class judgement, matched paragraph pointer (id, URL, harvest date, sha256)." },
  { id: "confidence", label: "Confidence layer (§8.2)", x: 1260, y: -60, kind: "product", systems: ["comparator"],
    detail: "M2: logistic score over comparator-intrinsic signals, fitted on the 30-item dev set and frozen before gold evaluation (product badges). M1: full signals, cross-validated on gold (research views)." },
];
const EDGES: [string, string][] = [["query", "class_filter"], ["query", "temporal_filter"], ["class_filter", "bm25"], ["class_filter", "dense"], ["temporal_filter", "rrf"],
  ["bm25", "rrf"], ["dense", "rrf"], ["rrf", "llm"], ["llm", "verifier"], ["verifier", "verdict"], ["llm", "verdict"], ["query", "long_context"], ["long_context", "verdict"],
  ["query", "comparator"], ["comparator", "verdict"], ["comparator", "confidence"], ["confidence", "verdict"]];

export default function Architecture() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const open = useDrawer((st) => st.open);
  const [sel, setSel] = useState<string>("comparator");
  const nodes: Node[] = useMemo(() => COMPS.map((c) => ({
    id: c.id, position: { x: c.x * 0.86, y: c.y * 1.15 }, data: { label: c.label },
    style: { background: c.kind === "product" ? "var(--product-soft)" : c.kind === "input" || c.kind === "verdict" ? "var(--panel-2)" : "var(--panel)",
      color: "var(--ink)", border: `1px solid ${sel === c.id ? "var(--accent)" : "var(--line)"}`, borderRadius: 8, fontSize: 12, width: 190, boxShadow: sel === c.id ? "0 0 0 2px var(--accent)" : undefined },
  })), [sel]);
  const edges: Edge[] = EDGES.map(([a, b]) => ({ id: `${a}-${b}`, source: a, target: b, markerEnd: { type: MarkerType.ArrowClosed, color: "var(--ink-3)" }, style: { stroke: "var(--ink-3)" } }));
  const c = COMPS.find((x) => x.id === sel)!;
  const fz = s.frozenComparator;
  return (
    <div>
      <PageHeader title="System Architecture Map" tier="SHOULD" subtitle="Click a component: the systems that use it, its ablation, and its measured effect." />
      <div className="grid gap-3 lg:grid-cols-[1fr_340px]">
        <Card className="h-[520px] overflow-hidden">
          <ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.04 }} onNodeClick={(_, n) => setSel(n.id)} nodesDraggable={false} proOptions={{ hideAttribution: true }}
            colorMode={document.documentElement.classList.contains("dark") ? "dark" : "light"}>
            <Background color="var(--line)" /><Controls showInteractive={false} />
          </ReactFlow>
        </Card>
        <Card><CardBody className="space-y-2 text-[12.5px]">
          <h3 className="text-[14px] font-semibold">{c.label}</h3>
          <p>{c.detail}</p>
          {c.ablation && <p>Ablation toggle: <Badge tone="accent">{c.ablation}</Badge></p>}
          {c.systems.length > 0 && <p>Used by: {c.systems.map((x) => <button key={x} type="button" className="mr-1 cursor-pointer text-accent hover:underline" onClick={() => open(`system:${x}`)}>{d.systemName(x)}</button>)}</p>}
          {(c.effect ?? []).map((pid) => { const p = s.paired.find((x) => x.id === pid); return p ? (
            <div key={pid}><p className="text-ink-3">{p.label} · {p.metric}</p><CICell point={p.delta} ci={p.ci} label={p.ciLabel} sourceKey={p.sourceKey} signed compact onOpen={() => open(`paired:${p.id}`)} />
              <CaveatChips ids={p.family === "T2" ? ["by_construction"] : p.family === "T3" ? ["circular"] : ["scoring_asymmetry", "single_expert"]} /></div>) : null; })}
          {c.id === "comparator" && (
            <div className="rounded-md bg-panel-2 p-2 text-[11.5px]"><p className="font-medium">Frozen {fz.frozen_at_utc} · {fz.model}</p>
              {Object.entries(fz.sha256).map(([k, v]) => <p key={k}><code>{k}</code> <code className="text-ink-3">{v.slice(0, 20)}…</code></p>)}</div>
          )}
          {c.id === "llm" && <p className="text-ink-3">Prompt hashes: see <Link className="text-accent" to="/provenance">Provenance &amp; Freeze Ledger</Link>.</p>}
        </CardBody></Card>
      </div>
    </div>
  );
}

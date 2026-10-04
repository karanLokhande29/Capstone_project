import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { RuleCard } from "@/components/RuleCard";
import { r10Freeze } from "@/intelligence/rules";
import { resolveKey } from "@/lib/keys";

export default function Provenance() {
  const s = useData((st) => st.snapshot)!;
  const model = useData((st) => st.confidence);
  const open = useDrawer((st) => st.open);
  const r10 = r10Freeze(s.frozen);
  const R = s.results;
  const p4 = resolveKey(R, "tables.11_llm_usage.p4") as { model: string; thinking: Record<string, string> };
  const timeline = [
    ["2026-09-26 → 09-29", "Gold v1 (P2-004) and P4-001 systems run on gold; results_v1.json"],
    ["2026-10-02", "Reliability plan v2 + amendments (pre-registration; comparator comparisons = amendment 3)"],
    ["2026-10-02", "Comparator developed on the separate 30-item dev set; one bug-fix revision (run 1 superseded)"],
    [s.frozenComparator.frozen_at_utc, "Comparator prompt + rule FROZEN by sha256 (FROZEN.json)"],
    ["2026-10-03", "Sealed predictions: comparator run on gold (412 units, prompt hash checked per unit)"],
    ["2026-10-03", "Gold scoring → results_v2.json (regression vs p4001 exact)"],
    [model?.evaluatedUtc ?? "—", "Confidence model: spec written → M2 frozen on dev → gold evaluation (this UI)"],
  ];
  return (
    <div>
      <PageHeader title="Provenance & Freeze Ledger" tier="SHOULD" subtitle="Recorded vs recomputed sha256 of every frozen artefact, the pre-registration order, decisions and LLM settings." />
      <div className={r10.verdict === "fail" ? "mb-3 rounded-md border border-neg bg-neg-soft p-3 text-sm font-medium text-neg" : "mb-3"}>{r10.verdict === "fail" ? `R10: ${r10.reason}` : <RuleCard r={r10} />}</div>
      <Card><CardBody className="overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-[12px]">
          <thead><tr className="border-b border-line text-left text-ink-3"><th className="px-3 py-2 font-normal">Artefact</th><th className="font-normal">Expected (source)</th><th className="font-normal">Recomputed at ingest</th><th className="font-normal">Status</th></tr></thead>
          <tbody>{s.frozen.map((f) => (
            <tr key={f.path} className="border-b border-line last:border-0">
              <td className="px-3 py-1.5"><code>{f.path}</code></td>
              <td><code className="text-ink-3">{f.expectedSha256.slice(0, 16)}…</code><span className="block text-[10.5px] text-ink-3">{f.expectedSource}</span></td>
              <td><code className="text-ink-3">{f.actualSha256?.slice(0, 16) ?? "—"}…</code></td>
              <td><Badge tone={f.status === "match" ? "pos" : "neg"}>{f.status}</Badge></td>
            </tr>))}</tbody>
        </table>
      </CardBody></Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Pre-registration timeline: the freeze came before gold scoring">
          <Card><CardBody><ol className="relative space-y-3 border-l border-line pl-4 text-[12.5px]">
            {timeline.map(([t, e], i) => (
              <li key={i}><span className={`absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full ${e.includes("FROZEN") ? "bg-accent" : "bg-ink-3"}`} />
                <span className="num text-ink-3">{t}</span><p className={e.includes("FROZEN") ? "font-semibold" : ""}>{e}</p></li>))}
          </ol></CardBody></Card>
        </Section>
        <Section title="LLM settings">
          <Card><CardBody className="space-y-1 text-[12.5px]">
            <p>Model: <code>{p4.model}</code> for every P4 system and the comparator</p>
            <p>Temperature 0 · thinking {Object.entries(p4.thinking).map(([k, v]) => `${k}: ${v}`).join(", ")} · JSON mode · frozen prompts</p>
            <p>NLI verifier: cross-encoder/nli-deberta-v3-xsmall (pinned revision)</p>
            <p>Dense: BAAI/bge-base-en-v1.5 @ a5beb1e3e68b9ab74eb54cfd186867f64f240e1a</p>
            <p className="text-ink-3">Assistant / live mode (opt-in) use a separate ASSISTANT_GEMINI_API_KEY and Google Cloud project; never the experiment key or quota.</p>
          </CardBody></Card>
        </Section>
      </div>
      <Section title="Decision log (public records)">
        <div className="grid gap-2 md:grid-cols-2">{s.decisions.map((dd) => (
          <Card key={dd.id} className="cursor-pointer hover:border-accent" onClick={() => open(`decision:${dd.id}`)}><CardBody className="text-[12.5px]">
            <p className="font-medium">{dd.decision}</p><p className="text-ink-3">Alternatives: {dd.alternatives} · {dd.record}</p><p>{dd.rationale}</p>
          </CardBody></Card>))}</div>
      </Section>
    </div>
  );
}

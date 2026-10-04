import { Link } from "react-router-dom";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { CaveatChips } from "@/components/CaveatChip";

const IDEAS = [
  ["Pre-submission gate", "One line on Readiness and Claims: unmatched numbers · over-claims · placeholders.", "/readiness"],
  ["Blast-radius graph", "Upstream/Downstream tabs and per-Future-Work regeneration lists.", "/next"],
  ["Reviewer / viva mode", "A guided, deep-linkable tour through the four traceability chains.", "/tour"],
  ["Comparator field heatmap", "Which of the 13 fields decide `different`, split by right and wrong verdicts.", "/different"],
  ["Annotation workbench", "Future Work #1–#2 with an enforced washout timer and per-item timestamps (browser-local).", "/workbench"],
  ["Snapshot diff", "results v1 → v2 numeric diff.", "/diff"],
  ["Human-review queue", "Low-confidence comparator verdicts routed to an analyst (selective prediction as a workflow).", "/review-queue"],
  ["Exports", "PNG/SVG for the forest plot and heatmap; gap list as Markdown.", "/gaps"],
] as const;

export default function BuildNext() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  return (
    <div>
      <PageHeader title="What should we build next?" tier="MUST" subtitle="Before submission (dated) and after submission (Future Work 1–11 in the authors' order)." />
      <Section title="Before submission">
        <div className="grid gap-2 md:grid-cols-3">{s.recommendations.filter((r) => r.tier === "REQUIRED").map((r) => (
          <Card key={r.id}><CardBody className="text-[12.5px]"><Badge tone="neg">{r.priority}</Badge><p className="mt-1 font-medium">{r.title}</p><p className="text-ink-3">{r.why}</p></CardBody></Card>))}
          {s.submissionTasks.filter((t) => t.status !== "done").slice(0, 3).map((t) => (
            <Card key={t.id}><CardBody className="text-[12.5px]"><span className="num text-ink-3">{t.due}</span><p className="font-medium">{t.title}</p></CardBody></Card>))}
        </div>
      </Section>
      <Section title="After submission: Future Work (authors' ranking, unchanged)">
        <div className="space-y-2">
          {s.futureWork.map((f) => (
            <Card key={f.rank}><CardBody className="grid gap-2 text-[12.5px] md:grid-cols-[40px_1fr_1fr]">
              <span className="text-[18px] font-semibold text-ink-3">#{f.rank}</span>
              <div>
                <button type="button" onClick={() => open(`fw:${f.rank}`)} className="cursor-pointer font-medium hover:text-accent">{f.item}</button>
                <p>{f.what}</p><p className="text-ink-3">Why: {f.why}</p><p className="text-ink-3">Effort: {f.effort}</p>
                {f.limitationIds.length > 0 && <div className="mt-1">Limitations addressed: <CaveatChips ids={f.limitationIds} /></div>}
              </div>
              <div>
                <p><b>Blast radius:</b> {f.blastRadius.join(" · ") || "—"}</p>
                {f.strengthens.length > 0 && <p>Strengthens: {f.strengthens.join(", ")}</p>}
                {f.couldOverturn.length > 0 && <p className="text-warn">Could overturn: {f.couldOverturn.join(", ")}</p>}
                {f.dependsOn.length > 0 && <p>Depends on: #{f.dependsOn.join(", #")}</p>}
                {f.openQuestions.length > 0 && <p className="text-ink-3">Open: {f.openQuestions.join(" ")}</p>}
              </div>
            </CardBody></Card>
          ))}
        </div>
      </Section>
      <Section title="Suggested re-ranking (separate panel; the authors' order above is authoritative)">
        <Card><CardBody className="text-[12.5px]">
          <p>Move <b>#2 second raters</b> ahead of <b>#1 retest</b> only if annotator time allows: it removes the single-expert caveat that sits upstream of five of the seven findings and of the confidence calibration, whereas #1 only tightens supplementary evidence. #1 stays cheaper and could run first as a pilot.</p>
        </CardBody></Card>
      </Section>
      <Section title="If I were building this product (kept: each has a clear user benefit)">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">{IDEAS.map(([t, d, href]) => (
          <Link key={t} to={href} className="rounded-md border border-line bg-panel p-2.5 text-[12.5px] hover:border-accent"><b>{t}</b><p className="text-ink-3">{d}</p></Link>))}</div>
        <p className="mt-2 text-[12px] text-ink-3">Rejected: activity feeds, velocity metrics, ungrounded "AI insights", any numeric health score without a stated formula.</p>
      </Section>
    </div>
  );
}

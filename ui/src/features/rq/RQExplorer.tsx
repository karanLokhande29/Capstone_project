import { useParams, Link } from "react-router-dom";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { CICell } from "@/components/CICell";
import { CaveatChips } from "@/components/CaveatChip";
import { cn } from "@/lib/utils";

export default function RQExplorer() {
  const { id } = useParams();
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const open = useDrawer((st) => st.open);
  return (
    <div>
      <PageHeader title="Research Question Explorer" tier="MUST" subtitle="Verbatim research questions → tasks → findings → answer status. RQ text is never paraphrased." />
      <div className="space-y-4">
        {d.rqs.map((r) => (
          <Card key={r.id} id={r.id} className={cn(id === r.id && "ring-2 ring-accent")}>
            <CardBody className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Link to={`/rq/${r.id}`} className="text-[15px] font-semibold hover:text-accent">{r.id} — {r.label}</Link>
                <Badge tone={r.answeredStatus === "answered" ? "pos" : r.answeredStatus === "partial" ? "warn" : "neg"}>{r.answeredStatus}</Badge>
                <button type="button" className="cursor-pointer text-[12px] text-accent hover:underline" onClick={() => open(`rq:${r.id}`)}>trace →</button>
              </div>
              <blockquote className="border-l-2 border-accent pl-3 text-[13.5px] italic text-ink">{r.text}</blockquote>
              {r.operationalisation && <p className="rounded-md bg-panel-2 px-3 py-2 text-[12.5px]"><b>Operationalisation (A6).</b> {r.operationalisation}</p>}
              <p className="text-[13px]"><b>Status reason.</b> {r.statusReason}</p>
              <div className="flex flex-wrap gap-2 text-[12.5px]">
                <span className="text-ink-3">Tasks:</span>
                {r.taskIds.map((t) => <button key={t} type="button" onClick={() => open(`task:${t}`)} className="cursor-pointer rounded bg-panel-2 px-1.5 hover:text-accent">{t}: {d.tasks.find((x) => x.id === t)?.title}</button>)}
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                {r.findingIds.map((fid) => {
                  const f = s.findings.find((x) => x.id === fid)!;
                  return (
                    <div key={fid} className="rounded-md border border-line p-2.5">
                      <button type="button" onClick={() => open(`finding:${fid}`)} className="cursor-pointer text-left text-[12.5px] font-medium hover:text-accent">{fid}: {f.statement}</button>
                      <div className="mt-1.5">{f.ci ? <CICell point={f.delta!} ci={f.ci} label={f.ciLabel} sourceKey={f.sourceKey} signed compact /> : <span className="num text-[12px]">{f.count} units</span>}</div>
                      <CaveatChips ids={f.caveatIds} className="mt-1.5" />
                    </div>
                  );
                })}
              </div>
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}

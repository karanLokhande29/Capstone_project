import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { PageHeader } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import { CICell } from "@/components/CICell";
import { CaveatChips } from "@/components/CaveatChip";

export default function Reliability() {
  const s = useData((st) => st.snapshot)!;
  const open = useDrawer((st) => st.open);
  return (
    <div>
      <PageHeader title="Annotation & Reliability" tier="MUST" />
      <div className="mb-4 rounded-lg border border-warn/50 bg-warn-soft px-4 py-3 text-[14px] font-medium text-warn">
        Gold is single-expert. Agreement below is measured on a separate 30-item sample, not on the gold.
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {s.reliability.map((r) => (
          <Card key={r.id}><CardBody className="space-y-2">
            <div className="flex flex-wrap items-center gap-1.5"><b className="text-[13px]">{r.statistic}, {r.target}</b><Badge tone="outline">in gold: no</Badge>
              {r.ciCrossesZero && <Badge tone="warn">CI crosses 0</Badge>}</div>
            <p className="text-[12px] text-ink-3">{r.design} · raters {r.raters}</p>
            <CICell point={r.value} ci={r.ci} label={r.ciLabel} sourceKey={r.sourceKey} domain={[-0.2, 1]} onOpen={() => open(`reliability:${r.id}`)} />
            <p className="text-[12px]">n = {r.n} items{r.nUnits ? `, ${r.nUnits} units` : ""}</p>
            {r.caveat && <CaveatChips ids={[r.caveat]} />}
          </CardBody></Card>
        ))}
      </div>
      <Card className="mt-4"><CardBody className="space-y-2 text-[13px]">
        <p><b>Retest gap.</b> The actual gap between the passes was 11.7–18.6 h (file-level bounds; per-item times were not logged), so recall may inflate agreement. The retest is supplementary evidence.</p>
        <p><b>Candidates shown on the sheets.</b> Every sheet showed the same two P2-002 candidate paragraphs per compared class (bge-base-en-v1.5 top-1 and top-2), in random order and with no scores. This may bias judgements toward them; the same bias is disclosed for T2. The comparator saw the same two candidates.</p>
        <p><b>Earlier team review.</b> Recorded as not independent; never used for agreement.</p>
        <p className="text-ink-3">Raters appear only as rater_1–rater_3.</p>
      </CardBody></Card>
    </div>
  );
}

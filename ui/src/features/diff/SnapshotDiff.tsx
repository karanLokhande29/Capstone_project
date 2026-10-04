import { useData } from "@/data/store";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Card, CardBody } from "@/components/ui/primitives";

export default function SnapshotDiff() {
  const s = useData((st) => st.snapshot)!;
  const df = s.diff;
  const all = [...df.changed, ...df.added, ...df.removed];
  return (
    <div>
      <PageHeader title="Snapshot diff: results v1 → v2" tier="COULD"
        subtitle={<>reports/results_v1.json (<code>{df.v1Sha.slice(0, 12)}…</code>) vs reports/results_v2.json (<code>{df.v2Sha.slice(0, 12)}…</code>). Part A changed wording only; it changed no result.</>} />
      <Card><CardBody className="space-y-1 text-[13px]">
        <p>v1 tables: <b>{df.tablesNumericLeaves}</b> numeric values. Changed in v2: <b>{df.changed.length}</b> · added: <b>{df.added.length}</b> · removed: <b>{df.removed.length}</b>.</p>
        <p>New top-level sections in v2: {df.newSections.map((x) => <Badge key={x} tone="accent" className="mr-1">{x}</Badge>)}</p>
        <p className="text-ink-3">phase4 holds the gold-v1 rescoring (regression vs p4001 exact) and the comparator: {df.phase4Keys.join(", ")}.</p>
      </CardBody></Card>
      <Section title={all.length ? "Changed values" : "No numeric value under `tables` changed between v1 and v2"}>
        {all.length > 0 && <Card><CardBody className="overflow-x-auto p-0"><table className="w-full text-[12px]"><tbody>
          {all.map((e) => <tr key={e.key} className="border-b border-line"><td className="px-3 py-1"><code>{e.key}</code></td><td>{e.v1 ?? "—"}</td><td>{e.v2 ?? "—"}</td><td><Badge>{e.kind}</Badge></td></tr>)}
        </tbody></table></CardBody></Card>}
      </Section>
    </div>
  );
}

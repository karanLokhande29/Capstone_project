import { Copy } from "lucide-react";
import { useData } from "@/data/store";
import { PageHeader, Section } from "@/components/Page";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { RuleCard } from "@/components/RuleCard";
import { r11Deadline, r12Scoring } from "@/intelligence/rules";
import { useNow } from "@/app/Countdown";
import { gate } from "@/features/claims/claimStatus";

const UNVERIFIED = ["Anonymity / blind review"];

export default function Readiness() {
  const s = useData((st) => st.snapshot)!;
  const now = useNow();
  const r11 = r11Deadline(s.submissionTasks, now);
  const g = gate(s);
  const master = s.masterSections.map((x) => x.text).join("\n");
  const crit = ["ST-PROSE", "ST-OVERLEAF", "ST-PDF", "ST-CMT"];
  return (
    <div>
      <PageHeader title="Submission Readiness" tier="MUST" subtitle="AISIGH–SD 2026 · CMT deadline 10 Oct 2026 · 6 pages is the hard limit. The UI never runs commands; copy them into a terminal." />
      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="lg:col-span-2"><CardBody className="p-0">
          <ol>
            {s.submissionTasks.map((t, i) => {
              const r = r11[i];
              return (
                <li key={t.id} className="border-b border-line px-3 py-2.5 last:border-0">
                  <div className="flex flex-wrap items-center gap-2 text-[13px]">
                    <span className="num w-20 shrink-0 text-ink-3">{t.due}</span>
                    <b>{t.title}</b>
                    {crit.includes(t.id) && <Badge tone="accent">critical path</Badge>}
                    <Badge tone={r.verdict === "fail" ? "neg" : r.verdict === "warn" ? "warn" : "neutral"}>{r.verdict === "fail" ? "overdue" : r.verdict === "warn" ? "< 1 day" : t.status}</Badge>
                  </div>
                  {t.dependsOn.length > 0 && <p className="ml-[88px] text-[11.5px] text-ink-3">depends on {t.dependsOn.join(", ")}</p>}
                  {t.note && <p className="ml-[88px] text-[11.5px] text-warn">{t.note}</p>}
                  {t.verifyCommand && (
                    <div className="ml-[88px] mt-1 flex items-center gap-1.5">
                      <code className="min-w-0 truncate rounded bg-panel-2 px-1.5 py-0.5 text-[11px]">{t.verifyCommand}</code>
                      <Button variant="ghost" size="sm" aria-label={`Copy command for ${t.title}`} onClick={() => navigator.clipboard?.writeText(t.verifyCommand!)}><Copy size={12} /></Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        </CardBody></Card>
        <div className="space-y-3">
          <Card><CardBody className="space-y-1 text-[12.5px]">
            <h3 className="text-[13px] font-semibold">Pre-submission gate</h3>
            <p className={g.unmatched ? "text-neg" : "text-pos"}>{g.unmatched} unmatched numbers</p>
            <p className={g.overclaims ? "text-warn" : "text-pos"}>{g.overclaims} over-claims (R1)</p>
            <p className={g.placeholders ? "text-neg" : "text-pos"}>{g.placeholders} placeholders</p>
          </CardBody></Card>
          <Card><CardBody className="text-[12.5px]">
            <h3 className="mb-1 text-[13px] font-semibold">Live placeholder scan (R7)</h3>
            <ul className="space-y-0.5">{s.placeholders.map((p, i) => <li key={i}><code>{p.text}</code> <span className="text-ink-3">{p.file}:{p.line} → {p.task}</span></li>)}</ul>
            <p className="mt-1 text-ink-3">Never invented: the authors fill the emails and the Zenodo DOI (A10/A16).</p>
          </CardBody></Card>
          <Card><CardBody className="text-[12.5px]">
            <h3 className="mb-1 text-[13px] font-semibold">Part A status</h3>
            <ul className="space-y-0.5">{s.meta.partAStatus.sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1))).map((p) => (
              <li key={p.id}><Badge tone={p.status === "present" ? "pos" : "warn"}>{p.id}</Badge> {p.note}</li>))}</ul>
          </CardBody></Card>
          <RuleCard r={r12Scoring(master)} />
        </div>
      </div>
      <Section title={`Venue constraints (read ${s.venue.checked}; source: ${s.venue.file})`}>
        <Card><CardBody className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] text-[12px]">
            <tbody>{s.venue.facts.map((f) => (
              <tr key={f.item} className="border-b border-line align-top last:border-0">
                <td className="w-48 px-3 py-1.5 font-medium">{f.item}{(UNVERIFIED.includes(f.item) || f.text.toLowerCase().includes("not stated")) && <Badge tone="warn" className="ml-1">Needs validation</Badge>}</td>
                <td className="py-1.5 pr-2">{f.text}</td>
                <td className="py-1.5 pr-3 text-ink-3">{f.sources.map((x) => <a key={x.id} href={x.url} target="_blank" rel="noreferrer" className="mr-1 text-accent hover:underline">{x.id}</a>)}<span className="block text-[10.5px]">{f.accessed}</span></td>
              </tr>))}</tbody>
          </table>
        </CardBody></Card>
        <Card className="mt-2"><CardBody className="text-[12.5px]"><b>Differences from the submission checklist:</b> {s.venue.differences.join(" · ")}</CardBody></Card>
      </Section>
    </div>
  );
}

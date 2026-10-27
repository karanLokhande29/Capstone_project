import { Card, CardBody } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { live } from "./api";
import { useAudit } from "./state";

const FORMATS = [
  { fmt: "xlsx" as const, label: "Excel workbook", note: "Summary, Applicability, Changes, Calendar, Differential, Enforcement, Gap analysis, Sources, About; filters, frozen headers, review columns" },
  { fmt: "docx" as const, label: "Report (DOCX)", note: "Executive summary, tables, About box" },
  { fmt: "pdf" as const, label: "Report (PDF)", note: "Same report; disclaimer and corpus hash in every page footer" },
  { fmt: "ics" as const, label: "Compliance calendar (.ics)", note: "Dated due dates for the next 12 months; low-confidence entries marked [verify]" },
  { fmt: "json" as const, label: "JSON audit trail", note: "Inputs, corpus hash, rule and threshold versions, the source of every row; uploaded files as hashes only" },
];

export default function Downloads() {
  const { mode, pack } = useAudit();
  return (
    <div>
      <PageHeader title="Downloads" subtitle="Every export carries the corpus snapshot and hash, the tool and rules versions, the as-of date, the entity profile, the validation box and the disclaimer." />
      {!pack ? <p className="text-[13px] text-ink-3">No pack loaded.</p> : (
        <Card><CardBody>
          <ul className="space-y-2 text-[13px]" aria-label="Exports">
            {FORMATS.map((f) => (
              <li key={f.fmt} className="flex flex-wrap items-baseline gap-2">
                {mode === "live"
                  ? <a className="font-medium text-accent hover:underline" href={live.exportUrl(pack.pack_id, f.fmt)} download>{f.label}</a>
                  : <span className="font-medium text-ink-3">{f.label}</span>}
                <span className="text-[12px] text-ink-3">{f.note}</span>
              </li>
            ))}
          </ul>
          {mode !== "live" && <p className="mt-3 text-[12.5px] text-ink-3">Replay mode cannot build files. The sample packs' exports are already on disk in
            <code> outputs/auditgen_samples/&lt;pack&gt;/</code> (audit_pack.xlsx, audit_report.docx / .pdf, compliance_calendar.ics, audit_trail.json); start the backend to export any pack.</p>}
        </CardBody></Card>
      )}
    </div>
  );
}

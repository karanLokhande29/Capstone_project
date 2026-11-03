import { Card, CardBody } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { useState } from "react";
import { downloadExport, HOSTED, live } from "./api";
import { useAudit } from "./state";
import { INSTALLED, PUBLIC_DEMO } from "./parts";

// Public demo: the same exports, pre-built from the capped sample packs by scripts/build_public_extras.py.
const FILE = { xlsx: "audit_pack.xlsx", docx: "audit_report.docx", pdf: "audit_report.pdf", ics: "compliance_calendar.ics", json: "audit_trail.json" };

const FORMATS = [
  { fmt: "xlsx" as const, label: "Excel workbook", note: "Summary, Applicability, Changes, Calendar, Differential, Enforcement, Gap analysis, Sources, About; filters, frozen headers, review columns" },
  { fmt: "docx" as const, label: "Report (DOCX)", note: "Executive summary, tables, About box" },
  { fmt: "pdf" as const, label: "Report (PDF)", note: "Same report; disclaimer and corpus hash in every page footer" },
  { fmt: "ics" as const, label: "Compliance calendar (.ics)", note: "Dated due dates for the next 12 months; low-confidence entries marked [verify]" },
  { fmt: "json" as const, label: "JSON audit trail", note: "Inputs, corpus hash, rule and threshold versions, the source of every row; uploaded files as hashes only" },
];

export default function Downloads() {
  const { mode, pack, packs } = useAudit();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sample = packs.find((p) => p.pack_id === pack?.pack_id);
  return (
    <div>
      <PageHeader title="Downloads" subtitle="Every export carries the corpus snapshot and hash, the tool and rules versions, the as-of date, the entity profile, the validation box and the disclaimer." />
      {!pack ? <p className="text-[13px] text-ink-3">No pack loaded.</p> : (
        <Card><CardBody>
          <ul className="space-y-2 text-[13px]" aria-label="Exports">
            {FORMATS.map((f) => (
              <li key={f.fmt} className="flex flex-wrap items-baseline gap-2">
                {mode === "live" && HOSTED
                  ? <button className="font-medium text-accent hover:underline disabled:text-ink-3" disabled={busy !== null}
                      onClick={async () => { setBusy(f.fmt); setErr(null); try { await downloadExport(pack.pack_id, f.fmt); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); } }}>
                      {busy === f.fmt ? `Building ${f.label}…` : f.label}</button>
                  : mode === "live"
                  ? <a className="font-medium text-accent hover:underline" href={live.exportUrl(pack.pack_id, f.fmt)} download>{f.label}</a>
                  : PUBLIC_DEMO && sample
                    ? <a className="font-medium text-accent hover:underline" href={`/auditgen/exports/${pack.pack_id}/${FILE[f.fmt]}`} download>{f.label}</a>
                    : <span className="font-medium text-ink-3">{f.label}</span>}
                <span className="text-[12px] text-ink-3">{f.note}</span>
              </li>
            ))}
          </ul>
          {err && <p className="mt-2 text-[12.5px] text-neg">{err}</p>}
          {mode === "live" && HOSTED && <p className="mt-3 text-[12.5px] text-ink-3">Files are built for this pack on request (the Excel workbook can take up to a minute); RBI quotes are cut to 12 words and every row links to the official RBI PDF.</p>}
          {mode !== "live" && PUBLIC_DEMO && <p className="mt-3 text-[12.5px] text-ink-3">These are the real exports of this sample pack, with RBI quotes cut to 12 words;
            each row keeps its link to the official RBI PDF. {INSTALLED.charAt(0).toUpperCase() + INSTALLED.slice(1)} builds them for your own profile with the full text.</p>}
          {mode !== "live" && !PUBLIC_DEMO && <p className="mt-3 text-[12.5px] text-ink-3">Replay mode cannot build files. The sample packs' exports are already on disk in
            <code> outputs/auditgen_samples/&lt;pack&gt;/</code> (audit_pack.xlsx, audit_report.docx / .pdf, compliance_calendar.ics, audit_trail.json); start the backend to export any pack.</p>}
        </CardBody></Card>
      )}
    </div>
  );
}

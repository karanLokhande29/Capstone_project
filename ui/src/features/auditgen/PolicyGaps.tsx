import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { HOSTED, live } from "./api";
import { useAudit } from "./state";
import { GapTable } from "./AuditPack";
import { Stat, INSTALLED, PUBLIC_DEMO } from "./parts";

export default function PolicyGaps() {
  const { mode: m, pack, reload } = useAudit();
  // The hosted service has no uploads or corpus refresh: those pages behave as in the read-only demo.
  const mode = HOSTED ? "replay" : m;
  const [files, setFiles] = useState<File[]>([]);
  const [fams, setFams] = useState<string[]>([]);
  const [explain, setExplain] = useState(false);
  const [llm, setLlm] = useState<{ available: boolean; reason?: string; model?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (mode === "live") void live.llm().then(setLlm).catch(() => setLlm(null)); }, [mode]);
  const families = useMemo(() => Array.from(new Set((pack?.register ?? []).filter((r) => !r.hidden && r.subject_family).map((r) => r.subject_family))).sort(), [pack]);
  const g = pack?.gaps;
  return (
    <div>
      <PageHeader title="Policy gaps" subtitle="Upload your policies (PDF, DOCX, TXT, MD). Each applicable obligation is marked covered / partial / missing with the matched clauses and scores, using local models only (bge + NLI cross-encoder)." />
      <Card><CardBody className="space-y-2 text-[12.5px]">
        <p className="rounded-md bg-accent-soft p-2 text-accent"><b>Privacy:</b> {PUBLIC_DEMO ? "in the installed version, documents are processed inside your network only." : "documents are processed on this machine only."} No document text goes to Gemini, Groq or any remote API.
          {!PUBLIC_DEMO && <>Files are stored in <code>data/auditgen_uploads/&lt;session&gt;/</code> (gitignored) and can be deleted below.</>}</p>
        {mode !== "live" ? <p className="text-ink-3">{PUBLIC_DEMO ? <>Uploading your own policies is part of {INSTALLED}. This demo shows the sample pack's gap run on a synthetic policy.</>
          : <>Uploading needs the local backend (<code>python3 scripts/auditgen.py serve</code>). Replay shows the sample pack's gap run on a synthetic policy.</>}</p> : (
          <form aria-label="Upload policies" className="space-y-2" onSubmit={async (e) => {
            e.preventDefault();
            if (!pack || !files.length) return;
            setBusy(true); setMsg(null);
            try { const r = await live.gaps(pack.pack_id, files, fams, explain); setMsg(`Done: ${JSON.stringify(r.counts)}`); await reload(); }
            catch (x) { setMsg((x as Error).message); } finally { setBusy(false); }
          }}>
            <input type="file" multiple accept=".pdf,.docx,.txt,.md" aria-label="Policy files" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            <label className="flex flex-col gap-1">Limit to subject families (optional; hold Cmd/Ctrl)
              <select multiple className="h-24 rounded-md border border-line bg-panel px-2" value={fams} onChange={(e) => setFams(Array.from(e.target.selectedOptions).map((o) => o.value))}>
                {families.map((f) => <option key={f}>{f}</option>)}
              </select>
            </label>
            {llm?.available ? (
              <label className="flex items-center gap-1"><input type="checkbox" checked={explain} onChange={(e) => setExplain(e.target.checked)} />
                Plain-language explanations from the local LLM ({llm.model}); every sentence is NLI-verified, unsupported ones are dropped.</label>
            ) : <p className="text-ink-3">Local LLM explanations: unavailable{llm?.reason ? ` (${llm.reason})` : ""}. Gap analysis works without it.</p>}
            <Button type="submit" disabled={busy || !files.length || !pack}>{busy ? "Analysing locally…" : "Run gap analysis"}</Button>
            {msg && <span className="ml-2">{msg}</span>}
          </form>
        )}
      </CardBody></Card>
      {g && (
        <div className="mt-4 space-y-3">
          {g.note && <p className="rounded-md bg-warn-soft p-2 text-[12.5px] text-warn">{g.note}</p>}
          <div className="grid gap-2 md:grid-cols-4">
            <Stat label="Covered" value={g.counts.covered ?? 0} tone="pos" />
            <Stat label="Partial" value={g.counts.partial ?? 0} tone="warn" />
            <Stat label="Missing" value={g.counts.missing ?? 0} tone="neg" />
            <Stat label="Policy clauses" value={g.clauses} />
          </div>
          <p className="text-[12px] text-ink-3">Files: {g.files.map((f) => `${f.name} (sha256 ${f.sha256.slice(0, 12)}…, ${f.clauses} clauses)`).join("; ")} · models {Object.values(g.models).join(", ")} ·
            thresholds {Object.entries(g.thresholds).map(([k, v]) => `${k} ${v}`).join(", ")}. Missing items are ranked by enforcement risk.</p>
          {mode === "live" && g.session && pack && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={async () => { await live.deleteUpload(g.session!, pack.pack_id, false); setMsg("Uploaded files deleted; results kept."); }}>Delete uploaded files</Button>
              <Button size="sm" variant="outline" onClick={async () => { await live.deleteUpload(g.session!, pack.pack_id, true); await reload(); setMsg("Uploaded files and results deleted."); }}>Delete files and results</Button>
            </div>
          )}
          <h3 className="text-[13px] font-semibold">Coverage by Direction</h3>
          <ul className="grid gap-1 text-[12px] md:grid-cols-2">{g.per_direction.slice(0, 20).map((d) => (
            <li key={d.md_id} className="flex items-center gap-2"><a className="truncate text-accent" href={d.source_url} target="_blank" rel="noreferrer">{d.direction_title}</a>
              <Badge tone="pos">{d.covered}</Badge><Badge tone="warn">{d.partial}</Badge><Badge tone="neg">{d.missing}</Badge></li>))}</ul>
          <GapTable rows={g.rows} />
        </div>
      )}
    </div>
  );
}

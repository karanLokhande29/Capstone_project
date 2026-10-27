import { useMemo, useState } from "react";
import { Badge, Button, Card, CardBody } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { live } from "./api";
import { useAudit } from "./state";
import { Excerpt, RowTable, SourceLink } from "./parts";
import type { Cited, Pack, ReviewStatus, Section } from "./types";

const SECTIONS: [Section, string][] = [["register", "Applicability"], ["changes", "Changes"], ["calendar", "Calendar"],
  ["differential", "Differential"], ["enforcement", "Enforcement"], ["gaps", "Gap analysis"]];
const STATUSES: ReviewStatus[] = ["unreviewed", "confirmed", "disputed", "not applicable"];

function rowsOf(pack: Pack, s: Section): Cited[] {
  if (s === "gaps") return pack.gaps?.rows ?? [];
  if (s === "register") return pack.register.filter((r) => !r.hidden);
  return pack[s] as Cited[];
}

export function progress(pack: Pack) {
  return SECTIONS.map(([s, label]) => {
    const rows = rowsOf(pack, s);
    const done = rows.filter((r) => r.review_status !== "unreviewed").length;
    return { s, label, total: rows.length, done, disputed: rows.filter((r) => r.review_status === "disputed").length };
  });
}

export default function Review() {
  const { mode, pack, reload, setPack } = useAudit();
  const [sec, setSec] = useState<Section>("register");
  const [reviewer, setReviewer] = useState("");
  const [onlyReview, setOnlyReview] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [wb, setWb] = useState<File | null>(null);
  const prog = useMemo(() => (pack ? progress(pack) : []), [pack]);
  if (!pack) return <p className="text-[13px] text-ink-3">No pack loaded.</p>;
  const editable = mode === "live" && !pack.signoff;
  const rows = rowsOf(pack, sec).filter((r) => !onlyReview || r.needs_review);
  const set = async (r: Cited, st: ReviewStatus, note: string) => {
    if (!editable) return;
    try {
      await live.review(pack.pack_id, [{ section: sec, row_id: r.row_id, review_status: st, reviewer, note }]);
      r.review_status = st; r.reviewer = reviewer; r.note = note;
      setPack({ ...pack });
    } catch (e) { setMsg((e as Error).message); }
  };
  const total = prog.reduce((a, p) => a + p.total, 0);
  const done = prog.reduce((a, p) => a + p.done, 0);
  return (
    <div>
      <PageHeader title="Review" subtitle="Confirm or dispute rows, then sign off. Nothing is settled until a reviewer confirms it. A sign-off writes a new pack; the original is kept." />
      <Card><CardBody className="space-y-2 text-[12.5px]">
        <div aria-label="Review progress" className="flex flex-wrap items-center gap-3">
          <b className="num">{done.toLocaleString()} / {total.toLocaleString()} rows reviewed</b>
          <div className="h-2 w-64 overflow-hidden rounded bg-panel-2"><div className="h-full bg-accent" style={{ width: `${total ? (100 * done) / total : 0}%` }} /></div>
          {pack.signoff && <Badge tone="pos">signed off by {pack.signoff.signer}</Badge>}
        </div>
        <ul className="flex flex-wrap gap-3 text-ink-2">{prog.map((p) => <li key={p.s}>{p.label}: <span className="num">{p.done}/{p.total}</span>{p.disputed > 0 && <span className="text-neg"> · {p.disputed} disputed</span>}</li>)}</ul>
        {mode !== "live" && <p className="text-ink-3">Read-only in replay mode. Start the backend to review, or review in the Excel export and re-import it: <code>python3 scripts/auditgen.py review-import</code>.</p>}
        {editable && (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">Reviewer<input aria-label="Reviewer name" className="h-7 rounded-md border border-line bg-panel px-2" value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></label>
            <label className="flex flex-col gap-1">Reviewed Excel (optional)<input type="file" accept=".xlsx" onChange={(e) => setWb(e.target.files?.[0] ?? null)} /></label>
            <Button disabled={!reviewer.trim()} onClick={async () => {
              try { const r = await live.signoff(pack.pack_id, reviewer, wb ?? undefined); setMsg(`Signed-off pack ${r.pack_id} written; this pack is unchanged.`); await reload(); }
              catch (e) { setMsg((e as Error).message); }
            }}>Sign off</Button>
          </div>
        )}
        {msg && <p>{msg}</p>}
      </CardBody></Card>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px]">
        {SECTIONS.map(([s, label]) => <Button key={s} size="sm" variant={sec === s ? "default" : "outline"} onClick={() => setSec(s)}>{label}</Button>)}
        <label className="ml-2 flex items-center gap-1"><input type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} />only rows that need review</label>
      </div>
      <div className="mt-2">
        <RowTable<Cited> label="Review rows" rows={rows} pageSize={25} filterText={(r) => `${r.direction_title} ${r.excerpt ?? ""} ${r.review_status}`}
          cols={[
            { key: "ob", label: "Row", render: (r) => <div><p className="text-ink-3">{r.direction_title}</p><Excerpt text={r.excerpt} pid={r.paragraph_id} /></div> },
            { key: "src", label: "Source", render: (r) => <SourceLink row={r} /> },
            { key: "st", label: "Review", render: (r) => (
              <div className="space-y-1">
                <select aria-label={`Review status for ${r.row_id}`} disabled={!editable || (!reviewer.trim())} value={r.review_status}
                  className="h-7 rounded-md border border-line bg-panel px-1" onChange={(e) => void set(r, e.target.value as ReviewStatus, r.note)}>
                  {STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
                {r.reviewer && <p className="text-ink-3">{r.reviewer} · {r.timestamp.slice(0, 16)}</p>}
                {editable && <input aria-label={`Note for ${r.row_id}`} placeholder="note" defaultValue={r.note} disabled={!reviewer.trim()}
                  className="h-7 w-full rounded-md border border-line bg-panel px-1" onBlur={(e) => { if (e.target.value !== r.note) void set(r, r.review_status, e.target.value); }} />}
              </div>) },
          ]} />
      </div>
    </div>
  );
}

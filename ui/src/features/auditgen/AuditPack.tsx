import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, CardBody, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { PageHeader } from "@/components/Page";
import { live } from "./api";
import { useAudit } from "./state";
import { Conf, Excerpt, ReviewBadge, RowTable, SourceLink, Stat } from "./parts";
import type { CalendarRow, ChangeRow, DiffRow, EnfRow, GapRow, Pack, Profile, RegisterRow } from "./types";

const ACTS: [string, string][] = [["deposits", "Deposits"], ["lending", "Lending"], ["digital_lending", "Digital lending"], ["forex", "Forex"],
  ["payments", "Payments"], ["priority_sector", "Priority-sector lending"], ["co_lending", "Co-lending"], ["outsourcing", "Outsourcing"],
  ["kyc_aml", "KYC / AML"], ["it_cyber", "IT / cyber"]];

function ProfileForm() {
  const { mode, setPack, refreshList } = useAudit();
  const [classes, setClasses] = useState<string[]>([]);
  const [p, setP] = useState<Profile>({ name: "My entity", entity_class: "Small Finance Banks", as_of: new Date().toISOString().slice(0, 10),
    last_review: "2025-12-01", activities: ["deposits", "lending", "kyc_aml", "outsourcing"], group_classes: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (mode === "live") void live.vocab().then((v) => setClasses(v.classes)).catch(() => {}); }, [mode]);
  const disabled = mode !== "live";
  return (
    <Card><CardBody>
      <form aria-label="Entity profile" className="grid gap-2 text-[12.5px] md:grid-cols-3" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true); setErr(null);
        try { setPack(await live.generate(p)); await refreshList(); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
      }}>
        <label className="flex flex-col gap-1">Name<input className="h-7 rounded-md border border-line bg-panel px-2" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></label>
        <label className="flex flex-col gap-1">Entity class
          <select className="h-7 rounded-md border border-line bg-panel px-2" value={p.entity_class} onChange={(e) => setP({ ...p, entity_class: e.target.value })}>
            {(classes.length ? classes : [p.entity_class]).map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">As of<input type="date" className="h-7 rounded-md border border-line bg-panel px-2" value={p.as_of} onChange={(e) => setP({ ...p, as_of: e.target.value })} /></label>
          <label className="flex flex-1 flex-col gap-1">Last review<input type="date" className="h-7 rounded-md border border-line bg-panel px-2" value={p.last_review} onChange={(e) => setP({ ...p, last_review: e.target.value })} /></label>
        </div>
        <fieldset className="md:col-span-2">
          <legend className="mb-1">Activities</legend>
          <div className="flex flex-wrap gap-x-3 gap-y-1">{ACTS.map(([id, label]) => (
            <label key={id} className="flex items-center gap-1"><input type="checkbox" checked={p.activities.includes(id)}
              onChange={(e) => setP({ ...p, activities: e.target.checked ? [...p.activities, id] : p.activities.filter((a) => a !== id) })} />{label}</label>))}</div>
        </fieldset>
        <label className="flex flex-col gap-1">Group entities (differential; hold Cmd/Ctrl)
          <select multiple className="h-16 rounded-md border border-line bg-panel px-2" value={p.group_classes}
            onChange={(e) => setP({ ...p, group_classes: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
            {classes.filter((c) => c !== p.entity_class).map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-2 md:col-span-3">
          <Button type="submit" disabled={disabled || busy}>{busy ? "Generating…" : "Generate audit pack"}</Button>
          {disabled && <span className="text-ink-3">Generating needs the local backend: <code>python3 scripts/auditgen.py serve</code>. Replay shows the sample packs.</span>}
          {err && <span className="text-neg">{err}</span>}
        </div>
      </form>
    </CardBody></Card>
  );
}

function MonthView({ rows, start }: { rows: CalendarRow[]; start: string }) {
  const [offset, setOffset] = useState(0);
  const d0 = new Date(start + "T00:00:00");
  const first = new Date(d0.getFullYear(), d0.getMonth() + offset, 1);
  const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const key = (d: number) => `${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const due = useMemo(() => {
    const m: Record<string, CalendarRow[]> = {};
    for (const r of rows) for (const d of r.next_due) (m[d] ??= []).push(r);
    return m;
  }, [rows]);
  const lead = (first.getDay() + 6) % 7;
  return (
    <div aria-label="Month view">
      <div className="mb-2 flex items-center gap-2 text-[12.5px]">
        <Button size="sm" variant="outline" onClick={() => setOffset(offset - 1)} disabled={offset <= 0}>‹</Button>
        <b>{first.toLocaleString("en-IN", { month: "long", year: "numeric" })}</b>
        <Button size="sm" variant="outline" onClick={() => setOffset(offset + 1)} disabled={offset >= 11}>›</Button>
        <span className="text-ink-3">Event-triggered deadlines cannot be dated and are listed below only.</span>
      </div>
      <div className="grid grid-cols-7 gap-px rounded-lg border border-line bg-line text-[11px]">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="bg-panel-2 px-1 py-0.5 text-ink-3">{d}</div>)}
        {Array.from({ length: lead }).map((_, i) => <div key={`l${i}`} className="min-h-14 bg-panel" />)}
        {Array.from({ length: days }).map((_, i) => {
          const items = due[key(i + 1)] ?? [];
          return (
            <div key={i} className="min-h-14 bg-panel p-1">
              <p className="num text-ink-3">{i + 1}</p>
              {items.slice(0, 3).map((r) => (
                <a key={r.entry_id} href={r.source_url} target="_blank" rel="noreferrer" title={`${r.summary} · ${r.paragraph_id}`}
                  className={`block truncate rounded px-0.5 ${r.verify ? "bg-warn-soft text-warn" : "bg-accent-soft text-accent"}`}>{r.verify ? "verify · " : ""}{r.summary}</a>
              ))}
              {items.length > 3 && <p className="text-ink-3">+{items.length - 3} more</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function RegisterTable({ pack }: { pack: Pack }) {
  const [showHidden, setShowHidden] = useState(false);
  const rows = showHidden ? pack.register : pack.register.filter((r) => !r.hidden);
  return (
    <div>
      <label className="mb-1 flex items-center gap-1 text-[12px] text-ink-3">
        <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
        show {pack.summary.register_hidden} hidden rows (filtered by activity, deleted or not yet in force; never removed)
      </label>
      <RowTable<RegisterRow> label="Applicability register" rows={rows}
        filterText={(r) => `${r.direction_title} ${r.excerpt} ${r.subject_family} ${r.paragraph_id} ${r.status}`}
        cols={[
          { key: "dir", label: "Direction · clause", className: "w-64", render: (r) => <div><p className="text-[12px]">{r.direction_title}</p><p className="text-ink-3">{r.section} {r.clause && `· ${r.clause}`}</p></div> },
          { key: "ex", label: "Obligation (excerpt ≤ 25 words)", render: (r) => <Excerpt text={r.excerpt} pid={r.paragraph_id} /> },
          { key: "st", label: "As-of status", render: (r) => <div><p>{r.status}</p>{r.amended_by.length > 0 && <p className="text-ink-3">amended by {r.amended_by.map((a) => <a key={a.id} className="text-accent" href={a.url} target="_blank" rel="noreferrer">{a.id} </a>)}</p>}<p className="text-ink-3">from {r.effective_from ?? "?"}</p></div> },
          { key: "dl", label: "Deadline / frequency", render: (r) => r.deadline_frequency || <span className="text-ink-3">–</span> },
          { key: "ap", label: "Applies to", render: (r) => <div><p>{r.applies_to}</p>{r.scope_note && <p className="text-warn">{r.scope_note}</p>}{r.hidden && <Badge tone="outline">{r.hidden_reason}</Badge>}</div> },
          { key: "c", label: "Conf.", render: (r) => <Conf v={r.confidence} /> },
          { key: "src", label: "Source", render: (r) => <div className="space-y-1"><SourceLink row={r} /><ReviewBadge row={r} /></div> },
        ]} />
    </div>
  );
}

export function GapTable({ rows }: { rows: GapRow[] }) {
  return (
    <RowTable<GapRow> label="Gap analysis" rows={rows} filterText={(r) => `${r.direction_title} ${r.excerpt} ${r.coverage}`}
      cols={[
        { key: "ob", label: "Obligation", render: (r) => <div><Excerpt text={r.excerpt} pid={r.paragraph_id} /><p className="text-ink-3">{r.direction_title}</p></div> },
        { key: "cov", label: "Coverage", render: (r) => <Badge tone={r.coverage === "covered" ? "pos" : r.coverage === "partial" ? "warn" : "neg"}>{r.coverage}</Badge> },
        { key: "c", label: "Conf.", render: (r) => <Conf v={r.confidence} /> },
        { key: "m", label: "Matched policy clause(s) and scores", render: (r) => r.matched_clauses.length ? (
          <ul className="space-y-1">{r.matched_clauses.map((c) => (
            <li key={c.clause_id}><p className="text-[12px]">“{c.excerpt}”</p><p className="num text-ink-3">{c.clause_id} · NLI entailment {c.entailment.toFixed(2)} · cosine {c.cosine.toFixed(2)}</p></li>))}
            {r.explanation && <li className="text-ink-2">Local LLM (NLI-verified): {r.explanation}</li>}</ul>
        ) : <span className="text-ink-3">no clause above threshold (best entailment {Math.max(...r.top_clauses.map((c) => c.entailment)).toFixed(2)})</span> },
        { key: "risk", label: "Enf. risk", render: (r) => <span className="num">{r.enforcement_risk}</span> },
        { key: "src", label: "Source", render: (r) => <div className="space-y-1"><SourceLink row={r} /><ReviewBadge row={r} /></div> },
      ]} />
  );
}

export function AboutBox({ pack }: { pack: Pack }) {
  const a = pack.about;
  const v = a.validation;
  const ci = (x?: number[]) => (x ? ` [${x[0]}, ${x[1]}]` : "");
  const items: [string, React.ReactNode][] = [
    ["Disclaimer", <b key="d">{a.disclaimer}</b>],
    ["Tool", `${a.tool} ${a.tool_version} · rules ${a.rules_version} (sha256 ${a.rules_sha256.slice(0, 12)}…)`],
    ["Corpus snapshot", `${a.corpus.kind} · ${a.corpus.snapshot_date} · sha256 ${a.corpus.sha256}`],
    ["Freshness", a.freshness.message], ["As of / last review", `${a.as_of} / ${a.last_review}`],
    ["Entity profile", `${a.entity_profile.name} · ${a.entity_profile.entity_class} · ${a.entity_profile.activities.join(", ")}${a.entity_profile.group_classes.length ? ` · group: ${a.entity_profile.group_classes.join(", ")}` : ""}`],
    ["Validation: applicability", `precision ${v.applicability.precision}${ci(v.applicability.precision_ci)}, recall ${v.applicability.recall}${ci(v.applicability.recall_ci)} vs T1 gold v1 (${v.applicability.units}). ${v.applicability.note ?? ""}`],
    ["Validation: temporal status", `accuracy ${v.temporal.accuracy}${ci(v.temporal.accuracy_ci)} on ${v.temporal.n_items} T3 items. ${v.temporal.note ?? ""}`],
    ["Validation: calendar extraction", v.calendar.status === "done" ? `precision ${v.calendar.precision} on ${v.calendar.n} checks` : `pending (${v.calendar.labelled ?? 0}/${v.calendar.n ?? 30} labelled). ${v.calendar.note ?? ""}`],
    ["Validation: gap analysis (synthetic)", `missing-recall ${v.gap_analysis.missing_recall}, missing-precision ${v.gap_analysis.missing_precision}; kept obligations marked covered ${v.gap_analysis.kept_marked_covered}. ${v.gap_analysis.note ?? ""}`],
    ["Caution: differential", v.differential.note ?? ""], ["Privacy", a.privacy], ["Excerpts", a.excerpt_rule],
    ["Rows dropped (no citation)", Object.entries(pack.dropped_without_citation ?? {}).map(([k, x]) => `${k}: ${x.count} (${x.md_ids.join(", ")})`).join("; ") || "none"],
    ["Sign-off", pack.signoff ? `${pack.signoff.signer} · ${pack.signoff.signed_utc} · ${pack.signoff.progress.reviewed}/${pack.signoff.progress.total} reviewed` : "not signed off"],
  ];
  return (
    <dl aria-label="About this pack" className="grid gap-x-4 gap-y-1.5 text-[12.5px] md:grid-cols-[220px_1fr]">
      {items.map(([k, val]) => <div key={k} className="contents"><dt className="font-medium text-ink-2">{k}</dt><dd className="min-w-0 break-words">{val}</dd></div>)}
    </dl>
  );
}

export default function AuditPack() {
  const { pack } = useAudit();
  return (
    <div>
      <PageHeader title="Audit pack" subtitle="Applicability register, change log, compliance calendar, cross-class differential, enforcement context and policy gaps, each row citing its RBI source." />
      <ProfileForm />
      {!pack && <p className="mt-4 text-[13px] text-ink-3">No pack loaded yet.</p>}
      {pack && <PackView pack={pack} />}
    </div>
  );
}

function PackView({ pack }: { pack: Pack }) {
  const s = pack.summary;
  return (
    <div className="mt-4">
      <h2 className="text-[15px] font-semibold">{pack.profile.name} · {pack.profile.entity_class} · as of {pack.profile.as_of}</h2>
      <div className="mt-2 grid gap-2 md:grid-cols-6">
        <Stat label="Applicable obligations" value={s.register_visible.toLocaleString()} />
        <Stat label="Need human review" value={s.needs_review.toLocaleString()} tone="warn" />
        <Stat label={`Changes since ${pack.profile.last_review}`} value={s.changes} />
        <Stat label="Calendar entries (verify)" value={`${s.calendar_entries} (${s.calendar_verify})`} />
        <Stat label="Differential rows (review)" value={`${s.differential_rows} (${s.differential_needs_review})`} />
        <Stat label="Penalty releases (class)" value={s.enforcement_releases} />
      </div>
      <Tabs defaultValue="register" className="mt-4">
        <TabsList>
          {["register", "changes", "calendar", "differential", "enforcement", "gaps", "about"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="register" className="pt-3"><RegisterTable pack={pack} /></TabsContent>
        <TabsContent value="changes" className="pt-3">
          <RowTable<ChangeRow> label="Change-impact log" rows={pack.changes} filterText={(r) => `${r.direction_title} ${r.change} ${r.governing_instrument}`}
            cols={[
              { key: "d", label: "Direction", className: "w-64", render: (r) => r.direction_title },
              { key: "ch", label: "Change", render: (r) => <div><p>{r.change}</p><Excerpt text={r.excerpt} pid={r.paragraph_id} /></div> },
              { key: "gi", label: "Governing instrument", render: (r) => <a className="text-accent" href={r.governing_url} target="_blank" rel="noreferrer">{r.governing_instrument}</a> },
              { key: "e", label: "Effective", render: (r) => r.effective ?? "?" },
              { key: "src", label: "Source", render: (r) => <div className="space-y-1"><SourceLink row={r} /><ReviewBadge row={r} /></div> },
            ]} />
        </TabsContent>
        <TabsContent value="calendar" className="space-y-4 pt-3">
          <MonthView rows={pack.calendar} start={pack.profile.as_of} />
          <RowTable<CalendarRow> label="Compliance calendar" rows={pack.calendar} filterText={(r) => `${r.summary} ${r.phrase}`}
            cols={[
              { key: "n", label: "Next due", render: (r) => r.next_due.slice(0, 2).join(", ") || <span className="text-ink-3">event-triggered</span> },
              { key: "w", label: "What", render: (r) => <div><p>{r.summary}</p><p className="text-ink-3">“{r.phrase}”</p></div> },
              { key: "c", label: "Conf.", render: (r) => <span><Conf v={r.confidence} /> {r.verify && <Badge tone="warn">verify</Badge>}</span> },
              { key: "src", label: "Source", render: (r) => <SourceLink row={r} /> },
            ]} />
        </TabsContent>
        <TabsContent value="differential" className="pt-3">
          {pack.differential.length === 0 ? <p className="text-[13px] text-ink-3">Add group entities to the profile to compare classes.</p> : <>
            <p className="mb-2 rounded-md bg-warn-soft p-2 text-[12.5px] text-warn">{pack.differential_caution}</p>
            <RowTable<DiffRow> label="Cross-class differential" rows={pack.differential} filterText={(r) => `${r.differential} ${r.target_class} ${r.direction_title} ${r.excerpt}`}
              cols={[
                { key: "cl", label: "Classes", render: (r) => `${r.source_class} → ${r.target_class}` },
                { key: "ob", label: "Obligation", render: (r) => <Excerpt text={r.excerpt} pid={r.paragraph_id} /> },
                { key: "dc", label: "Call", render: (r) => <Badge tone={r.differential === "shared" ? "neutral" : "warn"}>{r.differential}</Badge> },
                { key: "cp", label: "Counterpart", render: (r) => r.counterpart_paragraph_id ? <div><a className="text-accent" href={r.counterpart_url ?? "#"} target="_blank" rel="noreferrer">{r.counterpart_paragraph_id}</a><p className="text-ink-3">{r.counterpart_excerpt}</p></div> : "–" },
                { key: "s", label: "Score", render: (r) => <Conf v={r.confidence} /> },
                { key: "src", label: "Source", render: (r) => <div className="space-y-1"><SourceLink row={r} /><ReviewBadge row={r} /></div> },
              ]} /></>}
        </TabsContent>
        <TabsContent value="enforcement" className="pt-3">
          <p className="mb-2 rounded-md bg-panel-2 p-2 text-[12.5px]">{pack.enforcement_label}</p>
          <RowTable<EnfRow> label="Enforcement-risk view" rows={pack.enforcement}
            cols={[
              { key: "d", label: "Direction", render: (r) => r.direction_title },
              { key: "n", label: "Penalties", render: (r) => <span className="num">{r.penalty_count}</span> },
              { key: "dt", label: "Dates", render: (r) => `${r.first_date ?? "?"} – ${r.last_date ?? "?"}` },
              { key: "pr", label: "Press releases", render: (r) => <ul>{r.press_releases.slice(0, 4).map((p) => <li key={p.id}><a className="text-accent" href={p.url} target="_blank" rel="noreferrer">{p.date} {p.amount ?? ""}</a></li>)}{r.press_releases.length > 4 && <li className="text-ink-3">+{r.press_releases.length - 4} more</li>}</ul> },
              { key: "b", label: "Link", render: (r) => <span className="text-ink-3">{r.link_note} {r.link_basis.join("; ")}</span> },
              { key: "src", label: "Source", render: (r) => <SourceLink row={r} /> },
            ]} />
        </TabsContent>
        <TabsContent value="gaps" className="pt-3">
          {pack.gaps ? <GapTable rows={pack.gaps.rows} /> : <p className="text-[13px] text-ink-3">No policy gap analysis yet: use the Policy gaps page.</p>}
        </TabsContent>
        <TabsContent value="about" className="pt-3"><AboutBox pack={pack} /></TabsContent>
      </Tabs>
    </div>
  );
}

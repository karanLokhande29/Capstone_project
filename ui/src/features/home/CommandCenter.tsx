import { Link } from "react-router-dom";
import { ArrowRight, CircleAlert, CircleCheck, CircleDot } from "lucide-react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { Badge, Card, CardBody, CardHeader, CardTitle } from "@/components/ui/primitives";
import { CICell } from "@/components/CICell";
import { CaveatChips } from "@/components/CaveatChip";
import { Num } from "@/components/Provenance";
import { PageHeader } from "@/components/Page";
import { r10Freeze, r11Deadline } from "@/intelligence/rules";
import { useNow } from "@/app/Countdown";
import { resolveKey } from "@/lib/keys";
import { fmtInt } from "@/lib/utils";

const PHASES = [
  { id: "Phase 0–1", label: "Audit, corpus QA, matrix, pilot" }, { id: "P1-004", label: "Full Direction set" },
  { id: "P2-001…004", label: "Candidates, matching, sources, gold v1" }, { id: "P3-001/002", label: "T2 sets, baselines, T4 audit" },
  { id: "P4-001", label: "Pipeline, T3, ablations, long-context" }, { id: "P5-001", label: "Results, release, error analysis" },
  { id: "Final push", label: "Comparator freeze, Phase 4 scoring, MD + paper" }, { id: "Part A", label: "MD v2, A1–A16" },
  { id: "Submission", label: "Prose rewrite → CMT 10 Oct" },
];

function FixtureHome() {
  const s = useData((st) => st.snapshot)!;
  return (
    <div>
      <PageHeader title="Command Center (synthetic fixture)" subtitle="FixtureAdapter: only headline numbers printed in Master Document v2. Run `cd ui && npm run ingest` for the real snapshot." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {s.findings.map((f) => (
          <Card key={f.id}><CardBody className="space-y-2"><p className="text-[13px] font-medium">{f.id} {f.statement}</p>
            {f.ci && <CICell point={f.delta!} ci={f.ci} label={f.ciLabel} sourceKey={f.sourceKey} signed compact />}</CardBody></Card>
        ))}
      </div>
    </div>
  );
}

export function CommandCenter() {
  const fixture = useData((st) => st.snapshot?.meta.fixture);
  return fixture ? <FixtureHome /> : <RealCommandCenter />;
}

function RealCommandCenter() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const open = useDrawer((st) => st.open);
  const now = useNow();
  const R = s.results;
  const n = (k: string) => resolveKey(R, k) as number;
  const openTasks = s.submissionTasks.filter((t) => t.status !== "done");
  const r11 = r11Deadline(openTasks, now);
  const placeholders = s.placeholders.filter((p) => p.kind === "placeholder");
  const freeze = r10Freeze(s.frozen);
  const PRI = ["conflicting", "missing", "needs_validation"];
  const wrong = s.gaps.filter((g) => PRI.includes(g.status)).sort((a, b) => PRI.indexOf(a.status) - PRI.indexOf(b.status)).slice(0, 5);
  const musts = s.recommendations.filter((r) => r.tier === "REQUIRED").slice(0, 3);
  const opps = s.recommendations.filter((r) => r.tier === "NEW_OPPORTUNITY");
  const m2 = model?.models.M2.eval;
  const SHORT: Record<string, string> = { "ST-CMT": "Submit on CMT", "ST-PDF": "Final PDF", "ST-DOI": "Zenodo DOI", "ST-OVERLEAF": "page check",
    "ST-AUDIT": "number audit", "ST-AUTHOR-EMAILS": "author emails", "ST-SIMILARITY": "similarity check", "ST-PROSE": "prose rewrite", "ST-REPRO": "repro check" };
  const open_ = new Set(openTasks.map((t) => t.id));
  const pdf = s.submissionTasks.find((t) => t.id === "ST-PDF");
  const chain: string[] = [
    ...(open_.has("ST-CMT") ? [SHORT["ST-CMT"]] : []), ...(pdf && open_.has("ST-PDF") ? [SHORT["ST-PDF"]] : []),
    (pdf?.dependsOn ?? []).filter((x) => open_.has(x) && x !== "ST-SIMILARITY").map((x) => SHORT[x] ?? x).join(" + "),
    ...(open_.has("ST-PROSE") ? [SHORT["ST-PROSE"]] : []),
  ].filter(Boolean);
  return (
    <div>
      {freeze.verdict === "fail" && <div className="mb-3 rounded-md border border-neg bg-neg-soft px-3 py-2 text-sm text-neg">R10: {freeze.reason}</div>}
      <PageHeader title="Command Center"
        subtitle={<>RBI-ObliBench: a benchmark on {fmtInt(n("tables.01_corpus.directions"))} RBI Master Directions. <b>The benchmark is the contribution; the class- and date-aware pipeline is the engineering artefact evaluated on it.</b></>} />

      <Card className="mb-4">
        <CardBody className="grid gap-3 md:grid-cols-3">
          {d.rqs.map((r) => (
            <Link key={r.id} to={`/rq/${r.id}`} className="group rounded-md p-1 hover:bg-panel-2">
              <p className="flex items-center gap-2 text-[12px] font-semibold">{r.id} · {r.label}
                <Badge tone={r.answeredStatus === "answered" ? "pos" : "warn"}>{r.answeredStatus}</Badge></p>
              <p className="mt-1 line-clamp-3 text-[12.5px] text-ink-2">{r.text}</p>
            </Link>
          ))}
        </CardBody>
      </Card>

      <h2 className="mb-2 text-[14px] font-semibold">Seven headline findings</h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {s.findings.map((f) => (
          <Card key={f.id} className="flex flex-col">
            <CardBody className="flex flex-1 flex-col gap-2">
              <button type="button" onClick={() => open(`finding:${f.id}`)} className="cursor-pointer text-left text-[13px] font-medium leading-snug hover:text-accent">
                <span className="mr-1 text-ink-3">{f.id}</span>{f.statement}
              </button>
              <div className="mt-auto space-y-1.5">
                {f.ci ? <CICell point={f.delta!} ci={f.ci} label={f.ciLabel} sourceKey={f.sourceKey} signed compact onOpen={() => open(`finding:${f.id}`)} />
                  : <p className="text-[12px]"><Num value={`${f.count} of ${n("phase4.missed_by_every_llm_system.gold_different_units")}`} sourceKey={f.sourceKey} /> units (def. A);
                    {" "}<Num value={n("phase4.missed_by_every_llm_system.B_answered_only.missed")} sourceKey="phase4.missed_by_every_llm_system.B_answered_only.missed" /> (def. B)</p>}
                <CaveatChips ids={f.caveatIds} />
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Where are we?</CardTitle><Link to="/readiness" className="text-[12px] text-accent">readiness →</Link></CardHeader>
          <CardBody>
            <ol className="space-y-1 text-[12.5px]">
              {PHASES.map((p, i) => (
                <li key={p.id} className="flex items-start gap-2">
                  {i < PHASES.length - 1 ? <CircleCheck size={14} className="mt-0.5 shrink-0 text-pos" /> : <CircleDot size={14} className="mt-0.5 shrink-0 text-warn" />}
                  <span><b>{p.id}</b> <span className="text-ink-3">{p.label}</span></span>
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What have we built?</CardTitle></CardHeader>
          <CardBody className="space-y-1.5 text-[12.5px]">
            <p>Corpus: <Num value={fmtInt(n("tables.01_corpus.directions"))} sourceKey="tables.01_corpus.directions" /> Directions,{" "}
              <Num value={fmtInt(n("tables.01_corpus.paragraphs"))} sourceKey="tables.01_corpus.paragraphs" /> paragraphs</p>
            <p>4 tasks: T1 <Num value={n("tables.05_t1_benchmark.validated")} sourceKey="tables.05_t1_benchmark.validated" /> items · T2 3 sets · T3{" "}
              <Num value={n("tables.08_t3.scored")} sourceKey="tables.08_t3.scored" /> · T4 <Num value={n("tables.09_t4.n_questions")} sourceKey="tables.09_t4.n_questions" /> questions</p>
            <p>8 T1 systems · 5 retrievers · 3 ablations (A class filter, B temporal filter, C verifier)</p>
            <p>Pointer-only release (<code>release/</code>) · Master Document v2 · paper draft</p>
            <p className="text-ink-3">Nav: <Link className="text-accent" to="/construction">construction</Link> · <Link className="text-accent" to="/workspace/results">results</Link></p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What are we building?</CardTitle></CardHeader>
          <CardBody>
            <ul className="space-y-1.5 text-[12.5px]">
              {openTasks.slice(0, 4).map((t, i) => (
                <li key={t.id} className="flex gap-2"><span className="num w-12 shrink-0 text-ink-3">{t.due.slice(5)}</span>
                  <span className={r11[i].verdict === "fail" ? "text-neg" : r11[i].verdict === "warn" ? "text-warn" : ""}>{t.title}</span></li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What is left?</CardTitle></CardHeader>
          <CardBody className="space-y-1.5 text-[12.5px]">
            <p><b>{openTasks.length}</b> open submission tasks until CMT</p>
            <p><b>{placeholders.length}</b> placeholders in main.tex ({placeholders.map((p) => p.text.replace("\\placeholder", "")).join(", ")})</p>
            <p><b>{s.futureWork.length}</b> Future Work items after submission</p>
            <p><b>{s.gaps.filter((g) => g.status !== "complete").length}</b> open gaps of {s.gaps.length}</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What is blocked?</CardTitle></CardHeader>
          <CardBody className="text-[12.5px]">
            <p className="flex flex-wrap items-center gap-1">{chain.map((c, i) => <span key={c} className="inline-flex items-center gap-1">{i > 0 && <span className="text-ink-3">←</span>}<span className="rounded bg-panel-2 px-1.5 py-0.5">{c}</span></span>)}</p>
            <p className="mt-2 text-ink-3">The final PDF also waits on the similarity check (screened at submission).</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What is wrong?</CardTitle><Link to="/gaps" className="text-[12px] text-accent">all gaps →</Link></CardHeader>
          <CardBody>
            <ul className="space-y-1.5 text-[12.5px]">
              {wrong.map((g) => (
                <li key={g.id}><button type="button" onClick={() => open(`gap:${g.id}`)} className="cursor-pointer text-left hover:text-accent">
                  <CircleAlert size={12} className="mr-1 inline text-warn" /><b>{g.id}</b> {g.actual}</button>
                  <span className="block pl-4 text-ink-3">{g.reasonDetected}</span></li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What next?</CardTitle></CardHeader>
          <CardBody>
            <ol className="space-y-2 text-[12.5px]">
              {musts.map((r, i) => (<li key={r.id}><b>{i + 1}. {r.title}</b><span className="block text-ink-3">Why: {r.why}. Unblocks: {r.unblocks.join(", ") || "—"}</span></li>))}
            </ol>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>What can this become?</CardTitle><Badge tone="product">NEW OPPORTUNITY</Badge></CardHeader>
          <CardBody className="space-y-1.5 text-[12.5px]">
            {opps.map((o) => <p key={o.id}>{o.title}</p>)}
            {m2 && <p className="text-ink-3">Comparator confidence (M2, frozen on dev): High band {m2.operatingPoint.answered}/{m2.nUnits} units, {((m2.operatingPoint.accuracy ?? 0) * 100).toFixed(1)}% correct — mostly `same` verdicts.</p>}
            <Link to="/product" className="inline-flex items-center gap-1 text-product">Product showcase <ArrowRight size={12} /></Link>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

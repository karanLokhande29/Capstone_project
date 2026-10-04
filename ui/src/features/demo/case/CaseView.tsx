import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { create } from "zustand";
import { ArrowLeft, ArrowRight, FlaskConical, PencilLine, Radio } from "lucide-react";
import { Button, Tip } from "@/components/ui/primitives";
import { LoadingPage } from "@/components/Page";
import { liveAvailable, presenter, useApi } from "../api";
import { StatusBadge } from "../badges";
import { caseHref, useCase, useIndex } from "../data";
import { ALL_SYSTEMS, FIELD_LABEL } from "../names";
import type { Field, SystemId } from "../types";
import { ConfidenceBlock, DecisionTrace, Microscope, ParagraphCards, PredictionsStrip, ProvenanceDrawer, VerdictPill } from "./parts";
import { XRay } from "./XRay";

/** The ordered list "Next case" walks through: set by Explore / Failure Map / Play; defaults to the cases index. */
export const useCaseNav = create<{ ids: string[] | null; label: string | null; set: (ids: string[], label: string) => void }>((set) => ({
  ids: null, label: null, set: (ids, label) => set({ ids, label }),
}));

export default function CaseView() {
  const { unitId: raw } = useParams();
  const unitId = raw ? decodeURIComponent(raw) : null;
  const [sp, setSp] = useSearchParams();
  const sys = (ALL_SYSTEMS as string[]).includes(sp.get("system") ?? "") ? (sp.get("system") as SystemId) : null;
  const c = useCase(unitId);
  const index = useIndex().data;
  const nav = useCaseNav();
  const api = useApi();
  const navigate = useNavigate();
  const [field, setField] = useState<Field | null>(null);
  useEffect(() => setField(null), [unitId]);
  const order = useMemo(() => nav.ids ?? index?.units.map((u) => u.id) ?? [], [nav.ids, index]);
  if (c.error) return <div className="pt-10"><p className="text-[15px]">This case could not be loaded: {c.error}</p><Link className="text-accent" to="/cases">Back to cases</Link></div>;
  if (!c.data) return <LoadingPage />;
  const { unit, shard } = c.data;
  const i = order.indexOf(unit.id);
  const next = i >= 0 && i < order.length - 1 ? order[i + 1] : order[0];
  const prev = i > 0 ? order[i - 1] : null;
  const row = field ? unit.comparator.rows.find((r) => r.field === field) : null;
  const cmp = unit.predictions.comparator;

  return (
    <div className="pt-6 sm:pt-8">
      <p className="text-[13px]"><Link to="/cases" className="inline-flex items-center gap-1 text-ink-3 hover:text-ink"><ArrowLeft size={14} />Cases</Link></p>
      <header className="mt-3">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">{unit.topic ?? "Topic not recorded"}</p>
        <h1 className="mt-1 text-[24px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[30px]">{unit.sourceClass} → {unit.targetClass}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-2">
          <StatusBadge status="sealed" />
          <Tip content="How the expert label was reached: single pass, confirmed on a retest, or adjudicated after disagreement."><span className="cursor-help rounded-full border border-line px-2 py-0.5">Gold route: {unit.route}</span></Tip>
          {unit.missedA && <span className="rounded-full border border-warn/50 bg-warn-soft px-2 py-0.5 text-warn">All five LLM systems missed this difference</span>}
          <span className="font-mono text-[11px] text-ink-3">{unit.id}</span>
        </div>
      </header>

      <section className="mt-5" aria-labelledby="paras"><h2 id="paras" className="sr-only">The two paragraphs</h2>
        <ParagraphCards unit={unit} pointers={shard.pointers} api={api} highlight={row ? { source: row.sourceValue, target: row.targetValue } : null} />
      </section>

      <section className="mt-6" aria-labelledby="preds">
        <h2 id="preds" className="mb-2 text-[15px] font-semibold">What each system said</h2>
        <PredictionsStrip unit={unit} selected={sys} onSelect={(s) => { const n = new URLSearchParams(sp); n.set("system", s); setSp(n, { replace: true }); }} />
        {sys && sys !== "comparator" && <XRay unit={unit} system={sys} pointers={shard.pointers} />}
      </section>

      <section className="mt-8" aria-labelledby="micro">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="micro" className="text-[15px] font-semibold">The structured comparator, field by field</h2>
          <span className="flex items-center gap-2 text-[13px]">Verdict <VerdictPill j={cmp.judgement ?? (cmp.status === "abstained" ? "abstain" : undefined)} /></span>
        </div>
        <Microscope unit={unit} selected={field} onSelect={setField} />
        {row && <p className="mt-2 text-[12.5px] text-ink-2">Selected: <b>{FIELD_LABEL[row.field]}</b>.</p>}
        <div className="mt-4"><DecisionTrace unit={unit} ruleSha={String(unit.provenance.rule_sha256)} /></div>
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" aria-label="Confidence and provenance">
        <div><h2 className="mb-2 text-[15px] font-semibold">How much to trust the comparator here</h2><ConfidenceBlock unit={unit} /></div>
        <div>
          <h2 className="mb-2 text-[15px] font-semibold">Check it yourself</h2>
          <div className="flex flex-wrap gap-2">
            <ProvenanceDrawer unit={unit} pointers={shard.pointers} api={api} />
            {liveAvailable(api)
              ? <Button variant="outline" onClick={() => navigate(`/lab?unit=${encodeURIComponent(unit.id)}`)}><Radio size={15} />Re-run live</Button>
              : <Tip content={api.status === "checking" ? "Checking the comparator API…" : "Live service unavailable for this site (no model key or no backend). The sealed output above is the benchmark result."}><span><Button variant="outline" disabled><Radio size={15} />Re-run live</Button></span></Tip>}
            {presenter(api) && liveAvailable(api)
              ? <Button variant="outline" onClick={() => navigate(`/lab/edit?unit=${encodeURIComponent(unit.id)}`)}><PencilLine size={15} />Try an edit</Button>
              : <Tip content="The edit lab runs only in local / presenter mode. The public site explains it read-only."><span><Button variant="outline" onClick={() => navigate("/lab/edit")}><FlaskConical size={15} />How edits work</Button></span></Tip>}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {prev && <Link to={caseHref(prev, sys ?? undefined)}><Button variant="ghost"><ArrowLeft size={15} />Previous</Button></Link>}
            {next && <Link to={caseHref(next, sys ?? undefined)}><Button><span>Next case</span><ArrowRight size={15} /></Button></Link>}
          </div>
          {nav.label && <p className="mt-1 text-[12px] text-ink-3">Walking through: {nav.label} ({i + 1} of {order.length})</p>}
        </div>
      </section>
    </div>
  );
}

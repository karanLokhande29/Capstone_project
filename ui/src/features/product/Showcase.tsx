import { Link } from "react-router-dom";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, FileSearch, Fingerprint, GitCompare, Layers, ShieldCheck, Timer } from "lucide-react";
import { useData } from "@/data/store";
import { useDrawer } from "@/components/drawerState";
import { Badge, Button, Card, CardBody, Tip } from "@/components/ui/primitives";
import { r10Freeze, r14Confidence, r3Circularity } from "@/intelligence/rules";
import { excludesZero } from "@/lib/ci";
import { resolveKey } from "@/lib/keys";
import { fmtInt, pct } from "@/lib/utils";

function Fn({ caveat, sourceKey }: { caveat?: string; sourceKey: string }) {
  const c = useData((s) => (caveat ? s.snapshot?.caveats.find((x) => x.id === caveat) : undefined));
  const open = useDrawer((s) => s.open);
  return (
    <Tip content={<span className="block max-w-xs">{c?.text ?? "Read from the project record."}<span className="mt-1 block text-ink-3">source: {sourceKey}</span></span>}>
      <button type="button" aria-label={`Footnote: ${caveat ?? sourceKey}`} onClick={() => caveat && open(`caveat:${caveat}`)}
        className="ml-0.5 cursor-pointer align-super text-[10px] font-semibold text-product">†</button>
    </Tip>
  );
}

function Claim({ icon: Icon, title, children, node }: { icon: typeof Layers; title: string; children: React.ReactNode; node: string }) {
  const open = useDrawer((s) => s.open);
  return (
    <Card className="flex flex-col"><CardBody className="flex flex-1 flex-col gap-2">
      <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-md bg-product-soft text-product"><Icon size={16} /></span><h3 className="text-[14px] font-semibold">{title}</h3></div>
      <div className="flex-1 text-[13px] leading-relaxed text-ink-2">{children}</div>
      <Button variant="outline" size="sm" className="self-start" onClick={() => open(node, "evidence")}>View the evidence</Button>
    </CardBody></Card>
  );
}

export default function Showcase() {
  const s = useData((st) => st.snapshot)!;
  const model = useData((st) => st.confidence);
  const R = s.results;
  const n = (k: string) => resolveKey(R, k) as number;
  const v = (k: string) => (resolveKey(R, k) as { value: number }).value;
  const caware = (resolveKey(R, "tables.06_t2_retrieval.p3001.t2_xclass_t1.systems.class_aware.ndcg") as { mean: number }).mean;
  const rrf = (resolveKey(R, "tables.06_t2_retrieval.p3001.t2_xclass_t1.systems.hybrid_rrf.ndcg") as { mean: number }).mean;
  // "Leads every system" is shown only where the point estimate really is the maximum (checked here, not asserted).
  const lead = (["flag_macro_f1", "collapsed_macro_f1", "judgement_macro_f1"] as const).map((m) => {
    const cmpV = v(`phase4.comparator.metrics.${m}`);
    const others = Object.keys(resolveKey(R, "phase4.t1_systems") as object).map((x) => v(`phase4.t1_systems.${x}.${m}`));
    return { m, value: cmpV, leads: others.every((o) => cmpV > o) };
  });
  const diffF1 = n("phase4.comparator.different.different_f1");
  const diffLeads = Object.keys(resolveKey(R, "phase4.t1_systems") as object).every((x) => diffF1 > n(`phase4.t1_different.${x}.different_f1`));
  const pre = resolveKey(R, "phase4.preregistered_comparisons.comparator − class_aware.judgement.different_f1") as { diff: number; ci: [number, number] };
  const t3on = s.metrics.find((m) => m.datasetId === "t3" && m.systemId === "temporal_filter_on")!;
  const t3blocked = r3Circularity(t3on).blockShowcase;
  const m2 = model?.models.M2;
  const high = m2?.eval.bands.find((b) => b.band === "High");
  const showConfidence = !!m2 && !m2.eval.experimental && r14Confidence(high).verdict === "ok";
  const comp = m2?.eval.bandComposition.High ?? {};
  const freeze = r10Freeze(s.frozen);
  const concat = resolveKey(R, "tables.09_t4.paired.concatenated - genuine.composite_score") as { mean: number; ci_low: number; ci_high: number };
  const labels: Record<string, string> = { flag_macro_f1: "3-way flag F1", collapsed_macro_f1: "collapsed F1", judgement_macro_f1: "judgement macro-F1" };
  const relData = (m2?.eval.reliability ?? []).filter((b) => b.n > 0).map((b) => ({ conf: Number(b.meanConfidence!.toFixed(3)), acc: Number(b.accuracy!.toFixed(3)), n: b.n }));
  const curve = (m2?.eval.selectiveCurve ?? []).map((c) => ({ coverage: Number(c.coverage.toFixed(3)), accuracy: Number(c.accuracy.toFixed(3)) }));

  return (
    <div className="pb-6">
      <section className="rounded-xl border border-line bg-gradient-to-br from-product-soft to-panel px-5 py-8 sm:px-8">
        <Badge tone="product">Product view · separate from research results</Badge>
        <h1 className="mt-3 max-w-3xl text-[26px] font-semibold leading-tight tracking-tight sm:text-[30px]">
          Entity-class-aware compliance intelligence for RBI Master Directions
        </h1>
        <p className="mt-3 max-w-2xl text-[15px] text-ink-2">It tells you what applies to <b>your</b> class, what's different from others, and when to trust the answer.</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Link to="/explorer"><Button variant="product">Try the Obligation Explorer <ArrowRight size={14} /></Button></Link>
          <Link to="/tour"><Button variant="outline">Reviewer tour</Button></Link>
        </div>
        <p className="mt-6 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-ink-2">
          <span><b className="num text-ink">{fmtInt(n("tables.01_corpus.directions"))}</b><Fn sourceKey="tables.01_corpus.directions" /> Directions</span>
          <span><b className="num text-ink">{fmtInt(n("tables.01_corpus.paragraphs"))}</b><Fn sourceKey="tables.01_corpus.paragraphs" /> paragraphs</span>
          <span><b className="num text-ink">{n("tables.01_corpus.entity_classes")}</b><Fn sourceKey="tables.01_corpus.entity_classes" /> entity classes</span>
          <span><b className="num text-ink">{n("tables.01_corpus.subject_families")}</b><Fn sourceKey="tables.01_corpus.subject_families" /> subject families</span>
        </p>
      </section>

      <h2 className="mb-3 mt-8 text-[17px] font-semibold">The problem</h2>
      <p className="max-w-3xl text-[14px] text-ink-2">The same subject is regulated differently for a commercial bank, a small finance bank, a co-operative bank or an NBFC: a threshold, a deadline or a carve-out changes. RBI consolidates amendments in place, so the text you read today may not be the text that applied on a past date. Generic search returns a similar paragraph and calls it the same.</p>

      <h2 className="mb-3 mt-8 text-[17px] font-semibold">Proof points</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Claim icon={Layers} title="Finds the right counterpart obligation" node="finding:F1">
          Class-aware retrieval reaches nDCG@10 <b className="num text-ink">{caware.toFixed(3)}</b><Fn caveat="by_construction" sourceKey="tables.06_t2_retrieval.p3001.t2_xclass_t1.systems.class_aware.ndcg" /> vs{" "}
          <b className="num">{rrf.toFixed(3)}</b><Fn caveat="bias_t2_xclass_t1" sourceKey="tables.06_t2_retrieval.p3001.t2_xclass_t1.systems.hybrid_rrf.ndcg" /> for standard hybrid search on <code>t2_xclass_t1</code>.
        </Claim>
        <Claim icon={GitCompare} title="Best-in-benchmark differential reasoning" node="finding:F7">
          The structured comparator {lead.some((l) => l.leads) ? "has the highest point estimate of every system on " : "is reported on "}
          {lead.filter((l) => l.leads).map((l, i) => <span key={l.m}>{i ? ", " : ""}{labels[l.m]} (<b className="num text-ink">{l.value.toFixed(3)}</b><Fn caveat="scoring_asymmetry" sourceKey={`phase4.comparator.metrics.${l.m}`} />)</span>)}
          {diffLeads && <> and <code>different</code> F1 (<b className="num text-ink">{diffF1.toFixed(3)}</b><Fn caveat="no_ci_different_f1" sourceKey="phase4.comparator.different.different_f1" />)</>}
          <Fn caveat="single_expert" sourceKey="phase4.comparator.metrics" />. On finding <i>what's different</i> it beats the class-aware LLM by{" "}
          <b className="num text-ink">+{pre.diff.toFixed(3)}</b> <code>different</code> F1{excludesZero(pre.ci[0], pre.ci[1]) && " (CI excludes 0)"}
          <Fn caveat="candidates_shown" sourceKey="phase4.preregistered_comparisons.comparator − class_aware.judgement.different_f1" />. Point estimates; some pairwise CIs include 0.
        </Claim>
        <Claim icon={FileSearch} title="Explainable by design" node="system:comparator">
          A 13-field side-by-side diff (actor, scope, threshold, deadline, exception …). The verdict comes from a fixed, frozen rule (same &gt; different &gt; none), not model guesswork.
        </Claim>
        {showConfidence && high && (
          <Claim icon={ShieldCheck} title="Knows when to trust itself" node="system:comparator">
            Answering only at High confidence, the comparator is correct <b className="num text-ink">{pct(high.accuracy)}</b> [{pct(high.wilsonCI![0])}, {pct(high.wilsonCI![1])}] of the time on{" "}
            <b className="num text-ink">{pct(m2!.eval.operatingPoint.coverage)}</b><Fn caveat="single_expert" sourceKey="confidence_model_v1.json → models.M2.eval.operatingPoint" /> of benchmark units<Fn caveat="calibration" sourceKey="ui/src/data/confidence_model_v1.json → models.M2.eval" />;
            the rest goes to a human. Model M2: fitted on the 30-item dev set, frozen before the gold evaluation. Honest limit: the High band is almost entirely
            "same obligation" verdicts ({comp.same?.n ?? 0} same, {comp.none?.n ?? 0} none, {comp.different?.n ?? 0} different), so claimed <i>differences</i> are routed to review.
          </Claim>
        )}
        <Claim icon={Timer} title="Date-aware" node="paired:t3:status">
          Without the temporal filter, the LLM answered "in force, original" on <b className="num text-ink">{n("tables.08_t3.t3.off.pred_status.in_force_original")}</b> of{" "}
          <b className="num">{n("tables.08_t3.t3.off.n")}</b><Fn caveat="flash_lite" sourceKey="tables.08_t3.t3.off.n" /> dated questions, and got only{" "}
          <b className="num text-ink">{Math.round(n("tables.08_t3.t3.off.by_side.after.status_exact_match") * n("tables.08_t3.t3.off.by_side.after.n"))}</b> of{" "}
          <b className="num">{n("tables.08_t3.t3.off.by_side.after.n")}</b> right once the paragraph had been amended or deleted<Fn caveat="amended_text_only" sourceKey="tables.08_t3.t3.off.by_side.after" />.
          That is the problem the product solves. {t3blocked && <span className="text-ink-3">(The filter-on score is circular by construction and is not shown.)</span>}
        </Claim>
        <Claim icon={Fingerprint} title="Audit-ready" node="decision:comparator_freeze">
          Every answer carries a paragraph pointer, a source URL, a harvest date and a sha256. Prompts and the decision rule are frozen and hash-verified
          ({freeze.verdict === "ok" ? `all ${s.frozen.length} artefacts match` : "MISMATCH — see provenance"}).
        </Claim>
        <Claim icon={ShieldCheck} title="Tested against gamed metrics" node="finding:F6">
          We showed that a popular faithfulness metric (RePASs) can be gamed by concatenation (<b className="num text-ink">+{concat.mean.toFixed(3)}</b>
          <Fn caveat="small_n_t4" sourceKey="tables.09_t4.paired.concatenated - genuine.composite_score" />), so our evaluation does not rely on it blindly.
        </Claim>
      </div>

      <h2 className="mb-3 mt-8 text-[17px] font-semibold">How it works</h2>
      <Card><CardBody className="flex flex-wrap items-center gap-2 text-[12.5px]">
        {["Your class + question + date", "Class filter", "Temporal filter", "BM25 + dense → RRF", "13-field comparator", "Frozen rule", "Calibrated confidence", "Pointer + verdict"].map((x, i) => (
          <span key={x} className="inline-flex items-center gap-2">{i > 0 && <ArrowRight size={13} className="text-ink-3" />}<span className="rounded-md border border-line bg-panel-2 px-2 py-1">{x}</span></span>
        ))}
        <Link to="/architecture" className="ml-auto text-product">Full architecture →</Link>
      </CardBody></Card>

      {showConfidence && m2 && (
        <>
          <h2 className="mb-3 mt-8 text-[17px] font-semibold">Trust: our confidence means what it says</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <Card><CardBody>
              <p className="mb-1 text-[13px] font-medium">Reliability diagram (model M2, gold v1, {m2.eval.nUnits} units)</p>
              <div className="h-56"><ResponsiveContainer>
                <ComposedChart data={relData} margin={{ left: -18, right: 8, top: 6 }}>
                  <CartesianGrid stroke="var(--line)" />
                  <XAxis dataKey="conf" type="number" domain={[0, 1]} tick={{ fontSize: 10, fill: "var(--ink-3)" }} label={{ value: "predicted", fontSize: 10, fill: "var(--ink-3)", position: "insideBottom", offset: -2 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: "var(--ink-3)" }} />
                  <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", fontSize: 12 }} />
                  <Line data={[{ conf: 0, acc: 0 }, { conf: 1, acc: 1 }]} dataKey="acc" stroke="var(--ink-3)" strokeDasharray="4 4" dot={false} isAnimationActive={false} />
                  <Scatter dataKey="acc" fill="var(--product)" />
                </ComposedChart>
              </ResponsiveContainer></div>
              <p className="text-[12px] text-ink-3">ECE {m2.eval.ece.toFixed(3)}<Fn caveat="calibration" sourceKey="confidence_model_v1.json → models.M2.eval.ece" /> · Brier {m2.eval.brier.toFixed(3)}<Fn caveat="calibration" sourceKey="confidence_model_v1.json → models.M2.eval.brier" />. Points near the diagonal = calibrated.</p>
            </CardBody></Card>
            <Card><CardBody>
              <p className="mb-1 text-[13px] font-medium">Selective prediction: accuracy vs coverage</p>
              <div className="h-56"><ResponsiveContainer>
                <ComposedChart data={curve} margin={{ left: -18, right: 8, top: 6 }}>
                  <CartesianGrid stroke="var(--line)" />
                  <XAxis dataKey="coverage" type="number" domain={[0, 1]} tick={{ fontSize: 10, fill: "var(--ink-3)" }} />
                  <YAxis domain={[0.4, 1]} tick={{ fontSize: 10, fill: "var(--ink-3)" }} />
                  <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", fontSize: 12 }} />
                  <Line dataKey="accuracy" stroke="var(--product)" dot={false} strokeWidth={2} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer></div>
              <p className="text-[12px] text-ink-3">Base rate (answer everything): {pct(m2.eval.baseRate.accuracy)}<Fn caveat="single_expert" sourceKey="confidence_model_v1.json → models.M2.eval.baseRate" /> correct. Operating point fixed in the spec before evaluation.</p>
            </CardBody></Card>
          </div>
        </>
      )}

      <h2 className="mb-3 mt-8 text-[17px] font-semibold">What it does not do (yet)</h2>
      <Card><CardBody className="text-[13px] text-ink-2">
        Benchmark gold is single-expert; results come from a Flash-Lite-class model; the corpus holds only current (amended) text; T2 gains are partly by construction.
        It routes low-confidence answers to a human; it does not replace compliance review. <Link className="text-product" to="/reliability">Reliability</Link> ·{" "}
        <Link className="text-product" to="/gaps">Known gaps</Link>
      </CardBody></Card>

      <h2 className="mb-3 mt-8 text-[17px] font-semibold">Roadmap</h2>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {[4, 3, 6, 2].map((r) => { const f = s.futureWork.find((x) => x.rank === r); return f ? (
          <Card key={r}><CardBody className="text-[12.5px]"><Badge tone="outline">Future Work #{r}</Badge><p className="mt-1 font-medium">{f.item}</p><p className="text-ink-3">{f.why}</p></CardBody></Card>) : null; })}
      </div>
    </div>
  );
}

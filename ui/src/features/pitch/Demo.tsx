import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, CircleHelp, ExternalLink, XCircle } from "lucide-react";
import { useData } from "@/data/store";
import { unitConfidence } from "@/data/confidence";
import { Badge, Card, CardBody, Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { FIELD_LABEL, showcaseExample } from "./facts";
import { FinePrint, pct0 } from "./ui";

const VERDICT = {
  same: { label: "Same requirement", tone: "bg-pos-soft text-pos", text: "Both institution types have this obligation in substance." },
  different: { label: "Different requirement", tone: "bg-warn-soft text-warn", text: "Same topic, but at least one important detail changes." },
  none: { label: "No matching rule found", tone: "bg-panel-2 text-ink-2", text: "None of the closest paragraphs for this institution type imposes this duty." },
  abstain: { label: "Couldn't decide", tone: "bg-panel-2 text-ink-2", text: "The comparator's output couldn't be read, so it makes no call." },
  unanswered: { label: "Couldn't decide", tone: "bg-panel-2 text-ink-2", text: "No answer." },
} as const;

const EXPERT = { same: "Same requirement", different: "Different requirement", none: "No matching rule" } as const;

export default function Demo() {
  const s = useData((st) => st.snapshot)!;
  const d = useData((st) => st.derived)!;
  const model = useData((st) => st.confidence);
  const [sp, setSp] = useSearchParams();
  const ex = useMemo(() => showcaseExample(s), [s]);
  const classes = useMemo(() => [...new Set(s.t1Items.map((i) => i.sourceClass))].sort(), [s.t1Items]);
  const cls = sp.get("class") && classes.includes(sp.get("class")!) ? sp.get("class")! : ex?.item.sourceClass ?? classes[0];
  const topics = [...new Set(s.t1Items.filter((i) => i.sourceClass === cls).map((i) => i.subjectFamily ?? ""))].sort();
  const topic = sp.get("topic") && topics.includes(sp.get("topic")!) ? sp.get("topic")! : (ex && cls === ex.item.sourceClass ? ex.item.subjectFamily ?? topics[0] : topics[0]);
  const others = [...new Set(s.t1Items.filter((i) => i.sourceClass === cls && (i.subjectFamily ?? "") === topic).flatMap((i) => i.comparedClasses))].sort();
  const vs = sp.get("vs") && others.includes(sp.get("vs")!) ? sp.get("vs")! : (ex && cls === ex.item.sourceClass && others.includes(ex.unit.classId) ? ex.unit.classId : others[0]);
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    n.set(k, v);
    if (k === "class") { n.delete("topic"); n.delete("vs"); }
    if (k === "topic") n.delete("vs");
    setSp(n, { replace: true });
  };
  const items = s.t1Items.filter((i) => i.sourceClass === cls && (i.subjectFamily ?? "") === topic && i.comparedClasses.includes(vs));

  return (
    <div className="pt-10 sm:pt-14">
      <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">Try it</p>
      <h1 className="max-w-3xl text-[30px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[38px]">Compare your institution's rule with another institution type.</h1>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        These are real RBI rules from the test set. For each one you see the closest matching rule for the other institution type, what the comparator decided,
        what differs, how confident it is, and what the expert said.
      </p>

      <Card className="mt-6"><CardBody className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-[13px] text-ink-2">Your institution type
          <select id="demo-class" value={cls} onChange={(e) => set("class", e.target.value)} className="rounded-md border border-line bg-panel px-2 py-2 text-[14px] text-ink">{classes.map((c) => <option key={c}>{c}</option>)}</select>
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-ink-2">Topic
          <select id="demo-topic" value={topic} onChange={(e) => set("topic", e.target.value)} className="rounded-md border border-line bg-panel px-2 py-2 text-[14px] text-ink">{topics.map((t) => <option key={t}>{t}</option>)}</select>
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-ink-2">Compare with
          <select id="demo-vs" value={vs} onChange={(e) => set("vs", e.target.value)} className="rounded-md border border-line bg-panel px-2 py-2 text-[14px] text-ink">{others.map((c) => <option key={c}>{c}</option>)}</select>
        </label>
      </CardBody></Card>

      <div className="mt-5 space-y-5">
        {items.length === 0 && <p className="text-[14px] text-ink-3">No test rule for this combination. Try another topic.</p>}
        {items.map((it) => {
          const uid = `${it.id}|${vs}`;
          const u = d.unitById.get(uid)!;
          const cf = s.comparatorFields[uid];
          const j = u.predictions.comparator.judgement as keyof typeof VERDICT;
          const v = VERDICT[j] ?? VERDICT.abstain;
          const conf = unitConfidence(model, uid, "M2");
          const src = s.pointers[it.sourcePid];
          const tgt = cf?.decisivePid ? s.pointers[cf.decisivePid] : u.predictions.comparator.matchedPid ? s.pointers[u.predictions.comparator.matchedPid] : null;
          const diffs = (cf?.rows ?? []).filter((r) => ["differs", "only_source", "only_target"].includes(r.status));
          const agrees = u.goldJudgement === j;
          return (
            <Card key={it.id}><CardBody className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                {[{ who: `${cls} (your rule)`, p: src }, { who: `${vs} (closest rule)`, p: tgt }].map((x, i) => (
                  <div key={i} className="min-w-0 rounded-lg bg-panel-2 p-3">
                    <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-3">{x.who}</p>
                    {x.p ? (
                      <>
                        <p className="mt-1.5 text-[14.5px] leading-relaxed">“{x.p.excerpt ?? "…"}”</p>
                        <a href={x.p.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">Read the official text <ExternalLink size={12} /></a>
                      </>
                    ) : <p className="mt-1.5 text-[14px] text-ink-3">No counterpart paragraph.</p>}
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <span className={cn("rounded-md px-2.5 py-1 text-[14px] font-semibold", v.tone)}>{v.label}</span>
                <span className="text-[13.5px] text-ink-2">{v.text}</span>
              </div>

              {j === "different" && diffs.length > 0 && (
                <div>
                  <p className="text-[13px] font-semibold">What differs</p>
                  <ul className="mt-1.5 space-y-1 text-[14px]">
                    {diffs.map((r) => (
                      <li key={r.field} className="flex flex-wrap gap-x-2">
                        <span className="font-medium">{FIELD_LABEL[r.field] ?? r.field}:</span>
                        <span className="text-ink-2">{r.status === "only_source" ? `stated only for ${cls}` : r.status === "only_target" ? `stated only for ${vs}` : "differs"}
                          {(r.sourceValue || r.targetValue) && <> (“{r.sourceValue ?? "—"}” vs “{r.targetValue ?? "—"}”)</>}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid gap-3 border-t border-line pt-3 text-[13.5px] sm:grid-cols-2">
                <div>
                  <p className="font-semibold">How confident is it?</p>
                  {conf && !conf.blocked && conf.stat ? (
                    <p className="text-ink-2"><Badge tone={conf.band === "High" ? "pos" : conf.band === "Medium" ? "warn" : "neg"}>{conf.band}</Badge>{" "}
                      In testing, answers at this level were right {pct0(conf.stat.accuracy ?? 0)} of the time.
                      {conf.band !== "High" && " A person should check this one."}</p>
                  ) : <p className="text-ink-2">Not enough evidence for a confidence level; a person should check this one.</p>}
                </div>
                <div>
                  <p className="font-semibold">What did the expert say?</p>
                  <p className="flex items-center gap-1.5 text-ink-2">
                    {agrees ? <CheckCircle2 size={15} className="text-pos" /> : j === "abstain" ? <CircleHelp size={15} /> : <XCircle size={15} className="text-neg" />}
                    {EXPERT[u.goldJudgement]}{agrees ? ": the comparator agrees." : ": the comparator got this one wrong."}
                  </p>
                </div>
              </div>
              <p className="text-[11.5px] text-ink-3">
                <Tip content={`${it.sourcePid} · harvested ${src?.harvestDate ?? "—"} · sha256 ${src?.sha256?.slice(0, 16) ?? "—"}…`}><span className="cursor-help underline decoration-dotted">Source details</span></Tip>
                {" "}· Quotes are shortened to a few words; follow the link for the full rule. In force from {it.inForceFrom ?? "—"}.
              </p>
            </CardBody></Card>
          );
        })}
      </div>

      <FinePrint>
        <p>This demo shows the system's saved answers on the expert-checked test set, so you can see where it's right and where it's wrong.</p>
        <p>Analysing your own new text needs the full version running locally with its own AI key; it isn't enabled on this public site.</p>
        <p>The corpus holds only the current, amended text of each Direction. This is a research system, not legal or compliance advice.</p>
      </FinePrint>
    </div>
  );
}

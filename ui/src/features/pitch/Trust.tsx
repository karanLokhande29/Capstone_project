import { Link } from "react-router-dom";
import { FileCheck2, Link2, Lock, ShieldCheck, UserCheck } from "lucide-react";
import { useData } from "@/data/store";
import { Card, CardBody } from "@/components/ui/primitives";
import { agreementFact, corpusFacts, trustFacts } from "./facts";
import { Bars, Block, Meaning, pct0 } from "./ui";

export default function Trust() {
  const s = useData((st) => st.snapshot)!;
  const model = useData((st) => st.confidence);
  const t = trustFacts(model);
  const c = corpusFacts(s);
  const agree = agreementFact(s);
  const frozenOk = s.frozen.every((f) => f.status === "match");
  const roadmap = [
    { t: "Stronger AI models", d: "Re-run every system with larger models; the hardest cases (spotting differences) may get easier." },
    { t: "Smarter result ranking", d: "Re-rank search results with a second model so the best counterpart is first more often." },
    { t: "Wider date coverage", d: "Extend the date test beyond cases that can be read automatically from RBI's amendment notices." },
    { t: "A second expert on every label", d: "Independent double-labelling of the whole test set, so results don't rest on one person's judgement." },
  ];
  return (
    <div className="pt-10 sm:pt-14">
      <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">Trust & limits</p>
      <h1 className="max-w-3xl text-[30px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[38px]">How we keep the results honest, and what the system can't do yet.</h1>

      <Block eyebrow="Safeguards" title="Built so you can check every answer">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { icon: Link2, t: "Every answer cites its source", d: "A paragraph ID and a link to the official RBI PDF. Quotes are kept to a few words; the full text stays with RBI." },
            { icon: Lock, t: "Rules fixed before testing", d: `The comparator's instructions and decision rule were locked (with a digital fingerprint) before it saw the test set${frozenOk ? "; all fingerprints still match" : ""}.` },
            { icon: ShieldCheck, t: "Confidence that means something", d: "Built on a separate practice set and frozen before testing; never adjusted afterwards." },
            { icon: UserCheck, t: "Expert-labelled test set", d: `${c.comparisons} comparisons labelled by an expert${agree ? `; on a separate sample, three people agreed well (score ${agree.kappa.toFixed(2)} on a 0–1 scale)` : ""}.` },
            { icon: FileCheck2, t: "Decisions you can explain", d: "The verdict comes from a fixed rule over 13 named details, not from a black-box score." },
          ].map((x) => (
            <Card key={x.t}><CardBody className="space-y-1.5"><x.icon size={18} className="text-accent" /><p className="text-[15px] font-semibold">{x.t}</p><p className="text-[13.5px] leading-relaxed text-ink-2">{x.d}</p></CardBody></Card>
          ))}
        </div>
      </Block>

      {t && (
        <Block eyebrow="Confidence" title="Does “high confidence” actually mean right more often?">
          <div className="max-w-3xl">
            <Bars format={pct0} rows={[t.high, t.medium, t.low].map((b) => ({ label: `${b.band} (${b.n} answers)`, value: b.accuracy ?? 0, highlight: b.band === "High", note: `likely range ${pct0(b.wilsonCI![0])}–${pct0(b.wilsonCI![1])}` }))}
              caption="Share of answers that matched the expert, by confidence level." />
          </div>
          <Meaning>Yes: {pct0(t.high.accuracy ?? 0)} at high vs {pct0(t.low.accuracy ?? 0)} at low. A practical policy is to accept high-confidence answers ({pct0(t.coverage)} of cases) and send the rest to a reviewer.</Meaning>
        </Block>
      )}

      <Block eyebrow="Limits" title="What to keep in mind">
        <ul className="max-w-3xl list-disc space-y-2 pl-5 text-[14.5px] leading-relaxed text-ink-2">
          <li><b className="text-ink">One expert labelled the test set.</b> Agreement was checked on a separate sample, not on the test set itself.</li>
          <li><b className="text-ink">Small numbers.</b> {c.examples} obligations and {c.comparisons} comparisons; differences between some systems are within the margin of error.</li>
          <li><b className="text-ink">One fast AI model.</b> All AI results use Gemini 3.5 Flash-Lite. Larger models may do better.</li>
          <li><b className="text-ink">Over-flagging.</b> The comparator catches far more real differences but also raises false alarms; flagged differences need a human check.</li>
          <li><b className="text-ink">Current text only.</b> RBI publishes amended Directions in place, so earlier wording can't be shown.</li>
          <li><b className="text-ink">Not advice.</b> A research system; use it to find and prioritise, not to decide.</li>
        </ul>
      </Block>

      <Block eyebrow="Roadmap" title="What comes next">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {roadmap.map((f) => (
            <Card key={f.t}><CardBody><p className="text-[15px] font-semibold">{f.t}</p><p className="mt-1 text-[13.5px] text-ink-2">{f.d}</p></CardBody></Card>
          ))}
        </div>
        <p className="mt-5 text-[14px]"><Link to="/demo" className="text-accent hover:underline">Try the comparator on real rules →</Link></p>
      </Block>
    </div>
  );
}

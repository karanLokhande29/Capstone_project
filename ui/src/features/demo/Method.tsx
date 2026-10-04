import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowDown, FileCheck2, Link2, Lock, ShieldCheck, UserCheck } from "lucide-react";
import { Card, CardBody } from "@/components/ui/primitives";
import { resolveKey } from "@/lib/keys";
import { fmtInt } from "@/lib/utils";
import { Block, Meaning } from "../pitch/ui";
import { PostPaper } from "./badges";
import { useJson } from "./data";
import { Loading, LoadError, PageHead } from "./DemoLayout";
import { CostMeter } from "./lab/CostMeter";
import type { MethodShard, ResultsShard } from "./types";

const LANE1 = [
  ["Institution filter", "only Directions written for the institution type being compared against"],
  ["Keyword + meaning search", "BM25 and dense retrieval merged by reciprocal-rank fusion"],
  ["Date check (T3)", "which version applied on the as-of date, from RBI's amendment record"],
  ["LLM judgement", "same / different / no match over the retrieved paragraphs"],
  ["Optional fact-checker", "asks the model to retry or decline when it cannot back an answer (our first pipeline)"],
];
const LANE2 = [
  ["Two candidate paragraphs", "the same two paragraphs the expert saw on the annotation sheet"],
  ["13-field extraction", "the model fills who, what, scope, condition, threshold, amount, percentage, frequency, deadline, exception, records, reporting"],
  ["Fixed rule", "frozen by sha256 before any test run; decides same / different / none"],
  ["Verdict", "with the fields that decided it (decision trace)"],
  ["Confidence", "a small model fitted on a separate set and frozen (post-paper)"],
];

export default function Method() {
  const m = useJson<MethodShard>("method.json");
  const r = useJson<ResultsShard>("results.json");
  const loc = useLocation();
  useEffect(() => { if (loc.hash && m.data && r.data) document.getElementById(loc.hash.slice(1))?.scrollIntoView(); }, [loc.hash, m.data, r.data]);
  if (m.error || r.error) return <LoadError error={(m.error ?? r.error)!} />;
  if (!m.data || !r.data) return <Loading what="the method" />;
  const M = m.data, R = r.data.results;
  const n = (k: string) => resolveKey(R, k) as number;
  const kappa = M.reliability.find((x) => x.id === "fleiss_class_row");
  const allMatch = M.ledger.every((x) => x.status === "match");
  const s = M.sensitivity;
  const build = [
    ["Collect every Master Direction", `All ${fmtInt(n("tables.01_corpus.directions"))} RBI Master Directions, split into ${fmtInt(n("tables.01_corpus.paragraphs"))} paragraphs with stable IDs, tagged with institution type and topic.`],
    ["Find the obligations", `Duty language (“shall”, “must”…) screened by rules refined over four rounds: ${fmtInt(n("tables.02_candidates.candidates_kept"))} likely obligations, about ${Math.round(n("tables.02_candidates.precision_rounds.3.precision") * 100)}% genuine on a hand-checked sample.`],
    ["Pair them across institution types", "For each obligation, the most similar paragraphs in other institution types' Directions on the same topic (the P2-002 embedding candidates)."],
    ["Expert labels", `${n("tables.05_t1_benchmark.sample")} obligations drawn at random; ${n("tables.05_t1_benchmark.validated")} confirmed. Each judged against up to four other institution types: 412 labelled comparisons, 78 real differences.`],
    ["Four tests", "T1 spotting differences (main), T2 finding the matching rule, T3 status on a date, T4 whether an answer-scoring metric can be gamed."],
  ];

  return (
    <div>
      <PageHead eyebrow="Method & Trust" title="How the benchmark was built, how each system was evaluated, and what to keep in mind." />
      <Block id="build" eyebrow="The benchmark" title="From 381 regulations to a test any system can be measured on">
        <ol className="space-y-3">
          {build.map(([t, d], i) => (
            <li key={t} className="grid grid-cols-[32px_1fr] gap-3">
              <span className="num grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-[14px] font-semibold text-accent">{i + 1}</span>
              <div><p className="text-[16px] font-semibold">{t}</p><p className="mt-0.5 max-w-3xl text-[14.5px] leading-relaxed text-ink-2">{d}</p></div>
            </li>
          ))}
        </ol>
      </Block>

      <Block id="lanes" eyebrow="The systems" title="Two lanes, evaluated separately">
        <div className="grid gap-4 md:grid-cols-2">
          <Lane title="Lane 1 — Retrieval systems" sub="Evaluated on T1, T2 and T3" steps={LANE1} />
          <Lane title="Lane 2 — Structured comparator" sub="Targeted experiment, pre-registered" steps={LANE2} />
        </div>
        <Meaning>These were evaluated separately. The comparator has not yet been run on retrieved evidence; that is future work. Retrieval systems never used the comparator.</Meaning>
      </Block>

      <Block id="safeguards" eyebrow="Safeguards" title="Built so you can check every answer">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { icon: Link2, t: "Pointer-only release", d: "Every case cites a paragraph ID, a hash and RBI's official PDF. The public site shows at most 12 words per paragraph (25 across all uses)." },
            { icon: Lock, t: "Fixed before testing", d: `Prompt and rule were frozen by sha256 on ${M.frozenAtUtc.slice(0, 10)}${allMatch ? "; every frozen file still matches" : ""}.` },
            { icon: FileCheck2, t: "A traceable decision", d: `The verdict comes from a fixed rule over ${M.fields.length} named fields. Re-running that rule on the sealed outputs reproduces 412 of 412 stored verdicts.` },
            { icon: ShieldCheck, t: "Honest confidence", d: "Fitted on a separate 30-item set and frozen before gold evaluation; never rescaled. Post-paper." },
            { icon: UserCheck, t: "Expert-labelled test set", d: `412 comparisons labelled by one expert${kappa ? `; on a separate 30-item sample three raters agreed at κ ${kappa.value.toFixed(3)}` : ""}.` },
          ].map((x) => <Card key={x.t}><CardBody className="space-y-1.5"><x.icon size={18} className="text-accent" /><p className="text-[15px] font-semibold">{x.t}</p><p className="text-[13.5px] leading-relaxed text-ink-2">{x.d}</p></CardBody></Card>)}
        </div>
      </Block>

      <Block id="sensitivity" eyebrow="Sensitivity analysis" title="Does the comparator lean on institution names?">
        <p className="mb-3 inline-flex flex-wrap items-center gap-2 rounded-md border border-product/40 bg-product-soft px-3 py-1.5 text-[13.5px] font-semibold text-product">{s.label} <PostPaper /></p>
        <p className="max-w-3xl text-[14.5px] leading-relaxed text-ink-2">The frozen rule treats any extracted <code>actor</code> difference as material, and institution names differ between classes by construction (“A UCB” vs “An AIFI”).
          Re-running the frozen rule with actor comparisons masked shows how much rests on that:</p>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-[420px] text-[14px]">
            <thead className="text-left text-[12.5px] text-ink-3"><tr><th className="py-1 pr-6 font-medium" /><th className="pr-6 font-medium">Frozen rule (reported)</th><th className="font-medium">Actor masked</th></tr></thead>
            <tbody>
              <tr className="border-t border-line"><td className="py-1.5 pr-6">Correct “different” calls (of 78)</td><td className="num">{s.frozen.tp}</td><td className="num">{s.actorMasked.tp} ({s.actorMasked.tp} of {s.frozen.tp} remain)</td></tr>
              <tr className="border-t border-line"><td className="py-1.5 pr-6">False alarms</td><td className="num">{s.frozen.fp}</td><td className="num">{s.actorMasked.fp} ({s.actorMasked.fp} of {s.frozen.fp} remain)</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[13px] text-ink-2">Lost correct call: {s.lostCorrect.map((id) => <Link key={id} to={`/case/${encodeURIComponent(id)}`} className="font-mono text-[12px] text-accent hover:underline">{id}</Link>)}. In the Microscope, actor rows that differ only by entity name carry the note “Entity name differs by construction.” The headline figures (38 of 78, 70 false alarms) stay the frozen ones.</p>
      </Block>

      <Block id="limits" eyebrow="Limits" title="What to keep in mind">
        <ul className="max-w-3xl list-disc space-y-2 pl-5 text-[14.5px] leading-relaxed text-ink-2">
          <li><b className="text-ink">One expert labelled the test set.</b> Agreement was checked on a separate sample, not on the test set itself.</li>
          <li><b className="text-ink">Small numbers.</b> 106 obligations and 412 comparisons; some differences between systems are within the margin of error.</li>
          <li><b className="text-ink">One fast model.</b> Every system uses {M.model}. Larger models may do better.</li>
          <li><b className="text-ink">Over-flagging.</b> The comparator catches more real differences but raises {s.frozen.fp} false alarms; a flag is a reason to look.</li>
          <li><b className="text-ink">Comparator not on retrieved evidence.</b> It saw the expert's two candidates; an end-to-end pipeline was not evaluated.</li>
          <li><b className="text-ink">Current text only.</b> RBI publishes amended Directions in place, so earlier wording can't be shown.</li>
          <li><b className="text-ink">Topic matching is the next bottleneck.</b> In {M.missesSameDuty} of the comparator's 32 “no match” errors on real differences it judged neither paragraph to be about the same duty.</li>
          <li><b className="text-ink">Not advice.</b> A research system; use it to find and prioritise, not to decide.</li>
        </ul>
      </Block>

      <Block id="cost" eyebrow="Cost" title="What a comparator run costs"><CostMeter /></Block>

      <Block id="hashes" eyebrow="Frozen files" title="Hashes the backend and this page verify">
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[640px] text-left text-[12.5px]">
            <thead className="bg-panel-2 text-ink-3"><tr><th className="px-3 py-1.5 font-medium">File</th><th className="px-3 font-medium">sha256</th><th className="px-3 font-medium">Status</th></tr></thead>
            <tbody>{M.ledger.map((x) => (
              <tr key={x.path} className="border-t border-line"><td className="px-3 py-1.5 font-mono">{x.path}</td><td className="break-all px-3 font-mono text-ink-2">{x.actualSha256?.slice(0, 24)}…</td><td className="px-3">{x.status === "match" ? "✓ matches" : x.status}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <p className="mt-2 text-[12.5px] text-ink-3">Comparator model {M.model} · rule {M.ruleVersion} · frozen {M.frozenAtUtc} · confidence model sha256 {M.hashes.confidenceModel.slice(0, 16)}…</p>
      </Block>

      <Block id="licences" eyebrow="Licences" title="What you may reuse">
        <ul className="max-w-3xl list-disc space-y-1.5 pl-5 text-[14px] text-ink-2">
          <li>Code: MIT (repository <code>LICENSE</code>).</li>
          <li>Annotations and derived metadata (labels, pointers, matrix, T2–T4 items): CC BY 4.0 (<code>release/LICENSE-DATA</code>).</li>
          <li>RBI documents are not included and not licensed by this project; the release rebuilds text from RBI's own URLs (<code>release/rehydrate.py</code>).</li>
          <li>RePASs ships no licence file; it was run unmodified and is not redistributed.</li>
        </ul>
      </Block>
    </div>
  );
}

function Lane({ title, sub, steps }: { title: string; sub: string; steps: string[][] }) {
  return (
    <Card><CardBody>
      <p className="text-[16px] font-semibold">{title}</p><p className="text-[13px] text-ink-3">{sub}</p>
      <ol className="mt-3">
        {steps.map(([t, d], i) => (
          <li key={t}>
            <div className="rounded-md border border-line px-3 py-2"><p className="text-[14px] font-medium">{t}</p><p className="text-[13px] text-ink-2">{d}</p></div>
            {i < steps.length - 1 && <div className="flex justify-center py-0.5 text-ink-3" aria-hidden><ArrowDown size={14} /></div>}
          </li>
        ))}
      </ol>
    </CardBody></Card>
  );
}

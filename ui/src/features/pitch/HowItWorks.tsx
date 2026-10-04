import { ArrowDown } from "lucide-react";
import { useData } from "@/data/store";
import { Card, CardBody } from "@/components/ui/primitives";
import { resolveKey } from "@/lib/keys";
import { fmtInt } from "@/lib/utils";
import { corpusFacts } from "./facts";
import { Block } from "./ui";

export default function HowItWorks() {
  const s = useData((st) => st.snapshot)!;
  const c = corpusFacts(s);
  const n = (k: string) => resolveKey(s.results, k) as number;
  const build = [
    { title: "Collect every Master Direction", text: `All ${fmtInt(c.directions)} RBI Master Directions, split into ${fmtInt(c.paragraphs)} paragraphs with stable IDs, each tagged with the institution type it's written for and its topic (${c.topics} topics).` },
    { title: "Find the obligations", text: `Paragraphs with duty words ("shall", "must", "is required to"…) were screened by rules refined over four rounds: ${fmtInt(n("tables.02_candidates.candidates_kept"))} likely obligations, about ${Math.round(n("tables.02_candidates.precision_rounds.3.precision") * 100)}% of them genuine on a hand-checked sample.` },
    { title: "Pair them across institution types", text: "For each obligation, the most similar paragraphs in other institution types' Directions on the same topic were found automatically." },
    { title: "Have an expert label the pairs", text: `${n("tables.05_t1_benchmark.sample")} obligations were drawn at random; ${c.examples} were confirmed as real obligations. For each, an expert judged up to four other institution types: same requirement, different requirement, or no matching rule. That gives ${c.comparisons} labelled comparisons, ${c.realDifferences} of them real differences.` },
    { title: "Build four tests", text: "Spotting differences (the main test), finding the matching rule for another institution type, telling whether a rule was in force on a date, and checking whether a popular answer-scoring metric can be fooled." },
  ];
  const answer = [
    ["You choose", "your institution type, a topic or rule, and a date"],
    ["Institution filter", "only Directions written for the institution type you're comparing against"],
    ["Search", "keyword and meaning-based search combined to find the closest paragraphs"],
    ["Date check", "which version of the rule applied on your date (from RBI's amendment record)"],
    ["Field-by-field comparison", "who, what, scope, condition, threshold, amount, deadline, exceptions, records, reporting…; a fixed rule decides same / different / none"],
    ["Confidence", "a score built and frozen on a separate practice set; low-confidence answers go to a person"],
    ["Answer", "the verdict, what differs, and a link to the official RBI paragraph"],
  ];
  return (
    <div className="pt-10 sm:pt-14">
      <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">How it works</p>
      <h1 className="max-w-3xl text-[30px] font-semibold leading-tight tracking-tight [text-wrap:balance] sm:text-[38px]">From 381 regulations to a test any AI system can be measured on.</h1>
      <Block eyebrow="Part 1" title="How the benchmark was built">
        <ol className="space-y-3">
          {build.map((b, i) => (
            <li key={b.title} className="grid grid-cols-[32px_1fr] gap-3">
              <span className="num grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-[14px] font-semibold text-accent">{i + 1}</span>
              <div><p className="text-[16px] font-semibold">{b.title}</p><p className="mt-0.5 max-w-3xl text-[14.5px] leading-relaxed text-ink-2">{b.text}</p></div>
            </li>
          ))}
        </ol>
      </Block>
      <Block eyebrow="Part 2" title="How the system answers a question">
        <div className="max-w-2xl">
          {answer.map(([t, d], i) => (
            <div key={t}>
              <Card><CardBody className="py-3"><p className="text-[15px] font-semibold">{t}</p><p className="text-[14px] text-ink-2">{d}</p></CardBody></Card>
              {i < answer.length - 1 && <div className="flex justify-center py-1 text-ink-3"><ArrowDown size={16} /></div>}
            </div>
          ))}
        </div>
      </Block>
      <Block eyebrow="Glossary" title="Words you'll see">
        <dl className="grid max-w-4xl gap-x-8 gap-y-3 text-[14px] sm:grid-cols-2">
          {[
            ["Master Direction", "RBI's consolidated rulebook on one subject for one type of regulated institution."],
            ["Institution type", "Who a Direction is written for: e.g. Commercial Banks, NBFCs, Small Finance Banks, Urban Co-operative Banks."],
            ["Same / different / no match", "The expert's verdict on whether another institution type has the same obligation, a changed version of it, or none."],
            ["False alarm", "The system says the rules differ when the expert judged them the same (or found no match)."],
            ["Confidence level", "High / Medium / Low, with how often answers at that level were right in testing."],
            ["Benchmark", "A fixed, expert-labelled test that any system can be measured on, so results can be compared fairly."],
          ].map(([t, d]) => <div key={t}><dt className="font-semibold">{t}</dt><dd className="text-ink-2">{d}</dd></div>)}
        </dl>
      </Block>
    </div>
  );
}

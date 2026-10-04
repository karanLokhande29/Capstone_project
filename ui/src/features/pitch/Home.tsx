import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock, ExternalLink, Scale, Search, ShieldCheck } from "lucide-react";
import { useData } from "@/data/store";
import { Button, Card, CardBody } from "@/components/ui/primitives";
import { fmtInt } from "@/lib/utils";
import { corpusFacts, dateFacts, FIELD_LABEL, searchFacts, showcaseExample, systemOutcomes, trustFacts } from "./facts";
import { PERSONAS, usePersona, type Persona } from "./persona";
import { Block, pct0, Stat, Term } from "./ui";

const HERO: Record<Persona, { title: string; sub: string; cta: { to: string; label: string } }> = {
  compliance: {
    title: "Same topic, different institution. Is it really the same rule?",
    sub: "RBI writes a separate Master Direction for banks, NBFCs, co-operative banks and others. We built a system that finds the matching rule for your institution type, shows what differs, and tells you when to double-check.",
    cta: { to: "/demo", label: "Try it on real rules" },
  },
  researcher: {
    title: "Can AI tell which institution a rule binds, and what differs between them?",
    sub: "RBI-ObliBench is a benchmark built from all 381 RBI Master Directions, with expert-labelled examples, plus a measured pipeline. It shows where today's AI succeeds and where it quietly fails.",
    cta: { to: "/findings", label: "See the results" },
  },
  investor: {
    title: "Compliance teams compare parallel regulations by hand. We measured how to automate it safely.",
    sub: "Our comparator spots far more real differences between institution types than a standard AI assistant, and its confidence score separates answers you can trust from ones a person should review.",
    cta: { to: "/findings", label: "See the evidence" },
  },
};

const NEXT: Record<Persona, { title: string; text: string; to: string }[]> = {
  compliance: [
    { title: "Try it", text: "Pick your institution type and a topic; see the matching rule for another type and what changes.", to: "/demo" },
    { title: "When to trust it", text: "How the confidence badge works and when a human should check.", to: "/trust" },
    { title: "Dates matter", text: "Why the system checks which version of a rule applied on a date.", to: "/findings#dates" },
  ],
  researcher: [
    { title: "All results, explained", text: "Six findings with charts and the fine print (uncertainty, biases).", to: "/findings" },
    { title: "How the benchmark was built", text: "From 381 Directions to expert-checked examples.", to: "/how-it-works" },
    { title: "Limits", text: "Single-expert labels, small sample sizes and what we would do next.", to: "/trust" },
  ],
  investor: [
    { title: "The headline result", text: "Real differences found: ours vs standard AI assistants.", to: "/findings#differences" },
    { title: "Safety by design", text: "Confidence scores route uncertain answers to a person.", to: "/trust" },
    { title: "See it work", text: "A live walk-through on real RBI rules.", to: "/demo" },
  ],
};

export default function PitchHome() {
  const s = useData((st) => st.snapshot)!;
  const model = useData((st) => st.confidence);
  const { persona, set } = usePersona();
  const c = corpusFacts(s);
  const out = systemOutcomes(s);
  const ours = out.find((o) => o.ours)!;
  const nextBest = [...out].filter((o) => !o.ours).sort((a, b) => b.diffFound - a.diffFound)[0];
  const search = searchFacts(s);
  const std = search.rows.find((r) => r.name.startsWith("Both"))!;
  const filt = search.rows.find((r) => r.ours)!;
  const trust = trustFacts(model);
  const dates = dateFacts(s);
  const ex = showcaseExample(s);
  const hero = HERO[persona];

  return (
    <div>
      <section className="pb-6 pt-10 sm:pt-16">
        <div className="mb-6 flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Who are you?">
          <span className="text-[13px] text-ink-3">I'm here as:</span>
          {PERSONAS.map((p) => (
            <button key={p.id} type="button" role="radio" aria-checked={persona === p.id} onClick={() => set(p.id)}
              className={`cursor-pointer rounded-full border px-3 py-1 text-[13px] transition-colors ${persona === p.id ? "border-accent bg-accent text-white dark:text-black" : "border-line bg-panel text-ink-2 hover:border-ink-3"}`}>
              {p.label}
            </button>
          ))}
        </div>
        <h1 className="max-w-4xl text-[32px] font-semibold leading-[1.1] tracking-tight [text-wrap:balance] sm:text-[46px]">{hero.title}</h1>
        <p className="mt-5 max-w-2xl text-[16px] leading-relaxed text-ink-2 sm:text-[17px]">{hero.sub}</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to={hero.cta.to}><Button className="h-10 px-4 text-[14px]">{hero.cta.label} <ArrowRight size={15} /></Button></Link>
          <Link to="/how-it-works"><Button variant="outline" className="h-10 px-4 text-[14px]">How it works</Button></Link>
        </div>
        <div className="mt-10 grid grid-cols-2 gap-6 border-t border-line pt-6 sm:grid-cols-4">
          <Stat value={fmtInt(c.directions)} label="RBI Master Directions covered" />
          <Stat value={fmtInt(c.paragraphs)} label="paragraphs indexed" />
          <Stat value={c.institutionTypes} label="regulated institution types" hint={`${c.headings} headings in RBI's list; ${c.institutionTypes} are types of regulated institutions`} />
          <Stat value={c.comparisons} label="rule comparisons checked by an expert" hint={`${c.examples} source obligations × up to 4 other institution types`} />
        </div>
      </section>

      {ex && (
        <Block eyebrow="The problem in 30 seconds" title="Two Directions on the same topic can look identical and still impose different duties.">
          <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">
            A real case from the benchmark: the rule for <b className="text-ink">{ex.item.sourceClass}</b> and its counterpart for <b className="text-ink">{ex.unit.classId}</b>.
            {" "}None of the five AI assistants we tested flagged a difference. An expert did, and so did our comparator.
          </p>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {[{ who: ex.item.sourceClass, p: ex.src }, { who: ex.unit.classId, p: ex.tgt }].map((x) => (
              <Card key={x.p.id}><CardBody>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-ink-3">{x.who}</p>
                <p className="mt-2 text-[15px] leading-relaxed">“{x.p.excerpt}”</p>
                <a href={x.p.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
                  Official RBI source ({x.p.id}) <ExternalLink size={12} /></a>
              </CardBody></Card>
            ))}
          </div>
          <div className="mt-3 rounded-lg border border-warn/40 bg-warn-soft px-4 py-3 text-[14px]">
            <b>What differs:</b>{" "}
            {ex.diffs.slice(0, 3).map((d, i) => (
              <span key={d.field}>{i > 0 && "; "}<b>{FIELD_LABEL[d.field] ?? d.field}</b>
                {d.sourceValue || d.targetValue ? <> (“{d.sourceValue ?? "not stated"}” vs “{d.targetValue ?? "not stated"}”)</> : null}</span>
            ))}.
            <span className="mt-1 block text-[12.5px] text-ink-2">Quotes are shortened; follow the links for the full text.</span>
          </div>
        </Block>
      )}

      <Block eyebrow="What we built" title="A test set for this problem, and a system measured against it.">
        <div className="grid gap-3 md:grid-cols-2">
          <Card><CardBody className="space-y-2 text-[14px] leading-relaxed text-ink-2">
            <p className="text-[16px] font-semibold text-ink">1 · The benchmark (RBI-ObliBench)</p>
            <p>All {fmtInt(c.directions)} RBI Master Directions, split into {fmtInt(c.paragraphs)} paragraphs and tagged by <Term def="The type of regulated institution a Direction is written for, e.g. Commercial Banks, NBFCs, Payments Banks, Urban Co-operative Banks.">institution type</Term> and topic.</p>
            <p>An expert checked {c.comparisons} rule pairs and labelled each one <i>same</i>, <i>different</i> or <i>no matching rule</i>. That gives {c.realDifferences} real differences to find.</p>
          </CardBody></Card>
          <Card><CardBody className="space-y-2 text-[14px] leading-relaxed text-ink-2">
            <p className="text-[16px] font-semibold text-ink">2 · The system</p>
            <p><b className="text-ink">Institution-aware search</b> finds the matching rule for the type you ask about, and <b className="text-ink">date awareness</b> checks which version applies.</p>
            <p>The <b className="text-ink">field-by-field comparator</b> lines up who, what, threshold, deadline, exceptions and more, and a fixed rule decides. A <b className="text-ink">confidence score</b> says when to trust it.</p>
          </CardBody></Card>
        </div>
      </Block>

      <Block eyebrow="Key results" title="What we found, in plain numbers.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Link to="/findings#differences" className="group rounded-lg border border-line bg-panel p-4 hover:border-accent">
            <Scale size={18} className="text-accent" />
            <p className="num mt-3 text-[30px] font-semibold leading-none">{ours.diffFound}<span className="text-[16px] text-ink-3"> / {ours.diffTotal}</span></p>
            <p className="mt-2 text-[13.5px] text-ink-2">real differences found by our comparator, vs {nextBest.diffFound} for the best AI assistant.</p>
          </Link>
          <Link to="/findings#search" className="group rounded-lg border border-line bg-panel p-4 hover:border-accent">
            <Search size={18} className="text-accent" />
            <p className="num mt-3 text-[30px] font-semibold leading-none">{pct0(filt.top10)}</p>
            <p className="mt-2 text-[13.5px] text-ink-2">of searches put the matching rule in the top 10, vs {pct0(std.top10)} for standard search.</p>
          </Link>
          {trust && !trust.experimental && (
            <Link to="/findings#trust" className="group rounded-lg border border-line bg-panel p-4 hover:border-accent">
              <ShieldCheck size={18} className="text-accent" />
              <p className="num mt-3 text-[30px] font-semibold leading-none">{pct0(trust.high.accuracy ?? 0)}</p>
              <p className="mt-2 text-[13.5px] text-ink-2">correct when it says “high confidence” ({pct0(trust.coverage)} of cases). The rest goes to a person.</p>
            </Link>
          )}
          <Link to="/findings#dates" className="group rounded-lg border border-line bg-panel p-4 hover:border-accent">
            <CalendarClock size={18} className="text-accent" />
            <p className="num mt-3 text-[30px] font-semibold leading-none">{dates.wrong}<span className="text-[16px] text-ink-3"> / {dates.changed}</span></p>
            <p className="mt-2 text-[13.5px] text-ink-2">rules already amended or deleted that an AI called “in force, unchanged” without date checks.</p>
          </Link>
        </div>
        <p className="mt-4 text-[13px] text-ink-3">Each result has caveats; they're on the <Link to="/findings" className="text-accent hover:underline">Results</Link> page under “The fine print”.</p>
      </Block>

      <Block eyebrow="Where to go next" title="Suggested for you">
        <div className="grid gap-3 md:grid-cols-3">
          {NEXT[persona].map((n) => (
            <Link key={n.title} to={n.to} className="rounded-lg border border-line bg-panel p-4 hover:border-accent">
              <p className="flex items-center gap-1 text-[15px] font-semibold">{n.title} <ArrowRight size={14} className="text-accent" /></p>
              <p className="mt-1.5 text-[13.5px] text-ink-2">{n.text}</p>
            </Link>
          ))}
        </div>
      </Block>
    </div>
  );
}

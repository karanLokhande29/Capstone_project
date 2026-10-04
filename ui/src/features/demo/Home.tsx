import { Link } from "react-router-dom";
import { ArrowRight, Gauge, Grid3x3, Radio, Scale, Search, ShieldCheck } from "lucide-react";
import { fmtInt } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { PERSONAS, usePersona, type Persona } from "../pitch/persona";
import { useApi } from "./api";
import { StatusBadge } from "./badges";
import { useHome } from "./data";
import { Loading, LoadError, POSITIONING } from "./DemoLayout";
import { Round } from "./play/Round";

type CardId = "explore" | "live" | "triage" | "failures" | "method" | "cost";
const CARDS: Record<CardId, { title: string; text: string; to: string; icon: React.ReactNode }> = {
  explore: { title: "Explore cases", text: "Open any of the 412 expert-labelled comparisons in the field-by-field Microscope.", to: "/cases", icon: <Search size={18} /> },
  live: { title: "Run the comparator live", text: "Re-run the frozen comparator on a benchmark pair and compare it with the sealed output.", to: "/lab", icon: <Radio size={18} /> },
  triage: { title: "See the trade-off", text: "How much could a team let the system handle, and how accurate is what it handles?", to: "/triage", icon: <Gauge size={18} /> },
  failures: { title: "Where do the models fail?", text: "The 78 real differences, system by system: reasoning failures vs retrieval failures.", to: "/cases/failures", icon: <Grid3x3 size={18} /> },
  method: { title: "Method & Trust", text: "Frozen hashes, two separately evaluated lanes, limits and a post-paper sensitivity analysis.", to: "/method", icon: <ShieldCheck size={18} /> },
  cost: { title: "What it costs to run", text: "Tokens per comparator call and for the full 412-pair run, from the call ledger.", to: "/lab#cost", icon: <Scale size={18} /> },
};
/** The persona only reorders cards and sets default filters; it never hides caveats. */
const ORDER: Record<Persona, CardId[]> = {
  compliance: ["triage", "explore", "live"],
  researcher: ["failures", "method", "explore"],
  investor: ["live", "cost", "triage"],
};

export default function Home() {
  const h = useHome();
  const api = useApi();
  const { persona, set, myClass, setClass } = usePersona();
  if (h.error) return <LoadError error={h.error} />;
  if (!h.data) return <Loading />;
  const { hero, heroPointers, stats } = h.data;
  const cards = ORDER[persona].map((id) => (id === "explore" && persona === "compliance" && myClass ? { ...CARDS.explore, to: `/cases?class=${encodeURIComponent(myClass)}`, text: `Every comparison involving ${myClass}, in the field-by-field Microscope.` } : CARDS[id]));

  return (
    <div>
      <section className="pb-4 pt-8 sm:pt-12" aria-labelledby="hero">
        <div className="mb-3 flex flex-wrap items-center gap-2"><StatusBadge status="sealed" /><span className="text-[12.5px] text-ink-3">{hero.topic} · {hero.sourceClass} → {hero.targetClass}</span></div>
        <h1 id="hero" className="max-w-4xl text-[30px] font-semibold leading-[1.1] tracking-tight [text-wrap:balance] sm:text-[44px]">These two rules look the same. They aren't.</h1>
        <p className="mt-3 max-w-2xl text-[17px] leading-relaxed text-ink-2">None of the five AI systems we tested noticed. Can you?</p>
        <div className="mt-6"><Round key={hero.id} unit={hero} pointers={heroPointers} api={api} compact /></div>
      </section>

      <section className="border-t border-line py-8">
        <p className="max-w-3xl text-[18px] font-medium leading-snug [text-wrap:balance] sm:text-[20px]">{POSITIONING}</p>
        <div className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat value={fmtInt(stats.directions)} label="RBI Master Directions in the corpus" />
          <Stat value={fmtInt(stats.paragraphs)} label="paragraphs, each with a stable pointer" />
          <Stat value={String(stats.units)} label={`comparisons labelled by an expert (${stats.items} obligations)`} />
          <Stat value={`${stats.recovered} / ${stats.missedA}`} label="real differences every LLM system missed that the structured comparator caught" />
        </div>
      </section>

      <section className="border-t border-line py-8" aria-labelledby="next">
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="I'm here as">
          <span className="text-[13px] text-ink-3">I'm here as:</span>
          {PERSONAS.map((p) => (
            <button key={p.id} type="button" role="radio" aria-checked={persona === p.id} onClick={() => set(p.id)}
              className={cn("rounded-full border px-3 py-1 text-[13px]", persona === p.id ? "border-accent bg-accent text-white dark:text-black" : "border-line bg-panel text-ink-2 hover:border-ink-3")}>{p.label}</button>
          ))}
          {persona === "compliance" && (
            <label className="ml-1 flex items-center gap-1.5 text-[13px] text-ink-2">Your institution type
              <select value={myClass} onChange={(e) => setClass(e.target.value)} className="h-8 rounded-md border border-line bg-panel px-2 text-[13px] text-ink">
                <option value="">Any</option>{h.data.classes.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
          )}
        </div>
        <h2 id="next" className="sr-only">Where to go next</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {cards.map((c) => (
            <Link key={c.title} to={c.to} className="group rounded-xl border border-line bg-panel p-5 transition-colors hover:border-accent">
              <span className="text-accent">{c.icon}</span>
              <span className="mt-3 flex items-center gap-1 text-[17px] font-semibold">{c.title}<ArrowRight size={15} className="text-accent" aria-hidden /></span>
              <span className="mt-1 block text-[14px] text-ink-2">{c.text}</span>
            </Link>
          ))}
        </div>
        <p className="mt-4 text-[13px] text-ink-3">The comparator also over-flags: {stats.falseAlarms} of its {stats.comparatorFound + stats.falseAlarms} “different” calls were judged same or unmatched by the expert. Every number here has its caveats on <Link to="/results" className="text-accent hover:underline">Results</Link> and <Link to="/method" className="text-accent hover:underline">Method &amp; Trust</Link>.</p>
      </section>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="min-w-0">
      <p className="num text-[28px] font-semibold leading-none tracking-tight sm:text-[32px]">{value}</p>
      <p className="mt-1.5 text-[13px] leading-snug text-ink-2">{label}</p>
    </div>
  );
}

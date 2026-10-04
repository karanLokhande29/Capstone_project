import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Gamepad2, Grid3x3, Search } from "lucide-react";
import { Badge, Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import { caseHref, useIndex } from "../data";
import { Loading, LoadError, PageHead } from "../DemoLayout";
import { useCaseNav } from "../case/CaseView";
import { bandTone, VERDICT_SHORT } from "../names";
import type { IndexUnit } from "../types";
import { CasesNav } from "./CasesNav";

const FILTERS = ["src", "tgt", "topic", "gold", "cmp", "missed", "band", "route"] as const;
type FilterKey = (typeof FILTERS)[number];
const PAGE = 40;

export default function Cases() {
  const idx = useIndex();
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const setNav = useCaseNav((s) => s.set);
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [shown, setShown] = useState(PAGE);
  const f = Object.fromEntries(FILTERS.map((k) => [k, sp.get(k) ?? ""])) as Record<FilterKey, string>;
  const cls = sp.get("class") ?? "";
  const units = useMemo(() => idx.data?.units ?? [], [idx.data]);
  const opts = useMemo(() => ({
    src: [...new Set(units.map((u) => u.src))].sort(), tgt: [...new Set(units.map((u) => u.tgt))].sort(),
    topic: [...new Set(units.map((u) => u.topic ?? ""))].sort(), route: [...new Set(units.map((u) => u.route))].sort(),
  }), [units]);
  const rows = useMemo(() => units.filter((u) => {
    const cmpOk = u.sys.comparator === u.gold;
    return (!f.src || u.src === f.src) && (!f.tgt || u.tgt === f.tgt) && (!f.topic || u.topic === f.topic) && (!f.gold || u.gold === f.gold)
      && (!f.cmp || (f.cmp === "correct" ? cmpOk : !cmpOk)) && (!f.missed || (f.missed === "A" ? u.missedA : !u.missedA))
      && (!f.band || u.band === f.band) && (!f.route || u.route === f.route) && (!cls || u.src === cls || u.tgt === cls)
      && (!q.trim() || u.id.toLowerCase().includes(q.trim().toLowerCase()) || u.srcPid.toLowerCase().includes(q.trim().toLowerCase()));
  }), [units, f.src, f.tgt, f.topic, f.gold, f.cmp, f.missed, f.band, f.route, cls, q]);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); setShown(PAGE); };
  const open = (u: IndexUnit) => { setNav(rows.map((r) => r.id), "your Explore filter"); navigate(caseHref(u.id)); };

  return (
    <div>
      <PageHead eyebrow="Cases" title="412 expert-labelled comparisons between parallel RBI rules.">
        Each case pairs one institution type's obligation with the closest rule for another type. An expert labelled it <i>same</i>, <i>different</i> or <i>no matching rule</i>;
        five AI systems and a structured comparator answered the same question. Pick a way in:
      </PageHead>
      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <Choice to="/cases/play" icon={<Gamepad2 size={20} />} title="Can you spot the difference?" sub="Challenge yourself on regulatory pairs." />
        <Choice to="/cases/failures" icon={<Grid3x3 size={20} />} title="Where do the models fail?" sub="Explore the 78 real differences." />
        <Choice onClick={() => document.getElementById("explore")?.scrollIntoView({ behavior: "smooth" })} icon={<Search size={20} />} title="Inspect a specific case" sub="Search the benchmark." />
      </div>
      <CasesNav />

      <section id="explore" className="scroll-mt-20 pt-6" aria-labelledby="explore-h">
        <h2 id="explore-h" className="text-[20px] font-semibold">Explore</h2>
        {idx.error ? <LoadError error={idx.error} /> : !idx.data ? <Loading what="the cases" /> : (
          <>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Sel label="Source class" v={f.src} on={(v) => set("src", v)} options={opts.src} />
              <Sel label="Target class" v={f.tgt} on={(v) => set("tgt", v)} options={opts.tgt} />
              <Sel label="Topic" v={f.topic} on={(v) => set("topic", v)} options={opts.topic} />
              <Sel label="Expert verdict" v={f.gold} on={(v) => set("gold", v)} options={["same", "different", "none"]} fmt={(x) => VERDICT_SHORT[x as "same"]} />
              <Sel label="Comparator" v={f.cmp} on={(v) => set("cmp", v)} options={["correct", "incorrect"]} />
              <Sel label="Missed by all five LLMs" v={f.missed} on={(v) => set("missed", v)} options={["A", "no"]} fmt={(x) => (x === "A" ? "yes (56)" : "no")} />
              <Sel label="Confidence band (M2)" v={f.band} on={(v) => set("band", v)} options={["High", "Medium", "Low", "Abstain"]} />
              <Sel label="Gold route" v={f.route} on={(v) => set("route", v)} options={opts.route} />
            </div>
            <label className="mt-2 flex max-w-md items-center gap-2 rounded-md border border-line bg-panel px-2">
              <Search size={15} className="text-ink-3" aria-hidden />
              <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }} placeholder="Search by paragraph or case id (e.g. md_12949::p00040)"
                className="h-9 min-w-0 flex-1 bg-transparent text-[14px] outline-none" aria-label="Search by paragraph id" />
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
              <span className="num">{rows.length} of {units.length} cases</span>
              {cls && <Badge tone="accent">Involving {cls} <button type="button" className="ml-1" aria-label="Clear class filter" onClick={() => set("class", "")}>×</button></Badge>}
              {(FILTERS.some((k) => f[k]) || q) && <button type="button" className="text-accent hover:underline" onClick={() => { setQ(""); setSp(new URLSearchParams(), { replace: true }); }}>Clear filters</button>}
            </div>
            <ul className="mt-3 divide-y divide-line rounded-lg border border-line bg-panel">
              {rows.slice(0, shown).map((u) => (
                <li key={u.id}>
                  <Link to={caseHref(u.id)} onClick={(e) => { e.preventDefault(); open(u); }}
                    className="grid gap-1 px-4 py-3 hover:bg-panel-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                    <span className="min-w-0">
                      <span className="block text-[14px] font-medium">{u.src} → {u.tgt}</span>
                      <span className="block truncate text-[12.5px] text-ink-3">{u.topic} · <span className="font-mono">{u.srcPid}</span></span>
                    </span>
                    <span className="flex flex-wrap items-center gap-1.5 text-[12px]">
                      <Badge tone="outline">Expert: {VERDICT_SHORT[u.gold]}</Badge>
                      <Badge tone={u.sys.comparator === u.gold ? "pos" : "neg"}>Comparator: {u.sys.comparator in VERDICT_SHORT ? VERDICT_SHORT[u.sys.comparator as "same"] : "no call"}</Badge>
                      {u.sys.comparator !== "different" && <Badge tone={bandTone(u.band)}>{u.band}</Badge>}
                      {u.missedA && <Badge tone="warn">all LLMs missed</Badge>}
                    </span>
                  </Link>
                </li>
              ))}
              {rows.length === 0 && <li className="px-4 py-6 text-[14px] text-ink-3">No case matches these filters.</li>}
            </ul>
            {rows.length > shown && <Button variant="outline" className="mt-3" onClick={() => setShown(shown + PAGE)}>Show more ({rows.length - shown} left)</Button>}
          </>
        )}
      </section>
    </div>
  );
}

function Choice({ to, onClick, icon, title, sub }: { to?: string; onClick?: () => void; icon: React.ReactNode; title: string; sub: string }) {
  const body = (
    <>
      <span className="text-accent">{icon}</span>
      <span className="mt-3 block text-[18px] font-semibold leading-snug">{title}</span>
      <span className="mt-1 block text-[14px] text-ink-2">{sub}</span>
      <ArrowRight size={16} className="mt-3 text-accent" aria-hidden />
    </>
  );
  const cls = "block w-full rounded-xl border border-line bg-panel p-5 text-left transition-colors hover:border-accent";
  return to ? <Link to={to} className={cls}>{body}</Link> : <button type="button" onClick={onClick} className={cn(cls, "cursor-pointer")}>{body}</button>;
}

function Sel({ label, v, on, options, fmt }: { label: string; v: string; on: (v: string) => void; options: string[]; fmt?: (x: string) => string }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] text-ink-3">{label}
      <select value={v} onChange={(e) => on(e.target.value)} className="h-9 min-w-0 rounded-md border border-line bg-panel px-2 text-[13.5px] text-ink">
        <option value="">Any</option>
        {options.map((o) => <option key={o} value={o}>{fmt ? fmt(o) : o || "—"}</option>)}
      </select>
    </label>
  );
}
